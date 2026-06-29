import {defineConfig, loadEnv} from 'vite';
import react from '@vitejs/plugin-react';
import process from 'node:process';

export default defineConfig(({mode}) => {
  const env = loadEnv(mode, process.cwd(), '');
  const appBridge = env.VITE_SHOPIFY_EMBEDDED === 'true' && env.VITE_SHOPIFY_API_KEY
    ? `<meta name="shopify-api-key" content="${env.VITE_SHOPIFY_API_KEY}" />
    <script src="https://cdn.shopify.com/shopifycloud/app-bridge.js"></script>`
    : '';

  return {
    plugins: [
      react(),
      {
        name: 'shopify-app-bridge',
        transformIndexHtml: (html) => html.replace('<!-- shopify-app-bridge -->', appBridge),
      },
    ],
    server: {
      port: 5173,
      allowedHosts: [
        'localhost',
        '127.0.0.1',
        'media-generator.mailmerit.com',
      ],
      proxy: {
        '/api': 'http://localhost:8000',
        '/media': 'http://localhost:8000',
      },
    },
  };
});
