"""Deterministic price-scenario inputs; independent of personal hypotheses."""

METHOD_VERSION = "price-scenario-4"
SPEC_VERSION = "price-scenario-spec-4"
SPEC_SHA256 = "9e88a0ab26a66981e753bff3f834ff874a2dcfe00c2de3aed042c36692e88f1a"
SPEC_REVISION = 1
SPEC4_REVISION0_SHA256 = "67cea9237874e56cc5d86d1702b2f958dca0d536d312e5bbd9e15d6ba060d6aa"

# Earlier frozen versions stay readable. Their results are never rewritten.
SPEC3_METHOD_VERSION = "price-scenario-3"
SPEC3_SPEC_VERSION = "price-scenario-spec-3"
SPEC3_SHA256 = "13e9829dd9a0ad3fc248b2e6bac9f4cc31fcae58f0ea39910f4626c0160e031b"
SPEC2_METHOD_VERSION = "price-scenario-2"
SPEC2_SHA256 = "aab9d325ec3128e71cf4fec2e76f6dad6cbe87525cc52f16be272c86bb99571b"
LEGACY_METHOD_VERSION = "price-scenario-1"
LEGACY_SPEC_SHA256 = "4bd76facfade63e125b215b089a413f391641484abc6a493a05a57e528080659"


def method_at_least(version: str, minimum: int) -> bool:
    """Explicit numeric method lineage; an unrelated version never opens a calculation."""
    prefix = "price-scenario-"
    suffix = version.removeprefix(prefix) if isinstance(version, str) else ""
    return isinstance(version, str) and version.startswith(prefix) and suffix.isdigit() and int(suffix) >= minimum
