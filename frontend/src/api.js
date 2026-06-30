const API_ROOT = import.meta.env.VITE_API_URL || '/api';
let sessionTokenPromise = null;

function shopDomain() {
  return new URLSearchParams(location.search).get('shop') || '';
}

function launchToken() {
  return new URLSearchParams(location.search).get('id_token') || null;
}

function apiUrl(path) {
  const params = new URLSearchParams();
  const current = new URLSearchParams(location.search);
  ['shop', 'host', 'embedded'].forEach(key => {
    if (current.get(key)) params.set(key, current.get(key));
  });
  return `${API_ROOT}${path}${path.includes('?') ? '&' : '?'}${params}`;
}

function beginShopifyAuth() {
  const current = new URLSearchParams(location.search);
  const shop = shopDomain();
  if (!shop || sessionStorage.getItem('shopify-auth-redirecting')) return;
  sessionStorage.setItem('shopify-auth-redirecting', 'true');
  const params = new URLSearchParams({shop});
  if (current.get('host')) params.set('host', current.get('host'));
  window.open(`${API_ROOT}/auth/shopify/launch/?${params}`, '_top');
}

async function request(path, options = {}) {
  if (!sessionTokenPromise) {
    const initialToken = launchToken();
    sessionTokenPromise = Promise.race([
      window.shopify?.idToken
        ? window.shopify.idToken().catch(() => initialToken)
        : Promise.resolve(initialToken),
      new Promise(resolve => setTimeout(() => resolve(initialToken), 3000)),
    ]);
    setTimeout(() => { sessionTokenPromise = null; }, 30000);
  }
  const sessionToken = await sessionTokenPromise;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 45000);
  let response;
  try {
    response = await fetch(apiUrl(path), {
      ...options,
      signal: options.signal || controller.signal,
      headers: {
        'Content-Type': 'application/json',
        'X-Shop-Domain': shopDomain(),
        ...(sessionToken ? {Authorization: `Bearer ${sessionToken}`} : {}),
        ...options.headers,
      },
    });
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new Error('Shopify took too long to respond. Please try again.');
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    if (response.status === 401) beginShopifyAuth();
    const errorMessages = Array.isArray(payload.errors)
      ? payload.errors.map(error => error.message || String(error)).join('; ')
      : '';
    throw new Error(payload.detail || errorMessages || `Request failed (${response.status})`);
  }
  sessionStorage.removeItem('shopify-auth-redirecting');
  return response.status === 204 ? null : response.json();
}

export const api = {
  me: () => request('/me/'),
  products: () => request('/shopify/products/'),
  product: productId => request(`/shopify/products/${encodeURIComponent(productId)}/`),
  jobs: () => request('/generation/jobs/'),
  job: jobId => request(`/generation/jobs/${jobId}/`),
  createJob: (productId, sourceImages) => request('/generation/jobs/', {
    method: 'POST', body: JSON.stringify({product_id: productId, source_images: sourceImages}),
  }),
  generatePrompts: (jobId) => request(`/generation/jobs/${jobId}/generate-prompts/`, {method: 'POST'}),
  generateImages: (jobId, prompts) => request(`/generation/jobs/${jobId}/generate-images/`, {
    method: 'POST', body: JSON.stringify({prompts}),
  }),
  addToShopify: (jobId, imageIds) => request(`/generation/jobs/${jobId}/add-to-shopify/`, {
    method: 'POST', body: JSON.stringify({image_ids: imageIds}),
  }),
  plans: () => request('/billing/plans/'),
  subscribe: planId => request('/billing/subscribe/', {
    method: 'POST', body: JSON.stringify({plan_id: planId}),
  }),
  purchaseCredits: packId => request('/billing/purchase-credits/', {
    method: 'POST', body: JSON.stringify({pack_id: packId}),
  }),
};
