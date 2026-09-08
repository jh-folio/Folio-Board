"""Privacy-bounded screenshot preview orchestration.

**0.5.0에서는 이 모듈을 부르는 화면도 route도 없다.** 죽은 코드가 아니라 0.5.X를
위해 남겨 둔 것이다 — 사진 인식을 Agent 도크 하나로 옮기기로 했고(2026-08-07 사용자
결정), 그때 여기의 임시 파일 수명 관리·`validate_image` 가드·`import_preview`
정규화를 그대로 쓴다. 0.5.X가 정리할 것은 `local` 모드와 `local_ocr.py`다: 도크는
설정에 따라 CLI 아니면 API로 동작하므로 Tesseract가 설 자리가 없다.

지우기 전에 `plan/release/0.5_PLAN.md`의 해당 절을 먼저 본다.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from features.portfolio.agent_import import cli_status, extract_positions as extract_agent
from features.portfolio.import_schema import import_preview
from features.portfolio.local_ocr import extract_positions as extract_local, preprocess_image, tesseract_preflight, validate_image
from features.portfolio.vision_import import extract_positions as extract_vision

MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_MIME = {"image/png", "image/jpeg", "image/webp"}
MODES = ("local", "vision", "agent")


def preview_image(data_dir: Path, image_bytes: bytes, *, content_type: str, mode: str = "local", consent: bool = False) -> dict:
    if content_type not in ALLOWED_MIME:
        raise ValueError("portfolio_image_type_invalid")
    if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError("portfolio_image_size_invalid")
    suffix = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}[content_type]
    with tempfile.TemporaryDirectory(prefix="folio-portfolio-import-") as directory:
        source = Path(directory) / f"source{suffix}"
        processed = Path(directory) / "processed.png"
        source.write_bytes(image_bytes)
        validate_image(source, mime_type=content_type)
        if mode == "vision":
            rows = extract_vision(source, consent=consent, mime_type=content_type)
            engine = "external_vision"
            notices = ["선택한 crop만 외부 Vision provider에 전송했고 Folio Board에는 이미지를 보관하지 않았습니다."]
        elif mode == "agent":
            # 설정한 CLI가 파일을 직접 연다. 바이트는 프롬프트에 실리지 않고,
            # 이 with 블록이 끝나면 임시 파일도 사라진다.
            rows = extract_agent(source)
            engine = "agent_cli"
            notices = ["설정한 Agent CLI가 사진을 읽었습니다. 사진은 그 CLI 제공자에게 전달되며 Folio Board에는 보관하지 않았습니다."]
        else:
            preprocess_image(source, processed)
            rows, preflight = extract_local(processed)
            engine = "tesseract_local"
            notices = [] if preflight.get("ready") else [str(preflight.get("reason") or "tesseract_unavailable")]
        from features.portfolio.service import get_portfolio

        return import_preview(rows, get_portfolio(data_dir).get("positions") or [], engine=engine, notices=notices)


def preflight_payload() -> dict:
    """세 경로의 준비 상태를 함께 돌려준다.

    `ready`는 계속 로컬 OCR의 상태다(기존 호출자 계약). Agent CLI 여부는
    `agent.available`로 따로 싣는다 — 화면이 무엇을 고를 수 있는지 열기 전에
    알아야 방식을 골랐다가 막히는 일이 없다.

    못 쓰는 이유는 `agent.message`에 브리지 문장 그대로 싣는다. `CLI를 찾을 수
    없다`와 `로그인이 필요하다`는 사용자가 할 일이 다른데, 하나로 뭉뚱그리면
    설치된 CLI 앞에서 설치 안내를 읽게 된다.
    """
    return {
        **tesseract_preflight(),
        "autoInstall": False,
        "languagesRequired": ["kor", "eng"],
        "agent": cli_status(),
    }
