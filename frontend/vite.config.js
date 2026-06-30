import {defineConfig, loadEnv} from 'vite';
import react from '@vitejs/plugin-react';
import process from 'node:process';
import path from 'node:path';

function shopifyFrameProtection() {
  const middleware = server => {
    server.middlewares.use((request, response, next) => {
      const url = new URL(request.url || '/', 'https://localhost');
      const shop = (url.searchParams.get('shop') || '').toLowerCase();
      const ancestors = ['https://admin.shopify.com'];
      if (/^[a-z0-9][a-z0-9-]*\.myshopify\.com$/.test(shop)) {
        ancestors.unshift(`https://${shop}`);
      }
      response.setHeader('Content-Security-Policy', `frame-ancestors ${ancestors.join(' ')};`);
      next();
    });
  };
  return {
    name: 'shopify-frame-protection',
    configureServer: middleware,
    configurePreviewServer: middleware,
  };
}

export default defineConfig(({mode}) => {
  const env = loadEnv(mode, process.cwd(), '');
  const backendEnv = loadEnv(mode, path.resolve(process.cwd(), '../backend'), '');
  const apiKey = env.VITE_SHOPIFY_API_KEY || backendEnv.SHOPIFY_API_KEY;
  const embedded = env.VITE_SHOPIFY_EMBEDDED !== 'false';
  const appBridge = embedded && apiKey
    ? `<meta name="shopify-api-key" content="${apiKey}" />
    <script src="https://cdn.shopify.com/shopifycloud/app-bridge.js"></script>`
    : '';
  const allowedHosts = [
    'localhost',
    '127.0.0.1',
    'media-generator.mailmerit.com',
  ];
  const backendProxy = {
    target: 'http://127.0.0.1:8000',
    changeOrigin: true,
  };
  const proxy = {
    '/api': backendProxy,
    '/media': backendProxy,
  };

  return {
    plugins: [
      shopifyFrameProtection(),
      react(),
      {
        name: 'shopify-app-bridge',
        transformIndexHtml: (html) => html.replace('<!-- shopify-app-bridge -->', appBridge),
      },
    ],
    server: {
      port: 5173,
      allowedHosts,
      hmr: false,
      proxy,
    },
    preview: {
      host: '0.0.0.0',
      port: 5173,
      allowedHosts,
      proxy,
    },
  };
});
