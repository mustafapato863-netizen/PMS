"""Run the Phase 5 synthetic smoke test or exposed replay with one Cloudflare model."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from scripts import run_phase5_postfix_validation_v2 as v2
from services.ai import provider_engine

contract = v2.contract_v1
evaluator = contract.evaluator
MODELS = {
    "glm": "@cf/zai-org/glm-4.7-flash",
    "granite": "@cf/ibm-granite/granite-4.0-h-micro",
}
TIMEOUT_SECONDS = 30
OUTPUT_CAP_FIELDS = frozenset({"max_tokens", "max_completion_tokens", "maxOutputTokens"})
DEADLINE_SAMPLE = "ai_phase5_deadline_sample_v1.json"


def _load_deadline_sample(*, full_replay: bool = False) -> tuple[dict, dict]:
    directory = BACKEND / "tests" / "fixtures"
    sample_path = directory / DEADLINE_SAMPLE
    sample = json.loads(sample_path.read_bytes())
    corrections_path = directory / sample["expectations"]
    corrections = json.loads(corrections_path.read_bytes())
    source_path = directory / corrections["base_fixture"]
    if v2._sha256_file(source_path) != corrections["base_fixture_sha256"]:
        raise ValueError("The frozen base fixture hash does not match")
    old_result_path = BACKEND / "scripts" / sample["previous_result"]
    old_manifest = json.loads(old_result_path.with_suffix(".manifest.json").read_bytes())
    if v2._sha256_file(old_result_path) != old_manifest["result_sha256"]:
        raise ValueError("The previous replay hash does not match")
    old_result = json.loads(old_result_path.read_bytes())
    old_timeouts = {
        row["turn_id"] for row in old_result["results"]
        if any(attempt["status"] == "timeout" for call in row["provider_stages"] for attempt in call["attempts"])
    }
    source = json.loads(source_path.read_bytes())
    conversations = {c["turns"][0]["id"]: c for c in source["conversations"]}
    selected = []
    prefixes = (
        [[turn["id"] for turn in convo["turns"]] for convo in source["conversations"]]
        if full_replay else sample["turn_prefixes"]
    )
    for prefix in prefixes:
        convo = conversations[prefix[0]].copy()
        turns = convo["turns"][:len(prefix)]
        if [turn["id"] for turn in turns] != prefix:
            raise ValueError("The sample must replay a full conversation prefix")
        for turn in turns:
            correction = corrections["corrections"].get(turn["id"], {})
            for field in (*correction.get("remove", []), *correction.get("live_remove", [])):
                turn.pop(field, None)
            turn.update(correction.get("replace", {}))
        convo["turns"] = turns
        selected.append(convo)
    ids = [turn["id"] for convo in selected for turn in convo["turns"]]
    if not full_replay and set(ids) & old_timeouts != set(sample["previous_timeout_turns"]):
        raise ValueError("The selected turns do not match the declared previous timeouts")
    source.pop("freeze_manifest")
    source["conversations"] = selected
    if not full_replay:
        source["coverage"] = {}
    source["freeze_requirements"].update(min_conversations=len(selected), min_prompts=len(ids))
    metadata = {
        **sample,
        "turn_prefixes": prefixes,
        "full_replay": full_replay,
        "sample_sha256": v2._sha256_file(sample_path),
        "expectations_sha256": v2._sha256_file(corrections_path),
    }
    return source, metadata


def run(model_key: str, kind: str, version: int, *, deadline_seconds: int = TIMEOUT_SECONDS) -> dict:
    sample, sample_metadata = (
        _load_deadline_sample(full_replay=kind == "corrected")
        if kind in ("deadline", "corrected") else (None, None)
    )
    if sample_metadata:
        if MODELS[model_key] != sample_metadata["model"] or deadline_seconds not in sample_metadata["deadline_seconds"]:
            raise ValueError("Use the model and one of the deadlines declared by the sample")
        name = f"phase5_{kind}_{model_key}_{deadline_seconds}s_v1_r{version}"
    elif deadline_seconds != TIMEOUT_SECONDS:
        raise ValueError("A custom deadline requires the prespecified sample")
    else:
        name = f"phase5_{kind}_{model_key}_v3_r{version}"
    path = BACKEND / "scripts" / f"{name}.json"
    manifest_path = path.with_suffix(".manifest.json")
    if path.exists() or manifest_path.exists():
        raise FileExistsError(name)
    fixture_hash, freeze_hash, reference_hash = v2._verify_inputs()
    application_hash = contract._application_source_sha256()
    model = MODELS[model_key]
    evaluator.load_project_environment(str(BACKEND))
    with evaluator.MonkeyPatch.context() as patch:
        for key, value in {
            "PMS_AI_PRIMARY_PROVIDER": "cloudflare",
            "PMS_AI_CLOUDFLARE_ENABLED": "true",
            "PMS_AI_FALLBACK_ENABLED": "false",
            "PMS_AI_MAX_RETRIES": "0",
            "PMS_AI_PROVIDER_TIMEOUT_SECONDS": str(deadline_seconds),
            "CLOUDFLARE_AI_MODEL": model,
            "CLOUDFLARE_AI_MODEL_ALTER": model,
        }.items():
            patch.setenv(key, value)
        patch.setattr(provider_engine, "_default_engine", None)
        engine = provider_engine.get_unified_provider_engine()
        if sample_metadata:
            # Scope the experiment to this runner. Runtime config deliberately caps its default at 30s.
            patch.setattr(engine, "config", replace(engine.config, timeout_seconds=deadline_seconds))
        if not (engine.config.cloudflare_account_id and engine.config.cloudflare_api_token):
            raise RuntimeError("Cloudflare credentials are unavailable")
        generate = engine.generate
        read = provider_engine._read_with_deadline
        execute_http = engine.cloudflare_adapter._http_client
        run_chat_turn = evaluator.PmsAiOrchestrator.run_chat_turn
        wire_requests = []
        wire_models = []
        calls = []
        calls_by_turn = []

        def capture_http_request(request, *, timeout):
            payload = json.loads(request.data)
            wire_requests.append({
                "model": payload.get("model"),
                "body_keys": sorted(payload),
                "output_cap_fields": sorted(OUTPUT_CAP_FIELDS.intersection(payload)),
                "thinking_enabled": (payload.get("chat_template_kwargs") or {}).get("enable_thinking"),
                "response_format": (payload.get("response_format") or {}).get("type"),
                "timeout_seconds": timeout,
            })
            return execute_http(request, timeout=timeout)

        def read_metadata(response, *args, **kwargs):
            raw = read(response, *args, **kwargs)
            try:
                envelope = json.loads(raw)
                if isinstance(envelope, dict):
                    choices = envelope.get("choices") or []
                    choice = choices[0] if choices and isinstance(choices[0], dict) else {}
                    message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
                    usage = envelope.get("usage") if isinstance(envelope.get("usage"), dict) else {}
                    details = usage.get("completion_tokens_details")
                    wire_models.append({
                        "http_status": getattr(response, "status", None),
                        "reported_model": envelope.get("model"),
                        "finish_reason": choice.get("finish_reason"),
                        "completion_tokens": usage.get("completion_tokens"),
                        "reasoning_tokens": details.get("reasoning_tokens") if isinstance(details, dict) else None,
                        "has_reasoning_content": bool(message.get("reasoning_content") or message.get("reasoning")),
                    })
            except (ValueError, TypeError):
                pass
            return raw

        def capture_call(request):
            start = len(wire_models)
            start_requests = len(wire_requests)
            if sample_metadata and request.purpose in provider_engine.MODEL_LED_REQUEST_PURPOSES:
                request = replace(request, timeout_seconds=deadline_seconds)
            result = generate(request)
            calls.append({
                "stage": request.purpose,
                "max_tokens": request.max_tokens,
                "provider": result.provider,
                "engine_model": result.model,
                "outcome": result.outcome,
                "latency_ms": result.latency_ms,
                "usage": result.usage.to_dict(),
                "estimated_cost_usd": result.estimated_cost_usd,
                "error": provider_engine.redact_secrets(result.error_detail or "") or None,
                "attempts": [attempt.to_dict() for attempt in result.attempts],
                "http_requests": wire_requests[start_requests:],
                "http_responses": wire_models[start:],
            })
            return result

        def capture_turn(orchestrator, request):
            start = len(calls)
            result = run_chat_turn(orchestrator, request)
            calls_by_turn.append(calls[start:])
            if kind == "exposed" and len(calls_by_turn) % 10 == 0:
                print(f"{model_key}: {len(calls_by_turn)}/80 turns", file=sys.stderr, flush=True)
            elif sample_metadata:
                print(f"{deadline_seconds}s: {len(calls_by_turn)} sample turns", file=sys.stderr, flush=True)
            return result

        patch.setattr(provider_engine, "_read_with_deadline", read_metadata)
        patch.setattr(engine.cloudflare_adapter, "_http_client", capture_http_request)
        patch.setattr(engine, "generate", capture_call)
        patch.setattr(evaluator.PmsAiOrchestrator, "run_chat_turn", capture_turn)
        if kind == "smoke":
            for key, value in {
                "PMS_AI_INTENT_ENABLED": "true",
                "PMS_AI_SYNTHESIS_ENABLED": "true",
                "PMS_AI_GEMINI_ROUTING_ENABLED": "false",
                "PMS_AI_MODEL_LED_PILOT_ENABLED": "true",
                "PMS_AI_ROUTER_MODE": "hybrid",
            }.items():
                patch.setenv(key, value)
            db = evaluator._build_in_memory_db()
            try:
                evaluator._patch_records(patch, evaluator._build_eval_records())
                evaluator.ai_evidence_cache.clear()
                orchestrator = evaluator.PmsAiOrchestrator(
                    db, {"role": "Admin", "user_id": "phase5-smoke", "has_unrestricted_team_access": True},
                )
                response = orchestrator.run_chat_turn(evaluator.AiChatRequest(
                    prompt="What was Nadia Fadel's Waiting Time in September 2026?",
                ))
            finally:
                db.close()
                evaluator.ai_evidence_cache.clear()
            result = {"results": [{
                "outcome": response.outcome,
                "answer_source": response.answer_source,
                "answer_provider": response.provider_used,
                "answer_model": response.model_used,
                "fallback_outcome": getattr(response.provider_usage, "fallback_outcome", None),
                "headline": response.headline,
            }]}
        else:
            contract._AUDIT.clear()
            patch.setattr(evaluator, "validate_turn_response", contract._validate_turn)
            patch.setattr(evaluator, "validate_critical_evidence", contract._validate_critical)
            if sample is None:
                result = evaluator.evaluate_unseen_dataset(mode="live", fixture_name=contract.POSTFIX_FIXTURE_NAME)
                if (result["conversation_count"], result["prompt_count"]) != (20, 80):
                    raise ValueError("Expected 20 conversations and 80 turns")
            else:
                with TemporaryDirectory(prefix="pms-phase5-deadline-") as temp:
                    directory = Path(temp) / "fixtures"
                    directory.mkdir()
                    (directory / DEADLINE_SAMPLE).write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
                    with evaluator.MonkeyPatch.context() as fixture_patch:
                        fixture_patch.setattr(evaluator, "TESTS_DIR", Path(temp))
                        result = evaluator.evaluate_unseen_dataset(mode="live", fixture_name=DEADLINE_SAMPLE)
            v2._prepare_result(result, v2._sha256_file(Path(__file__)), reference_hash, "live")
            if sample_metadata:
                result["run_bound"]["max_turns"] = sum(map(len, sample_metadata["turn_prefixes"]))
                result["experiment"] = sample_metadata

    for row, turn_calls in zip(result["results"], calls_by_turn, strict=True):
        row["provider_stages"] = turn_calls

    model_led_requests = [
        request for call in calls if call["stage"] in provider_engine.MODEL_LED_REQUEST_PURPOSES
        for request in call["http_requests"]
    ]
    if any(request["output_cap_fields"] or request["model"] != model for request in model_led_requests):
        raise RuntimeError("Unexpected model or output cap in the model-led retest transport")
    if sample_metadata and (
        not model_led_requests
        or any(request["thinking_enabled"] is not True or not deadline_seconds - 1 <= request["timeout_seconds"] <= deadline_seconds
               for request in model_led_requests)
    ):
        raise RuntimeError("Deadline or reasoning setting did not reach the experiment transport")

    exact_stages = Counter(
        call["stage"] for call in calls
        if call["outcome"] == "success" and call["provider"] == "cloudflare"
        and call["engine_model"] == model
        and any(
            response["reported_model"] == model and response["http_status"] == 200
            for response in call["http_responses"]
        )
    )
    estimate = [call["estimated_cost_usd"] for call in calls]
    telemetry = {
        "requested_model": model,
        "api_response_confirmed_stages": dict(exact_stages),
        "stage_outcomes": dict(Counter(f"{c['stage']}:{c['outcome']}" for c in calls)),
        "engine_calls": len(calls),
        "provider_attempts_by_status": dict(Counter(a["status"] for c in calls for a in c["attempts"])),
        "estimated_cost_usd_known_subtotal": sum(cost for cost in estimate if cost is not None),
        "engine_calls_without_cost_estimate": estimate.count(None),
        "actual_provider_cost_status": "unknown" if calls else "not_applicable",
        "application_fallbacks": dict(Counter(
            row["fallback_outcome"] for row in result["results"]
            if row.get("fallback_outcome") not in (None, "none")
        )),
        "answer_sources": dict(Counter(row.get("answer_source") for row in result["results"])),
    }
    result.update(run_id=name, telemetry=telemetry)
    if kind == "smoke":
        result["verified"] = bool(
            exact_stages["model_led_router"]
            and exact_stages["model_led_synthesis"]
            and result["results"][0]["answer_source"] == "model_synthesis"
            and result["results"][0]["outcome"] == "answer"
        )
    if application_hash != contract._application_source_sha256():
        raise RuntimeError("Application source changed during the evaluation")
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    manifest = {
        "run_id": name,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "requested_provider": "cloudflare",
        "timeout_seconds": deadline_seconds,
        "model_led_output_cap_omitted": bool(model_led_requests),
        "application_source_sha256": application_hash,
        "runner_sha256": v2._sha256_file(Path(__file__)),
        "v2_runner_sha256": v2._sha256_file(Path(v2.__file__)),
        "validator_harness_sha256": v2._sha256_file(Path(contract.__file__)),
        "scoring_helper_sha256": v2._sha256_file(Path(contract.contract.__file__)),
        "reference_evaluator_sha256": reference_hash,
        "reference_fixture_sha256": fixture_hash,
        "reference_freeze_manifest_sha256": freeze_hash,
        "scoring_version": contract.CONTRACT_VERSION if kind != "smoke" else None,
        "experiment": sample_metadata,
        "evaluated_fixture_sha256": result.get("fixture_sha256"),
        "result_sha256": v2._sha256_file(path),
        "telemetry": telemetry,
    }
    with manifest_path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", choices=MODELS)
    parser.add_argument("kind", choices=("smoke", "exposed", "deadline", "corrected"))
    parser.add_argument("--revision", type=int, default=3)
    parser.add_argument("--deadline-seconds", type=int, choices=(30, 60), default=TIMEOUT_SECONDS)
    args = parser.parse_args()
    report = run(args.model, args.kind, args.revision, deadline_seconds=args.deadline_seconds)
    summary = {key: report[key] for key in ("run_id", "telemetry")}
    if args.kind == "smoke":
        summary.update(verified=report["verified"], results=report["results"])
    else:
        summary["gate"] = report["quality_gate"]
        summary["summary"] = {
            key: value for key, value in report["summary"]["overall"].items() if key != "failures"
        }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if args.kind == "smoke" and not report["verified"]:
        sys.exit(1)
