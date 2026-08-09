# Self-Hosted VPS Deployment Guide

This guide now points to the canonical Hostinger-compatible monorepo deployment. See [`hostinger-vps.md`](hostinger-vps.md) for the full production procedure.

---

## 1. Deployment Model & Architecture

A self-hosted deployment runs the TLS gateway, static frontend, API, and Redis on the VPS. PostgreSQL remains on Supabase.

```
                  Web Client Request (Port 80 / 443)
                                 |
                                 v
                            [Caddy TLS Gateway]
                                 |
           +---------------------+---------------------+
           |                                           |
           v (Port 80)                                 v (Port 7860)
  [Static React Files]                          [FastAPI Backend]
                                                       |
                                            +----------+----------+
                                            |                     |
                                            v                     v
                                   [Supabase PostgreSQL]       [Redis]
```

---

## 2. Prerequisites
- A VPS running Ubuntu 20.04/22.04 LTS (minimum 2 Core CPU, 4GB RAM).
- Docker and Docker Compose installed:
  - Docker v20.10+
  - Docker Compose v2.0+
- A domain name pointing to the VPS public IP address.
- Port 80 and 443 open on the network firewall.

---

## 3. Provisioning Steps

1. **Clone the monorepo:**
   ```bash
   git clone <repository-url> /opt/pms-dashboard
   cd /opt/pms-dashboard
   ```

2. **Configure Environment variables:**
   Create a `.env` file from the template and edit it:
   ```bash
   cp DevOps/.env.hostinger.example DevOps/.env.hostinger
   nano DevOps/.env.hostinger
   ```

3. **Establish Scripts Permissions:**
   ```bash
   chmod +x DevOps/scripts/*.sh
   ```

4. **Run Ingestion and Compilation Deployments:**
   ```bash
   DevOps/scripts/deploy.sh
   ```

5. **Verify Stack Container health checks:**
   ```bash
   docker compose --env-file DevOps/.env.hostinger -f compose.production.yml ps
   ```

---

## 4. Backups and Logging Maintenance
- Use Supabase managed backups as the primary database recovery mechanism and verify restore procedures in staging.
- Logger rotated trace files reside under the backend's `/app/logs/` directories inside the container.
