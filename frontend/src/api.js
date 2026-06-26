const API_ROOT = import.meta.env.VITE_API_URL || '/api';

function shopDomain() {
  return new URLSearchParams(location.search).get('shop') || 'demo-store.myshopify.com';
}

function apiUrl(path) {
  const params = new URLSearchParams();
  params.set('shop', shopDomain());
  return `${API_ROOT}${path}${path.includes('?') ? '&' : '?'}${params}`;
}

async function request(path, options = {}) {
  const sessionToken = window.shopify?.idToken ? await window.shopify.idToken() : null;
  const response = await fetch(apiUrl(path), {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-Shop-Domain': shopDomain(),
      ...(sessionToken ? {Authorization: `Bearer ${sessionToken}`} : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || 'Something went wrong');
  }
  return response.status === 204 ? null : response.json();
}

export const api = {
  me: () => request('/me/'),
  products: () => request('/shopify/products/'),
  jobs: () => request('/generation/jobs/'),
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
};
