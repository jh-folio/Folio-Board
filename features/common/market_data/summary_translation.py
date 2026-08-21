"""회사 소개 원문(영문)의 한국어 번역. LLM이 있을 때만, 원문당 1회만.

번역은 사실 생성을 하지 않는 순수 변환이라 LLM 사용이 §5 원칙과 충돌하지 않는다.
다만 세 가지 경계를 지킨다:

- **키가 없으면 원문 그대로 둔다.** LLM 없이도 앱은 동작해야 하고, Agent CLI 경로는
  한 번에 수십 초라 모달을 여는 자리에 넣을 수 없다 — CLI 모드도 원문으로 둔다.
- **원문 해시로 캐시한다.** provider 캐시(하루 주기 갱신)에 묶으면 갱신마다 같은
  문단을 다시 번역해 토큰을 버린다. 소개문은 사실상 바뀌지 않으므로 해시가 맞으면
  영원히 재사용한다.
- **실패는 원문이다.** 번역이 안 됐다고 소개가 사라지면 안 된다.
"""
from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

from features.common.atomic_replace import write_bytes_atomic

_CACHE_LOCK = threading.Lock()
_PROMPT = (
    "다음 영문 기업 소개를 자연스러운 한국어로 번역하세요. "
    "사실을 더하거나 빼지 말고, 회사명과 제품명은 원문 표기를 유지하세요. "
    "번역문만 출력하세요."
)


def _cache_path(data_dir: Path) -> Path:
    return Path(data_dir) / "provider-cache" / "summary-translations.json"


def _read_cache(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:  # noqa: BLE001 - 캐시가 깨졌으면 새로 시작한다
        return {}


def translated_summary(data_dir: Path, text: str) -> str:
    original = str(text or "").strip()
    if not original:
        return ""
    key = hashlib.sha256(original.encode("utf-8")).hexdigest()
    path = _cache_path(data_dir)
    with _CACHE_LOCK:
        cache = _read_cache(path)
        cached = cache.get(key)
        if isinstance(cached, str) and cached.strip():
            return cached

    from features.llm_settings.client import LlmRequestError, request_llm_text, selected_llm_config

    cfg = selected_llm_config()
    if not cfg.get("enabled") or not cfg.get("apiKey"):
        return original
    try:
        translated = str(request_llm_text(cfg, _PROMPT, original, max_output_tokens=1200) or "").strip()
    except (LlmRequestError, Exception):  # noqa: BLE001 - 번역 실패는 원문이다
        return original
    # 모델이 번역 대신 사과문이나 빈 답을 내면 원문을 지킨다. 한국어가 실제로
    # 들어 있는지가 가장 값싼 검증이다.
    if not translated or not any("가" <= ch <= "힣" for ch in translated):
        return original
    with _CACHE_LOCK:
        cache = _read_cache(path)
        cache[key] = translated
        path.parent.mkdir(parents=True, exist_ok=True)
        write_bytes_atomic(path, json.dumps(cache, ensure_ascii=False, indent=1).encode("utf-8"))
    return translated
