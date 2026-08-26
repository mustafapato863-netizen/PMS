# Environment Variables Directory

This document details all configurations, secrets, database parameters, and environment flags used by the PMS Dashboard services.

---

## 1. Backend Service Configuration Variables

The following properties configure the FastAPI application server, database mappings, and logging outputs:

| Variable | Type | Default | Purpose |
| :--- | :--- | :--- | :--- |
| `APP_ENV` | String | `development` | Runtime safety profile. Hosted production must set `production`. |
| `PORT` | Integer | `8000` direct / `7860` container | HTTP port. The container/platform may override it. |
| `DATABASE_URL` | Connection URL | N/A | PostgreSQL connection string (`postgresql://user:pass@host:5432/db`). |
| `DATABASE_POOL_SIZE` | Integer | `20` development / `5` hosted | Maximum persistent database connections. |
| `DATABASE_MAX_OVERFLOW`| Integer | `10` development / `0` hosted | Temporary database connection overflow headroom. |
| `DATABASE_POOL_RECYCLE`| Integer | `1800` | Bumps stale database connections after specified seconds. |
| `PMS_AUTO_SEED` | Boolean | `false` outside development | Seeds the bundled workbook only when explicitly enabled; keep disabled in hosted production. |
| `PMS_SEED_PERMISSIONS_ON_STARTUP` | Boolean | `false` outside development | Seeds permissions at startup. Forbidden in production; use a controlled release job. |
| `PMS_SEED_DEMO_LEVELS` | Boolean | `false` | Seeds demo performance levels. Forbidden in production. |
| `REDIS_URL` | Connection URL | N/A | Redis caching instance string (`redis://:pass@host:6379/0`). |
| `REDIS_SOCKET_TIMEOUT_SECONDS` | Decimal seconds | `0.25` | Upper bound for a Redis connection or command attempt before falling back. |
| `REDIS_RETRY_INTERVAL_SECONDS` | Decimal seconds | `30` | Cooldown before retrying an unavailable Redis service. |
| `PMS_REALTIME_MODE` | Enum String | `disabled` on Vercel; `in_process` elsewhere | Enables process-local Socket.IO only on a compatible single-process runtime. |
| `PMS_REPORT_CENTER_ENABLED` | Boolean | `true` locally; explicitly staged in hosted environments | Enables the role-adaptive Reports Center routes. Keep the legacy report workspace available for rollback during the first release. |
| `PMS_SCOPED_PERFORMANCE_API_ENABLED` | Boolean | `false` | Enables the bounded, scope-aware performance summary/records/history routes. Roll out only with the matching frontend flag. |
| `PMS_SCOPED_PERFORMANCE_ALLOWED_ROLES` | CSV roles | unset | Optional allow-list for scoped performance reads, for example `Admin,Manager,Executive`. |
| `JWT_SECRET` | String | N/A | Encryption key used to sign session cookies and JWTs. |
| `JWT_ALGORITHM` | String | `HS256` | Encryption token hashing format. |
| `JWT_EXPIRE_MINUTES` | Integer | `10` | Short-lived bearer access-token lifespan in minutes. |
| `AUTH_REFRESH_SESSION_HOURS` | Integer | `8` | Non-remembered browser refresh-session lifetime. |
| `AUTH_REMEMBER_SESSION_DAYS` | Integer | `30` | Remember-me browser refresh-session lifetime. |
| `AUTH_COOKIE_SECURE` | Boolean | `true` in hosted environments | Sends refresh and CSRF cookies only over HTTPS. |
| `AUTH_COOKIE_SAMESITE` | `lax, strict, or none` | `lax` locally, `none` for split-origin hosting | Cookie cross-site policy; `none` requires `AUTH_COOKIE_SECURE=true`. |
| `AUTH_COOKIE_DOMAIN` | Hostname | unset | Optional shared cookie domain when frontend/API are under the same parent domain. |
| `CORS_ALLOWED_ORIGINS` | CSV origins | Local frontend origins | Exact trusted browser origins. Wildcards are rejected in production. |
| `PMS_DATA_DIR` | Directory Path | `/app/data` | Container storage path preserving uploaded sheets. |
| `PMS_DEFAULT_FILE_PATH`| File Path | `/app/data/PMS_Trend_All.xlsx` | Default seed workbook fallback file path. |
| `LOG_LEVEL` | Enum String | `INFO` | Structured logging volume filters (DEBUG/INFO/WARNING/ERROR). |

---

## 2. Frontend Web Portal Variables

Vercel builds static assets and injects the following variables into index bundles:

| Variable | Type | Default | Purpose |
| :--- | :--- | :--- | :--- |
| `VITE_API_BASE_URL` | Endpoint URL | `http://localhost:8000` | Base API target URL for HTTP requests. |
| `VITE_SOCKET_URL` | Endpoint URL | `http://localhost:8000` | Base URL target for WebSocket connections. |
| `VITE_REALTIME_ENABLED` | Boolean | `false` in production; `true` in development | Enables the Socket.IO client only when the backend runs in `in_process` realtime mode. |
| `VITE_SCOPED_PERFORMANCE_API` | Boolean | `false` | Switches dashboard consumers to the bounded REST read path. Enable only after the backend flag and role rollout are ready. |
| `VITE_REPORT_CENTER_ENABLED` | Boolean | `true` locally; explicitly staged in hosted environments | Enables the Reports Center client. Coordinate with `PMS_REPORT_CENTER_ENABLED` during rollout. |

---

## 3. Monitoring & Operations Variables

Variables mapping ports and credentials for monitoring tools:

| Variable | Type | Default | Purpose |
| :--- | :--- | :--- | :--- |
| `PROMETHEUS_PORT` | Integer | `9090` | Host port exposing Prometheus dashboards. |
| `GRAFANA_PORT` | Integer | `3000` | Host port exposing Grafana analytical widgets. |
| GF_SECURITY_ADMIN_USER | String | `admin` | Initial Grafana dashboard administrator user ID. |
| GF_SECURITY_ADMIN_PASSWORD | String | `adminpassword` | Initial Grafana dashboard administrator password. |
| `ENVIRONMENT` | String | `production` | Deploy profile configuration identifier (production/staging/dev). |
| `APP_VERSION` | String | `2.0.0` | Containerized build version tag tracker. |
