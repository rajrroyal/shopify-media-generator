# PixelMint AI

An embedded Shopify app for generating product photography with AI, reviewing results, and attaching selected images to Shopify products.

## What is included

- React + React Router + Shopify Polaris merchant UI
- Django + Django REST Framework API
- Celery tasks with Redis configuration
- Shopify OAuth, live catalog reads, product media, and subscription service boundaries
- OpenAI prompt and image generation integration
- Credit ledger with automatic refunds when generation fails
- Local demo mode, PostgreSQL-ready generation storage, and filesystem media storage
- Production-ready environment seams for PostgreSQL, Redis, and S3

## Project layout

```text
backend/   Django API, workers, Shopify/OpenAI services
frontend/  React embedded app
```

## Quick start

### Backend

Python 3.12+ is recommended.

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

In another terminal, once Redis is available:

```bash
celery -A config worker -l info
```

Without Redis, set `CELERY_TASK_ALWAYS_EAGER=true` in `.env`.

### Frontend

Node 20+ is recommended.

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Set `VITE_DEMO_MODE=true` only when you explicitly
want the standalone demo catalog.

Product catalog data is always read directly from the Shopify Admin API. PixelMint
stores generation jobs, prompts, generated images, credits, and a small immutable
product snapshot inside each generation job for historical display; it does not
maintain or synchronize a local product catalog.

### PostgreSQL

The backend reads its database from `DATABASE_URL` in `backend/.env`.

```env
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DB_NAME
```

For local PostgreSQL, create the database and user first, then run:

```bash
cd backend
python manage.py migrate
python manage.py seed_demo
```

## Required configuration

See [`backend/.env.example`](backend/.env.example). For live Shopify use, create a public app in the Shopify Partner Dashboard and configure:

- App URL: your HTTPS frontend URL
- Allowed redirection URL: `https://your-api.example.com/api/auth/shopify/callback/`
- Scopes: `read_products,write_products,read_files,write_files`

Webhooks should point to:

- `/api/webhooks/app-uninstalled/`
- `/api/webhooks/app-purchases-one-time-update/`

Subscription plans and one-time credit packs are managed in Django admin under
**Subscription plans** and **Credit packs**. Plan credits reset with the Shopify
billing period; purchased credits are stored separately and roll over.

## Production notes

- Put Django and Celery behind HTTPS.
- Use PostgreSQL, Redis, S3-compatible object storage, and a secrets manager.
- Validate Shopify session tokens on every embedded request. The included dev header fallback is intentionally disabled unless `DEBUG=true`.
- Configure Shopify billing return URLs and webhook subscriptions.
- Run workers separately from the web process.
