from __future__ import annotations

GENERATION_MODES = {"rules", "llm_cli"}

ALIASES = {
    "rule": "rules",
    "rules": "rules",
    "fallback": "rules",
    "off": "rules",
    "none": "rules",
    "agent": "llm_cli",
    "cli": "llm_cli",
    "llm_cli": "llm_cli",
}


def _boolish(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None


def normalize_generation_mode(value=None, *, use_llm=None, default="rules") -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    if text in {"api", "llm_api", "llm"}:
        raise ValueError("llm_api_removed: 설정에서 CLI로 전환해 주세요.")
    if text:
        normalized = ALIASES.get(text)
        if normalized:
            return normalized
        raise ValueError(f"Unsupported generation mode: {value}")
    legacy = _boolish(use_llm)
    if legacy is not None:
        return "llm_cli" if legacy else "rules"
    if str(default).lower().replace("-", "_") in {"api", "llm_api", "llm"}:
        raise ValueError("llm_api_removed")
    fallback = ALIASES.get(str(default or "rules").strip().lower().replace("-", "_"), "rules")
    return fallback


def llm_override_for_mode(mode: str) -> bool:
    normalized = normalize_generation_mode(mode)
    if normalized == "llm_cli":
        raise ValueError("llm_cli must be handled by the Agent Bridge")
    return False
