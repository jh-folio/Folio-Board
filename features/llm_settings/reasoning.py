"""Provider-native reasoning effort capabilities.

The UI and runtime must use the same transport values.  Display labels are
kept provider-specific so a label such as Codex ``Ultra`` cannot accidentally
be sent as an unsupported value or silently downgraded to another level.
"""
from __future__ import annotations

from typing import Any


REASONING_VALUES = (
    "provider_default",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
    "ultra",
)

# Codex's current model catalog (client 0.153.4) reports these transport
# levels.  The model-specific table is deliberately conservative for models
# that are not in that catalog: an unknown model is limited to xhigh rather
# than being presented with an unverified Max/Ultra option.
CODEX_MODEL_REASONING_EFFORTS: dict[str, tuple[str, ...]] = {
    "gpt-6-astra": ("low", "medium", "high", "xhigh", "max", "ultra"),
    "gpt-5.6-sol": ("low", "medium", "high", "xhigh", "max", "ultra"),
    "gpt-5.6-terra": ("low", "medium", "high", "xhigh", "max", "ultra"),
    "gpt-5.6-luna": ("low", "medium", "high", "xhigh", "max"),
    "gpt-5.5": ("low", "medium", "high", "xhigh"),
    "gpt-5.4": ("low", "medium", "high", "xhigh"),
    "gpt-5.4-mini": ("low", "medium", "high", "xhigh"),
    "gpt-5.3-codex-spark": ("low", "medium", "high", "xhigh"),
}
CODEX_REASONING_FALLBACK = ("low", "medium", "high", "xhigh")
CLAUDE_REASONING_EFFORTS = ("low", "medium", "high", "xhigh", "max")
# Claude Code's effort flag is model-sensitive.  In particular, the 4.6
# Sonnet/Opus family accepts Low/Medium/High/Max but does not accept Extra
# High.  Keep this table explicit so a dynamically discovered 4.6 model does
# not inherit the newer model's option list by accident.
CLAUDE_MODEL_REASONING_EFFORTS: dict[str, tuple[str, ...]] = {
    "claude-opus-4-6": ("low", "medium", "high", "max"),
    "claude-sonnet-4-6": ("low", "medium", "high", "max"),
}
ANTIGRAVITY_REASONING_EFFORTS = ("low", "medium", "high")
# The local Responses transport currently accepts these explicit Astra
# values.  Other OpenAI API models, Gemini, and Claude API stay at the
# provider default until their API contract exposes a matching field.
OPENAI_API_REASONING_EFFORTS = ("low", "medium", "high", "xhigh", "max")

COMMON_LABELS = {
    "provider_default": "제공자 기본값",
    "low": "Low",
    "medium": "Medium",
    "high": "High",
    "xhigh": "Extra High",
    "max": "Max",
    "ultra": "Ultra",
}
CODEX_LABELS = {
    **COMMON_LABELS,
    "low": "Light",
}


def normalize_reasoning_effort(value: Any) -> str:
    """Normalize a persisted/request value to a transport enum."""
    effort = str(value or "").strip().lower().replace("-", "_")
    if effort in {"", "default", "providerdefault", "provider_default"}:
        return "provider_default"
    if effort not in REASONING_VALUES:
        raise ValueError("unsupported_reasoning_effort")
    return effort


def supported_reasoning_efforts(mode: str, provider: str, model: str = "") -> tuple[str, ...]:
    """Return explicit transport enums for one mode/provider/model tuple."""
    normalized_mode = str(mode or "").strip().lower().replace("-", "_")
    if normalized_mode in {"llm_api", "api"}:
        normalized_mode = "api"
    elif normalized_mode in {"llm_cli", "cli", "agent"}:
        normalized_mode = "cli"
    normalized_provider = str(provider or "").strip().lower()
    normalized_model = str(model or "").strip().lower()
    if normalized_mode == "api":
        if normalized_provider == "openai" and normalized_model == "gpt-6-astra":
            return OPENAI_API_REASONING_EFFORTS
        return ()
    if normalized_mode != "cli":
        return ()
    if normalized_provider == "codex":
        return CODEX_MODEL_REASONING_EFFORTS.get(normalized_model, CODEX_REASONING_FALLBACK)
    if normalized_provider == "claude":
        return CLAUDE_MODEL_REASONING_EFFORTS.get(normalized_model, CLAUDE_REASONING_EFFORTS)
    if normalized_provider == "antigravity":
        return ANTIGRAVITY_REASONING_EFFORTS
    return ()


def reasoning_choices(mode: str, provider: str, model: str = "") -> list[dict[str, str]]:
    """Return a UI-safe list with provider-native display labels."""
    levels = supported_reasoning_efforts(mode, provider, model)
    labels = CODEX_LABELS if str(provider or "").strip().lower() == "codex" and str(mode or "").strip().lower() in {"cli", "llm_cli", "agent"} else COMMON_LABELS
    return [
        {"value": "provider_default", "label": labels["provider_default"]},
        *[{"value": level, "label": labels[level]} for level in levels],
    ]


def is_supported_reasoning_effort(mode: str, provider: str, model: str, value: Any) -> bool:
    try:
        normalized = normalize_reasoning_effort(value)
    except ValueError:
        return False
    return normalized == "provider_default" or normalized in supported_reasoning_efforts(mode, provider, model)


def reasoning_label(mode: str, provider: str, value: Any) -> str:
    """Map a transport enum to the provider's visible name."""
    normalized = normalize_reasoning_effort(value)
    labels = CODEX_LABELS if str(provider or "").strip().lower() == "codex" and str(mode or "").strip().lower() in {"cli", "llm_cli", "agent"} else COMMON_LABELS
    return labels.get(normalized, normalized)


__all__ = [
    "ANTIGRAVITY_REASONING_EFFORTS",
    "CLAUDE_MODEL_REASONING_EFFORTS",
    "CLAUDE_REASONING_EFFORTS",
    "CODEX_MODEL_REASONING_EFFORTS",
    "CODEX_REASONING_FALLBACK",
    "COMMON_LABELS",
    "OPENAI_API_REASONING_EFFORTS",
    "REASONING_VALUES",
    "is_supported_reasoning_effort",
    "normalize_reasoning_effort",
    "reasoning_choices",
    "reasoning_label",
    "supported_reasoning_efforts",
]
