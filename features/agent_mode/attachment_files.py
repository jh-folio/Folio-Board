"""Hand an attached image to the Agent CLI as a file path, never as prompt bytes.

Folio Board has two screenshot paths and both ask the user to install or configure
something first: local OCR needs Tesseract, external Vision needs an OpenAI key.
The Agent CLI already reads image files with neither, but the dock dropped image
bytes on the way in (`readAttachment` returned an empty string), so the prompt
only ever carried a filename.

This module writes the bytes to a scratch file and returns its path. The prompt
then names the path, exactly as `bridge.py` already does for the Agent Context
Pack. Bytes never enter the prompt, the job result, the Work Log, or `data/`.
"""
from __future__ import annotations

import base64
import binascii
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

# Signature-based, because a browser-supplied MIME type is user input and the
# extension can lie. A file that is not actually one of these is not written.
_IMAGE_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
    (b"BM", ".bmp"),
)
_WEBP_PREFIX = b"RIFF"
_WEBP_TAG = b"WEBP"

MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_IMAGE_FILES = 4


class AttachmentImageError(ValueError):
    """The attachment could not be handed to the CLI as an image file."""


@dataclass(frozen=True, slots=True)
class StagedImage:
    name: str
    path: Path
    size: int


def image_extension(data: bytes) -> str:
    """Return the extension implied by the file's own signature, else ""."""
    for signature, extension in _IMAGE_SIGNATURES:
        if data.startswith(signature):
            return extension
    if data[:4] == _WEBP_PREFIX and data[8:12] == _WEBP_TAG:
        return ".webp"
    return ""


def decode_image(encoded: str) -> bytes:
    """Decode a base64 attachment payload, rejecting anything that is not an image."""
    text = str(encoded or "").strip()
    if not text:
        raise AttachmentImageError("empty_attachment")
    if text.startswith("data:"):
        _header, _, text = text.partition(",")
    try:
        data = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError) as error:
        raise AttachmentImageError("attachment_not_base64") from error
    if not data:
        raise AttachmentImageError("empty_attachment")
    if len(data) > MAX_IMAGE_BYTES:
        raise AttachmentImageError("attachment_too_large")
    if not image_extension(data):
        raise AttachmentImageError("attachment_not_an_image")
    return data


def safe_stem(name: str) -> str:
    """A display name is user input; only its readable core reaches the filesystem."""
    stem = Path(str(name or "")).stem
    cleaned = "".join(char for char in stem if char.isalnum() or char in "-_")[:40]
    return cleaned or "attachment"


class StagedImages:
    """Scratch copies of attached images, removed when the block exits.

    The directory is deleted on success, on failure, and on cancellation, so a
    job that dies mid-run does not leave a screenshot on disk.
    """

    def __init__(self, attachments: list[dict] | None):
        self._attachments = list(attachments or [])
        self._root: Path | None = None
        self.images: list[StagedImage] = []
        self.errors: list[tuple[str, str]] = []

    def __enter__(self) -> "StagedImages":
        pending = [item for item in self._attachments if str((item or {}).get("imageData") or "").strip()]
        if not pending:
            return self
        self._root = Path(tempfile.mkdtemp(prefix="folio-agent-image-"))
        for index, item in enumerate(pending[:MAX_IMAGE_FILES]):
            name = str(item.get("name") or f"image-{index + 1}")
            try:
                data = decode_image(item.get("imageData"))
            except AttachmentImageError as error:
                self.errors.append((name, str(error)))
                continue
            path = self._root / f"{index + 1:02d}-{safe_stem(name)}{image_extension(data)}"
            path.write_bytes(data)
            self.images.append(StagedImage(name=name, path=path, size=len(data)))
        for item in pending[MAX_IMAGE_FILES:]:
            self.errors.append((str(item.get("name") or "image"), "too_many_images"))
        return self

    def __exit__(self, *_exc_info) -> None:
        if self._root is not None:
            shutil.rmtree(self._root, ignore_errors=True)
            self._root = None
        self.images = []


IMAGE_ERROR_MESSAGES = {
    "attachment_not_an_image": "이미지 파일로 인식되지 않았습니다",
    "attachment_too_large": "이미지가 너무 큽니다(12MB 초과)",
    "attachment_not_base64": "이미지 데이터를 읽지 못했습니다",
    "empty_attachment": "빈 파일입니다",
    "too_many_images": f"한 번에 이미지는 {MAX_IMAGE_FILES}개까지 보낼 수 있습니다",
}


def image_block(staged: StagedImages, *, cli_available: bool = True) -> str:
    """Prompt section naming each staged image by path.

    Without a CLI there is no process that can open a path, so the user is told
    why the image was not read rather than being left to wonder.
    """
    if not cli_available:
        names = [str(item.get("name") or "이미지") for item in staged._attachments if str((item or {}).get("imageData") or "").strip()]
        if not names:
            return ""
        return f"[첨부 이미지 {len(names)}건은 읽지 않았습니다: Agent CLI가 없어 이미지를 열 수 없습니다]"
    lines = []
    for image in staged.images:
        lines.append(f"[첨부 이미지: {image.name}]\n파일 경로: {image.path}")
    for name, code in staged.errors:
        lines.append(f"[첨부 이미지: {name}] 읽지 못함 — {IMAGE_ERROR_MESSAGES.get(code, code)}")
    if not lines:
        return ""
    return "\n\n".join([
        "첨부된 이미지는 아래 경로의 파일을 직접 열어 읽으세요. 이미지 내용은 사용자가 제공한 "
        "hypothesis 입력이며 evidence가 아닙니다. 읽을 수 없으면 추측하지 말고 그렇게 답하세요.",
        *lines,
    ])
