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

## 3a. One-Time Network Change for Rate Limiting

The `private` network has a fixed subnet, `10.218.10.0/24` by default. The gateway sits on it, and the backend honours `X-Forwarded-For` only from that range. Without this, every user is seen as the gateway address, and all staff share one rate-limit bucket.

An existing host created `private` with an automatic subnet. `deploy.sh` runs `docker compose up -d` without `down`, and an existing network is not re-addressed by a normal `up`. So each existing host needs this once, before the first deploy that includes the change.

1. **Check that the range is free on the host.** Both commands must show no overlap with `10.218.10.0/24`:
   ```bash
   docker network ls -q | xargs docker network inspect --format '{{.Name}}: {{range .IPAM.Config}}{{.Subnet}} {{end}}'
   ip -4 route
   ```
   If it overlaps, pick another private `/24` and set it in `DevOps/.env.hostinger`. Set both variables to the same value:
   ```bash
   PMS_PRIVATE_SUBNET=10.218.240.0/24
   PMS_TRUSTED_PROXY_CIDRS=10.218.240.0/24
   ```

2. **Stop the stack once.** This removes the containers and the networks. It causes downtime.
   ```bash
   docker compose --env-file DevOps/.env.hostinger -f compose.production.yml down
   ```
   Do **not** add `-v`. That deletes the named volumes, including `backend_data`, `redis_data` and `caddy_data`.

3. **Deploy as usual:**
   ```bash
   DevOps/scripts/deploy.sh
   ```

4. **Verify the gateway is inside the trusted range.** The first command shows the network's subnet. The second shows the gateway's address on it. The address must fall inside the subnet.
   ```bash
   docker network inspect pms-dashboard_private --format '{{range .IPAM.Config}}{{.Subnet}}{{end}}'
   docker inspect -f '{{range $name, $net := .NetworksSettings.Networks}}{{$name}} {{$net.IPAddress}}{{"\n"}}{{end}}' "$(docker compose --env-file DevOps/.env.hostinger -f compose.production.yml ps -q gateway)"
   ```

**Failure mode.** If `PMS_TRUSTED_PROXY_CIDRS` is empty, or does not contain the gateway's address, the backend ignores the forwarded client address. Every request then appears to come from the gateway. A sign of this is a 429 flood for many users at once, with the same hashed `subject=` in the warnings. Fix the value, then redeploy.

---

## 4. Backups and Logging Maintenance
- Use Supabase managed backups as the primary database recovery mechanism and verify restore procedures in staging.
- Logger rotated trace files reside under the backend's `/app/logs/` directories inside the container.
