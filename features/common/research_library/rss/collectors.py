"""Collector adapters for Folio Board Evidence Intake."""
from __future__ import annotations

import json
from pathlib import Path


def _strip_quotes(value: str) -> str:
    text = str(value or "").strip()
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        return text[1:-1]
    return text


def _parse_scalar(value: str):
    text = _strip_quotes(value)
    low = text.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in {"null", "none"}:
        return None
    if text.startswith("[") and text.endswith("]"):
        try:
            return json.loads(text)
        except Exception:
            return [x.strip().strip("\"'") for x in text[1:-1].split(",") if x.strip()]
    try:
        return int(text)
    except ValueError:
        return text


def load_simple_yaml(path: str | Path) -> dict:
    config_path = Path(path)
    if not config_path.exists():
        return {}
    text = config_path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        pass
    data: dict = {}
    stack: list[tuple[int, object]] = [(-1, data)]
    last_key_at_indent: dict[int, str] = {}
    for raw in text.splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        stripped = raw.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if stripped.startswith("- "):
            rest = stripped[2:].strip()
            if not isinstance(parent, list):
                key = last_key_at_indent.get(indent - 2)
                grand = stack[-2][1] if len(stack) >= 2 else data
                if isinstance(grand, dict) and key:
                    parent = []
                    grand[key] = parent
                    stack[-1] = (stack[-1][0], parent)
            item: dict = {}
            if isinstance(parent, list):
                parent.append(item)
            if rest and ":" in rest:
                key, value = rest.split(":", 1)
                item[key.strip()] = _parse_scalar(value)
            stack.append((indent, item))
            continue
        if ":" in stripped and isinstance(parent, dict):
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value:
                parent[key] = _parse_scalar(value)
            else:
                parent[key] = {}
                last_key_at_indent[indent] = key
                stack.append((indent, parent[key]))
    return data


def collect_official_items(config: dict) -> tuple[list[dict], dict]:
    """Adapter placeholder for existing official-data modules.

    Phase 5 intentionally avoids fake official evidence. Existing SEC/OpenDART
    or macro providers can plug into this function later and return normalized
    EvidenceItems with ``source_type=official_filing|macro_data``.
    """
    official = config.get("official_sources") if isinstance(config, dict) else {}
    enabled = {
        key: value
        for key, value in (official or {}).items()
        if isinstance(value, dict) and value.get("enabled", True)
    }
    return [], {
        "enabled_sources": sorted(enabled),
        "items": 0,
        "warning": "official collector adapter stub only; no fake official data generated",
    }
