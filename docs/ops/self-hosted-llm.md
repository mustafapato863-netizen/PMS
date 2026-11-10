# Self-hosted PMS model

The chat brain is the Qwen3-4B server already running on the Hostinger KVM. PMS still computes every score. The model classifies intent and, for two narrow answers, phrases numbers PMS already calculated. A timeout, HTTP error, bad JSON, or a failed numeric check falls back to the rules engine.

## Earlier standalone container

Recorded before the Dokploy cutover. The live runtime is [Production runtime and rollback](#production-runtime-and-rollback). Do not use container `pms-qwen-pilot` (`f79fff9784c2`) as a rollback target.

| Item | Value |
|---|---|
| Container | `pms-qwen-pilot` (standalone `docker run`, not Dokploy) |
| Image | `ghcr.io/ggml-org/llama.cpp` build b12199, process `/app/llama-server` |
| Model file | `/models/Qwen3-4B-Q4_K_M.gguf` |
| Alias | `qwen3-4b-q4_k_m` |
| Inside the container | `0.0.0.0:8080` |
| On the host | `127.0.0.1:18080` only. Ports 11434 and 18080 are not public. |
| Args | `--host 0.0.0.0 --port 8080 --ctx-size 2048 --parallel 1 --threads 1 --n-gpu-layers 0` |
| Limits | 1 CPU, about 3.5 GB RAM |
| Network | default bridge only |

The PMS backend is the Dokploy project `performance-managment-system-backend-pwhfoc`. It is on `dokploy-network` and `performance-managment-system-backend-pwhfoc_default`. At that time it did not share a network with the standalone container, and no AI env was set. The box is a 2 vCPU / 8 GB host. Do not start a second copy of the model.

The context window is 2048 tokens. Requests cap `max_tokens`, send `chat_template_kwargs.enable_thinking=false`, append `/no_think`, and truncate the prompt to fit. `<think>` blocks are stripped before JSON parsing. One completion runs at a time. Routing waits up to 15 seconds and synthesis up to 30 seconds.

## Dokploy environment

Set these on the backend application `performance-managment-system-backend-pwhfoc`. No secret is required. `PMS_AI_LLM_API_KEY` stays empty.

```text
PMS_AI_LLM_BASE_URL=http://pms-qwen-pilot:8080
PMS_AI_LLM_MODEL=qwen3-4b-q4_k_m
PMS_AI_LLM_API_KEY=
PMS_AI_LLM_ALLOWED_HOSTS=localhost,127.0.0.1,::1,llm,pms-qwen-pilot,host.docker.internal
PMS_AI_LLM_INTENT_ENABLED=false
PMS_AI_LLM_SYNTHESIS_ENABLED=false
PMS_AI_LLM_EXPLORATION_ENABLED=false
PMS_AI_LLM_TIMEOUT_SECONDS=15
PMS_AI_LLM_SYNTHESIS_TIMEOUT_SECONDS=30
PMS_AI_LLM_MAX_CALLS_PER_TURN=3
PMS_AI_LLM_CONTEXT=2048
PMS_RATE_LIMIT_AI_CHAT_PER_MINUTE=20
```

`PMS_AI_LLM_BASE_URL` may be the origin (`http://pms-qwen-pilot:8080`) or the `/v1` base. The client calls `POST /v1/chat/completions`. `PMS_AI_LOCAL_ROUTER_URL` is still accepted when the base URL is unset, and must be the full chat URL.

Checked-in Compose files, env examples, and the Hostinger workflow default intent and synthesis to false. Turning either flag on is a separate pilot step. It does not start a model: the `llm` Compose profile stays opt-in, and the product switch `ai_enabled` stays off until an administrator enables it. Exploration stays off while `APP_ENV=production`, even if its flag is true.

## Option A — attach the existing container

This applied while the standalone container was the only model process. Use [Production runtime and rollback](#production-runtime-and-rollback). Do not start `pms-qwen-pilot` again. The steps below are retired.

```bash
docker network connect dokploy-network pms-qwen-pilot
```

Then set `PMS_AI_LLM_BASE_URL=http://pms-qwen-pilot:8080` and redeploy the backend. From inside the backend container:

```bash
python -c "import urllib.request; print(urllib.request.urlopen('http://pms-qwen-pilot:8080/health', timeout=5).status)"
```

`127.0.0.1:18080` from inside the backend container is not the model. That address is the container's own loopback.

## Option B — Compose service `llm`

`compose.production.yml` and `docker-compose.yml` define a profile-gated service named `llm`. A normal deploy does not start it. Leave it stopped while `pms-qwen-pilot-dkp` is the live model. See [Production runtime and rollback](#production-runtime-and-rollback). The service uses the same image family, alias, context, and a read-only mount of `/opt/pms-qwen-pilot/models`. The commands below are the old opt-in path. Running them starts another model process.

```bash
docker stop pms-qwen-pilot
docker compose -f compose.production.yml --profile llm up -d llm
```

Point the backend at the service name:

```text
PMS_AI_LLM_BASE_URL=http://llm:8080
```

`llm` is on the default allowlist. Limits default to 1 CPU and 3584 MB.

## Host port, if the networks stay separate

The backend container has `extra_hosts: host.docker.internal:host-gateway`. The existing publish is `127.0.0.1:18080` on the VPS, which forwards to container port 8080. This reaches the model without `docker network connect` and without a second process:

```text
PMS_AI_LLM_BASE_URL=http://host.docker.internal:18080
```

Prefer the Dokploy runtime in [Production runtime and rollback](#production-runtime-and-rollback). It keeps model traffic on `dokploy-network`.

## Production runtime and rollback

Recorded 2026-11-10 by DevOps. This is the live model. Recreate this runtime for a model rollback. The old standalone container `pms-qwen-pilot` (`f79fff9784c2`) is no longer a reliable rollback target. Do not rely on it.

The model is a separate Dokploy raw compose named `Qwen Pilot`, in project `Performance Managment System`. It is separate from the profile-gated `llm` service in the checked-in Compose files. The backend reaches it at `http://pms-qwen-pilot:8080` (`PMS_AI_LLM_BASE_URL`).

| Item | Value |
|---|---|
| Dokploy compose | `Qwen Pilot` (`composeId` `aC0KZzpfyvArSB6EHqd9h`) |
| Dokploy app | `pms-qwen-pilot-dkp-jmiwz1` |
| Container | `pms-qwen-pilot-dkp` on `dokploy-network` |
| Network alias | `pms-qwen-pilot` |
| Image | `ghcr.io/ggml-org/llama.cpp@sha256:0d64368a9835b2edd38a96324b1130fa756a48452bd65cdee1d33e2b267ca5b8` |
| Process | `llama-server`, CPU build, `/app/llama-server` |
| Mount | host `/opt/pms-qwen-pilot/models` to `/models`, read-only |
| Model file | `/models/Qwen3-4B-Q4_K_M.gguf` |
| Alias | `qwen3-4b-q4_k_m` |
| User | `65534` |
| Root filesystem | read-only |
| `/tmp` | tmpfs, 32m |
| Privileges | `no-new-privileges` |
| Memory | `3489660928` bytes (~3.25 GiB) |
| CPUs | 1 |
| Restart | `no` |
| Publish | `127.0.0.1:18080` to `8080` only. Keep this port off the public internet. |
| Healthcheck | `GET /health` |

TODO: record the sha256 of the model file. It was not captured on 2026-11-10 and needs a host shell: `sha256sum /opt/pms-qwen-pilot/models/Qwen3-4B-Q4_K_M.gguf`.

Args:

```text
--host 0.0.0.0 --port 8080 -m /models/Qwen3-4B-Q4_K_M.gguf --alias qwen3-4b-q4_k_m --ctx-size 2048 --parallel 1 --threads 2 --threads-batch 1 --batch-size 256 --ubatch-size 128 --n-gpu-layers 0 --reasoning-budget 0 --no-webui
```

The CPU limit versus `--threads` is being benchmarked. The container is limited to 1 CPU and currently starts with `--threads 2`. Keep `--threads` less than or equal to the CPU limit. Update this section after the benchmark.

### Example compose

Redeploying the Dokploy `Qwen Pilot` compose is the usual path. This snippet recreates the same service: the image is pinned by digest, `dokploy-network` is external, and the alias is `pms-qwen-pilot`. Healthcheck intervals were not recorded; the check is `GET /health`.

```yaml
services:
  qwen-pilot:
    image: ghcr.io/ggml-org/llama.cpp@sha256:0d64368a9835b2edd38a96324b1130fa756a48452bd65cdee1d33e2b267ca5b8
    container_name: pms-qwen-pilot-dkp
    entrypoint: ["/app/llama-server"]
    user: "65534"
    read_only: true
    restart: "no"
    command:
      - --host
      - 0.0.0.0
      - --port
      - "8080"
      - -m
      - /models/Qwen3-4B-Q4_K_M.gguf
      - --alias
      - qwen3-4b-q4_k_m
      - --ctx-size
      - "2048"
      - --parallel
      - "1"
      - --threads
      - "2"
      - --threads-batch
      - "1"
      - --batch-size
      - "256"
      - --ubatch-size
      - "128"
      - --n-gpu-layers
      - "0"
      - --reasoning-budget
      - "0"
      - --no-webui
    volumes:
      - type: bind
        source: /opt/pms-qwen-pilot/models
        target: /models
        read_only: true
    tmpfs:
      - /tmp:size=32m
    security_opt:
      - no-new-privileges:true
    mem_limit: "3489660928"
    cpus: "1"
    ports:
      - "127.0.0.1:18080:8080"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://127.0.0.1:8080/health"]
    networks:
      dokploy-network:
        aliases:
          - pms-qwen-pilot

networks:
  dokploy-network:
    external: true
```

### Recreate and rollback

The host is a Hostinger KVM 2 with 2 vCPU and 8 GB RAM. Run one model container. Stop the current one before starting another.

1. Stop the running model container first. That is `pms-qwen-pilot-dkp`. Also stop `pms-qwen-pilot` if it was started again. Leave the host with no model process before the next step.

```bash
docker stop pms-qwen-pilot-dkp
```

2. Redeploy the Dokploy `Qwen Pilot` compose, or recreate the container from the snippet above.

3. From the backend container (it is on `dokploy-network`), check `/health` and `/v1/models`, then the backend `/api/health`. `/health` should return 200. `/v1/models` should list the alias `qwen3-4b-q4_k_m`.

```bash
python -c "import urllib.request; print(urllib.request.urlopen('http://pms-qwen-pilot:8080/health', timeout=5).status)"
python -c "import urllib.request; print(urllib.request.urlopen('http://pms-qwen-pilot:8080/v1/models', timeout=5).read())"
python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:7860/api/health', timeout=5).status)"
```

4. App-level rollback does not depend on the model container. Set `PMS_AI_LLM_INTENT_ENABLED`, `PMS_AI_LLM_SYNTHESIS_ENABLED`, and `PMS_AI_LLM_EXPLORATION_ENABLED` to `false`, and/or turn the product switch `ai_enabled` off. The backend falls back to the rules engine.
