# Railway Deployment Guide (Backend API)

This guide documents the procedures for deploying the FastAPI backend server on **Railway**.

---

## 1. Deployment Model & Strategy

Railway connects directly to your GitHub repository and automatically deploys the application on every commit pushed to the main branch (`develop` or `main` depending on staging configurations).

```
[GitHub Repo: PMS-Backend] ──(Webhook Trigger)──> [Railway Platform]
                                                          │
                                                    (Docker Build)
                                                          │
                                                          v
                                               [FastAPI ASGI Container]
                                              (Health Checks at /api/health)
```

---

## 2. Prerequisites
- A Railway developer account connected to your GitHub profile.
- A PostgreSQL database provisioned as a service on Railway.
- A Redis cache instance provisioned as a service on Railway.

---

## 3. In-Repository Requirements
Because Railway builds and deploys directly from the application repository, the backend repo must retain the following build files:
- `Dockerfile` — Contains the secure multi-stage runner instructions.
- `requirements.txt` — Declares all required backend packages and libraries.

---

## 4. Provisioning & Setup

1. **Create New Project:** Go to the Railway dashboard, select **New Project**, and pick **Deploy from GitHub repository**.
2. **Select Repository:** Choose `PMS-Backend`.
3. **Provision Databases:**
   * Click **New** -> **Database** -> **Add PostgreSQL**.
   * Click **New** -> **Database** -> **Add Redis**.
   * Railway automatically provisions the instances and binds their connection variables (`DATABASE_URL` and `REDIS_URL`) to the backend environment context.
4. **Configure Environment Variables:** Add the following environment properties on the service variable configuration tab:
   * `JWT_SECRET` — Secure 32-byte signing secret.
   * `JWT_ALGORITHM` — Defaults to `HS256`.
   * `JWT_EXPIRE_MINUTES` — Defaults to `10` minutes for short-lived access tokens.
   * `AUTH_REFRESH_SESSION_HOURS` — Defaults to `8` hours for non-remembered sessions.
   * `AUTH_REMEMBER_SESSION_DAYS` — Defaults to `30` days for explicit Remember me sessions.
   * `AUTH_COOKIE_SECURE` — Must be `true` for HTTPS deployment.
   * `AUTH_COOKIE_SAMESITE` — Use `none` for a split-origin frontend/API deployment.
   * `PMS_DATA_DIR` — Set to `/app/data` (persistent volume path).
   * `PORT` — Set to `7860` (Railway port mapping target).
5. **Configure Persistent Disk Volume:** Under the service settings, mount a persistent volume at `/app/data` to preserve Excel upload documents and static worksheets across container rebuilds.

---

## 5. Health Check Monitoring

Configure the health check parameters inside the Railway dashboard under **Service Settings**:
- **Healthcheck Path:** `/api/health/liveness` (returns instantly to ensure container responsiveness).
- **Restart Policy:** Enabled. Re-provisions container immediately if health queries return non-200.
