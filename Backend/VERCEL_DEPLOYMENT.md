# Deploying the FastAPI backend on Vercel

Vercel detects the exported ASGI application from `app.py`. When creating the
Vercel project from the `PMS` repository, set **Root Directory** to
`Backend` and leave the Framework Preset as **Other**. The checked-in
`Backend/vercel.json` configures the Python function bundle and includes the
team configuration files read at runtime.

## Required environment variables

Set these in Vercel Project Settings for Production, Preview, and Development
as appropriate:

- `DATABASE_URL` — Supabase Pooler SQLAlchemy URL with `sslmode=require`.
- `APP_ENV=production`
- `PMS_AUTO_SEED=false`
- `PMS_REALTIME_MODE=disabled`
- `REDIS_SOCKET_TIMEOUT_SECONDS=0.25`
- `REDIS_RETRY_INTERVAL_SECONDS=30`
- `CORS_ALLOWED_ORIGINS` — the deployed frontend origin(s), comma-separated.
- Existing application secrets such as `JWT_SECRET` and any Redis settings
  used by the selected features.

Run database bootstrap/migrations as a release job before serving traffic. Do
not run Alembic from every Vercel function invocation.

## Runtime boundary

Vercel provides request-oriented serverless functions. REST endpoints work,
but Socket.IO/WebSocket connections are not a durable process; host the
real-time worker on Railway, Render, or a VPS if persistent connections are
required. The frontend should point `VITE_API_BASE_URL` to the deployed API.
