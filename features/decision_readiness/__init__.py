"""Personal comparison context, never an investment verdict or an evidence source."""

SCHEMA_VERSION = "decision-readiness-1"
METHOD_VERSION = "decision-readiness-rules-1"
SPEC_SHA256 = "fbe365ec2b855d4d997522efcf7ba622c55810c53c2bff704c0b2f0a61a87006"


class DecisionError(ValueError):
    def __init__(self, code: str, status: int = 422):
        self.code, self.status = code, status
        super().__init__(code)
