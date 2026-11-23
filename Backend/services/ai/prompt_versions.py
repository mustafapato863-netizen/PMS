"""Centralized canonical prompt version identifiers for PMS AI runtime prompts."""

from __future__ import annotations

MODEL_LED_PLANNER_PROMPT_VERSION = "model-led-planner-v4"
MODEL_LED_SYNTHESIS_PROMPT_VERSION = "model-led-synthesis-v2"
INTENT_CLASSIFIER_PROMPT_VERSION = "intent-classifier-v1"
NARROW_EVIDENCE_SYNTHESIS_PROMPT_VERSION = "narrow-evidence-synthesis-v1"
EXECUTIVE_VARIATION_PROMPT_VERSION = "executive-variation-v1"
EXPLAIN_PREVIOUS_PROMPT_VERSION = "explain-previous-v1"

ACTIVE_PROMPT_VERSIONS: dict[str, str] = {
    "model_led_planner": MODEL_LED_PLANNER_PROMPT_VERSION,
    "model_led_synthesis": MODEL_LED_SYNTHESIS_PROMPT_VERSION,
    "intent_classifier": INTENT_CLASSIFIER_PROMPT_VERSION,
    "narrow_evidence_synthesis": NARROW_EVIDENCE_SYNTHESIS_PROMPT_VERSION,
    "executive_variation": EXECUTIVE_VARIATION_PROMPT_VERSION,
    "explain_previous": EXPLAIN_PREVIOUS_PROMPT_VERSION,
}

__all__ = [
    "ACTIVE_PROMPT_VERSIONS",
    "EXECUTIVE_VARIATION_PROMPT_VERSION",
    "EXPLAIN_PREVIOUS_PROMPT_VERSION",
    "INTENT_CLASSIFIER_PROMPT_VERSION",
    "MODEL_LED_PLANNER_PROMPT_VERSION",
    "MODEL_LED_SYNTHESIS_PROMPT_VERSION",
    "NARROW_EVIDENCE_SYNTHESIS_PROMPT_VERSION",
]
