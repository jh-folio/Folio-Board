"""Deterministic price-scenario inputs; independent of personal hypotheses."""

METHOD_VERSION = "price-scenario-5"
SPEC_VERSION = "price-scenario-spec-5"
SPEC_SHA256 = "3015c60574c65a621d1ba90841540095b324858203631698003185eb90fb0184"
SPEC4_SHA256 = "083085f1425d2db29286c3b01fb59ce9b5a0356affd45420803cfe8d86f35773"
SPEC4_REVISION1_FUND_SOURCE_SHA256 = "b249c6dcffd1db4da41cb0ea891e8ea76860d16ccfd9cbbb3e1bb4f857cbc567"
SPEC4_REVISION1_INITIAL_SHA256 = "9e88a0ab26a66981e753bff3f834ff874a2dcfe00c2de3aed042c36692e88f1a"
SPEC_REVISION = 1
SPEC4_REVISION0_SHA256 = "67cea9237874e56cc5d86d1702b2f958dca0d536d312e5bbd9e15d6ba060d6aa"


def spec4_revision(inputs: dict) -> int | None:
    if inputs.get("methodVersion") != "price-scenario-4" or inputs.get("specVersion") != "price-scenario-spec-4":
        return None
    sha = inputs.get("specSha256")
    if sha in {None, SPEC4_REVISION0_SHA256}:
        return 0
    return 1 if sha in {SPEC4_SHA256, SPEC4_REVISION1_INITIAL_SHA256, SPEC4_REVISION1_FUND_SOURCE_SHA256} else None

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
    return isinstance(version, str) and version.startswith(prefix) and suffix.isdigit() and minimum <= int(suffix) <= 5


def known_spec(inputs: dict) -> bool:
    version = inputs.get("methodVersion")
    sha = inputs.get("specSha256")
    if version == METHOD_VERSION:
        return inputs.get("specVersion") == SPEC_VERSION and sha == SPEC_SHA256
    if version == "price-scenario-4":
        return spec4_revision(inputs) is not None
    return (version, inputs.get("specVersion"), sha) in {
        (SPEC3_METHOD_VERSION, SPEC3_SPEC_VERSION, SPEC3_SHA256),
        (SPEC2_METHOD_VERSION, "price-scenario-spec-2", SPEC2_SHA256),
        (LEGACY_METHOD_VERSION, "price-scenario-spec-1", LEGACY_SPEC_SHA256),
    }
