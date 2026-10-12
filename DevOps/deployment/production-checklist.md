# Production Deployment Checklist

This checklist contains the pre-flight verification checks required before deploying releases or promoting branches to the production server.

---

## 1. Pre-Release Compilation & Verification Gates

- [ ] **Backend Test Coverage:** Run `python -m pytest tests -v` inside Backend ensuring zero test suite failures.
- [ ] **Frontend Build Compilation:** Run `npm run build` inside Frontend to guarantee React static bundles compile without TypeScript errors.
- [ ] **Frontend Code Linting:** Run `npm run lint` to prevent format issues.
- [ ] **Database Schema Migrations:** Run `alembic current` to ensure database tables match the code migrations history.

---

## 2. Security & Secrets Management Checks

- [ ] **Secrets Sanitization:** Verify that no credentials, API keys, or raw passwords exist inside config or compose files.
- [ ] **Environment Validation:** Verify `.env` is securely loaded on the host VPS.
- [ ] **JWT Key Strength:** Confirm `JWT_SECRET` is set to a secure, randomly generated 32-byte value.
- [ ] **Access Port Isolation:** Check firewalls to ensure PostgreSQL (5432) and Redis (6379) are isolated from public ingress. Only ports 80/443 (HTTP/S) and SSH (22) should be publicly accessible.
- [ ] **Orchestrator Health Config:** Verify liveness (`/api/health/liveness`) and readiness (`/api/health/readiness`) checks are wired into Docker container definitions.

---

## 3. Storage, Volumes, and Backup Validation

- [ ] **Volume Persistence:** Ensure persistent volume directories (`/app/data` for uploads, `/var/lib/postgresql/data` for DB) are correctly mapped to host paths.
- [ ] **Host Storage Checks:** Run `df -h` on the host VPS to ensure at least 20% available storage space.
- [ ] **Backup Automation:** Confirm `scripts/backup-db.sh` is mapped to run daily via cron.
- [ ] **Recovery Audit:** Run a database restore dry-run using a generated SQL dump on a staging instance to verify backup file integrity.

## 4. Rate Limiting and Proxy Trust

- [ ] **Network migration:** On an existing host, the one-time `down` / `up` in `self-hosted-vps.md`, section 3a, has been run. The `private` network reports the subnet configured for this host.
- [ ] **Subnet is free:** No host or Docker network overlaps `PMS_PRIVATE_SUBNET` (default `10.218.10.0/24`).
- [ ] **Trusted proxy matches:** `PMS_TRUSTED_PROXY_CIDRS` equals `PMS_PRIVATE_SUBNET`, and the gateway's address is inside it.
- [ ] **Mode:** `PMS_RATE_LIMIT_MODE` is `enforce` in production (the default when `APP_ENV=production`).
- [ ] **Redis:** `REDIS_URL` is set, so counters are shared. Without it each process keeps its own counters.
