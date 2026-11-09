# Self-hosted PMS model

The chat brain is the Qwen3-4B server already running on the Hostinger KVM. PMS still computes every score. The model classifies intent and, for two narrow answers, phrases numbers PMS already calculated. A timeout, HTTP error, bad JSON, or a failed numeric check falls back to the rules engine.

## What is running today

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

The PMS backend is the Dokploy project `performance-managment-system-backend-pwhfoc`. It is on `dokploy-network` and `performance-managment-system-backend-pwhfoc_default`. It does not share a network with `pms-qwen-pilot`, and no AI env is set yet. The box is using about 6 of 8 GB, so do not start a second copy of the model.

The context window is 2048 tokens. Requests cap `max_tokens`, send `chat_template_kwargs.enable_thinking=false`, append `/no_think`, and truncate the prompt to fit. `<think>` blocks are stripped before JSON parsing. One completion runs at a time. Routing waits up to 15 seconds and synthesis up to 30 seconds.

## Dokploy environment

Set these on the backend application `performance-managment-system-backend-pwhfoc`. No secret is required. `PMS_AI_LLM_API_KEY` stays empty.

```text
PMS_AI_LLM_BASE_URL=http://pms-qwen-pilot:8080
PMS_AI_LLM_MODEL=qwen3-4b-q4_k_m
PMS_AI_LLM_API_KEY=
PMS_AI_LLM_ALLOWED_HOSTS=localhost,127.0.0.1,::1,llm,pms-qwen-pilot,host.docker.internal
PMS_AI_LLM_INTENT_ENABLED=true
PMS_AI_LLM_SYNTHESIS_ENABLED=true
PMS_AI_LLM_EXPLORATION_ENABLED=false
PMS_AI_LLM_TIMEOUT_SECONDS=15
PMS_AI_LLM_SYNTHESIS_TIMEOUT_SECONDS=30
PMS_AI_LLM_MAX_CALLS_PER_TURN=3
PMS_AI_LLM_CONTEXT=2048
PMS_RATE_LIMIT_AI_CHAT_PER_MINUTE=20
```

`PMS_AI_LLM_BASE_URL` may be the origin (`http://pms-qwen-pilot:8080`) or the `/v1` base. The client calls `POST /v1/chat/completions`. `PMS_AI_LOCAL_ROUTER_URL` is still accepted when the base URL is unset, and must be the full chat URL.

Exploration stays off while `APP_ENV=production`. Intent routing and validated synthesis are the production paths. Turn the Settings switch `ai_enabled` on only after a chat reports `provider_used=llama_cpp` and `model_used=qwen3-4b-q4_k_m`.

## Option A — attach the existing container

This is the right option on this box. It reuses `pms-qwen-pilot` and does not load the weights twice.

```bash
docker network connect dokploy-network pms-qwen-pilot
```

Then set `PMS_AI_LLM_BASE_URL=http://pms-qwen-pilot:8080` and redeploy the backend. From inside the backend container:

```bash
python -c "import urllib.request; print(urllib.request.urlopen('http://pms-qwen-pilot:8080/health', timeout=5).status)"
```

`127.0.0.1:18080` from inside the backend container is not the model. That address is the container's own loopback.

## Option B — Compose service `llm`

`compose.production.yml` and `docker-compose.yml` define a profile-gated service named `llm`. A normal deploy does not start it. Use it only if `pms-qwen-pilot` is stopped first. The service uses the same image family, alias, context, thread count, and a read-only mount of `/opt/pms-qwen-pilot/models`.

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

Prefer option A. It keeps model traffic on `dokploy-network` and does not depend on the host publish.
