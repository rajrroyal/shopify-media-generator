const API_ROOT = import.meta.env.VITE_API_URL || '/api';

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
  const redirectStartedAt = Number(sessionStorage.getItem('shopify-auth-redirecting'));
  if (!shop || (redirectStartedAt && Date.now() - redirectStartedAt < 10000)) return;
  sessionStorage.setItem('shopify-auth-redirecting', String(Date.now()));
  const params = new URLSearchParams({shop});
  if (current.get('host')) params.set('host', current.get('host'));
  window.open(`${API_ROOT}/auth/shopify/launch/?${params}`, '_top');
}

async function currentSessionToken() {
  const initialToken = launchToken();
  return Promise.race([
    window.shopify?.idToken
      ? window.shopify.idToken().catch(() => initialToken)
      : Promise.resolve(initialToken),
    new Promise(resolve => setTimeout(() => resolve(initialToken), 3000)),
  ]);
}

async function request(path, options = {}, retryAuthentication = true) {
  const sessionToken = await currentSessionToken();
  const {timeoutMs = 45000, ...fetchOptions} = options;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  let response;
  try {
    response = await fetch(apiUrl(path), {
      ...fetchOptions,
      signal: fetchOptions.signal || controller.signal,
      headers: {
        'Content-Type': 'application/json',
        'X-Shop-Domain': shopDomain(),
        ...(sessionToken ? {Authorization: `Bearer ${sessionToken}`} : {}),
        ...fetchOptions.headers,
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
    if (response.status === 401 && retryAuthentication && sessionToken) {
      return request(path, options, false);
    }
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
    method: 'POST',
    body: JSON.stringify({prompts}),
    timeoutMs: 15 * 60 * 1000,
  }),
  addToShopify: (jobId, imageIds) => request(`/generation/jobs/${jobId}/add-to-shopify/`, {
    method: 'POST', body: JSON.stringify({image_ids: imageIds}),
  }),
  createVideoJob: (productId, sourceImages) => request('/generation/video-jobs/', {
    method: 'POST', body: JSON.stringify({product_id: productId, source_images: sourceImages}),
  }),
  generateVideoPrompt: jobId => request(`/generation/video-jobs/${jobId}/generate-prompt/`, {method: 'POST'}),
  generateVideo: (jobId, payload) => request(`/generation/video-jobs/${jobId}/generate/`, {
    method: 'POST', body: JSON.stringify(payload),
  }),
  addVideoToShopify: jobId => request(`/generation/video-jobs/${jobId}/add-to-shopify/`, {method: 'POST'}),
  plans: () => request('/billing/plans/'),
  subscribe: planId => request('/billing/subscribe/', {
    method: 'POST', body: JSON.stringify({plan_id: planId}),
  }),
  purchaseCredits: packId => request('/billing/purchase-credits/', {
    method: 'POST', body: JSON.stringify({pack_id: packId}),
  }),
  confirmCreditPurchase: reference => request('/billing/confirm-credit-purchase/', {
    method: 'POST', body: JSON.stringify({reference}),
  }),
};
