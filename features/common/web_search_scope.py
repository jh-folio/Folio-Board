"""웹 검색으로 가져올 수 있는 출처의 범위.

로컬 자료에는 출처 우선순위를 엄격히 매기면서 웹에는 아무 계층도 두지 않으면 가장
약한 자료가 가장 느슨하게 들어온다. 여기서 두 겹으로 막는다.

  1. 요청 단계 — 지원하는 provider에는 허용 도메인을 넘긴다.
  2. 응답 단계 — 돌아온 URL을 목록과 대조한다. provider가 필터를 지원하든 안 하든
     통과하므로 이쪽이 실제 보증이다.

회사 공식 도메인은 목록에 두지 않는다. 1만 종목의 IR 주소를 손으로 관리할 수 없어
해석된 회사에서 도출하고, 그 회사 분석에서만 허용한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

OFFICIAL = "official"
MEDIA = "media"
COMPANY = "company"
REJECTED = "rejected"

_CONFIG_NAME = "web_search_sources.yaml"


@dataclass(frozen=True, slots=True)
class SourceScope:
    """한 번의 분석에서 허용되는 출처."""

    official: dict[str, str]
    media: dict[str, str]
    paywalled: frozenset[str]
    company_domains: frozenset[str]

    def allowed_domains(self) -> list[str]:
        return sorted({*self.official, *self.media, *self.company_domains})

    def classify(self, url: str) -> tuple[str, str]:
        """`(등급, 표시 이름)`. 목록에 없으면 `("rejected", "")`."""
        host = _host(url)
        if not host:
            return (REJECTED, "")
        for domain in self.company_domains:
            if _covers(domain, host):
                return (COMPANY, domain)
        for table, tier in ((self.official, OFFICIAL), (self.media, MEDIA)):
            for domain, label in table.items():
                if _covers(domain, host):
                    return (tier, label)
        return (REJECTED, "")

    def is_paywalled(self, url: str) -> bool:
        host = _host(url)
        return any(_covers(domain, host) for domain in self.paywalled)


def _host(url: str) -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    if "//" not in text:
        text = f"https://{text}"
    try:
        return (urlparse(text).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def _covers(domain: str, host: str) -> bool:
    """서브도메인은 같은 출처다. `investor.nvidia.com`은 `nvidia.com`에 속한다."""
    domain = str(domain or "").lower().removeprefix("www.")
    return bool(domain) and (host == domain or host.endswith(f".{domain}"))


def company_domain(company: dict | None, overrides: dict | None = None) -> str:
    """회사 공식 도메인. 설정 override가 있으면 그것을 쓰고 없으면 조회 결과를 쓴다."""
    company = company or {}
    ticker = str(company.get("ticker") or "").upper()
    override = (overrides or {}).get(ticker) or (overrides or {}).get(ticker.lower())
    if override:
        return _host(override)
    return _host(company.get("website") or company.get("companyWebsite") or "")


def load_source_scope(company: dict | None = None, *, config_loader=None) -> SourceScope:
    """설정 파일에서 허용 목록을 읽고 이 회사의 도메인을 더한다."""
    payload = _read_config(config_loader)
    official = {
        str(row.get("domain") or "").lower(): str(row.get("label") or row.get("domain") or "")
        for row in payload.get("official") or []
        if isinstance(row, dict) and row.get("domain")
    }
    media = {
        str(row.get("domain") or "").lower(): str(row.get("label") or row.get("domain") or "")
        for row in payload.get("media") or []
        if isinstance(row, dict) and row.get("domain")
    }
    paywalled = {
        str(row.get("domain") or "").lower()
        for row in (payload.get("media") or []) + (payload.get("official") or [])
        if isinstance(row, dict) and row.get("paywalled")
    }
    domain = company_domain(company, payload.get("company_domain_overrides") or {})
    return SourceScope(
        official=official,
        media=media,
        paywalled=frozenset(paywalled),
        company_domains=frozenset({domain} if domain else set()),
    )


def _read_config(config_loader=None) -> dict:
    try:
        import yaml

        from features.common.config_bootstrap import resolve_config

        loader = config_loader or (lambda: resolve_config(_CONFIG_NAME).read_text(encoding="utf-8"))
        payload = yaml.safe_load(loader())
        return payload if isinstance(payload, dict) else {}
    except Exception:
        # 설정을 못 읽으면 아무 도메인도 허용하지 않는다. 목록 없이 여는 것보다
        # 웹 검색을 쓰지 않는 편이 낫다.
        return {}


def render_scope_instruction(scope: SourceScope, company: dict | None = None) -> str:
    """프롬프트에 넣을 허용 목록. 모델이 어디를 봐야 하는지 알아야 한다."""
    company = company or {}
    lines = [
        "## 웹 검색 출처 범위",
        "아래 목록에 있는 출처만 근거로 씁니다. 목록 밖에서 찾은 내용은 보고서에 넣지 않습니다.",
        "",
        f"공식 자료: {', '.join(sorted(scope.official.values()))}",
        f"신뢰 매체: {', '.join(sorted(scope.media.values()))}",
    ]
    if scope.company_domains:
        lines.append(f"회사 공식 사이트: {', '.join(sorted(scope.company_domains))}")
    lines += [
        "",
        "- 유료 매체는 검색 결과의 제목·요약과 공개 페이지까지만 씁니다. 유료 본문을 우회하지 않습니다.",
        "- 공식 자료와 매체 보도는 같은 무게가 아닙니다. 수치는 공식 자료를 우선하고, 매체는 맥락과 해석에 씁니다.",
        "- `Sources Used`에는 출처마다 등급(공식/매체/회사)과 URL을 함께 남깁니다.",
    ]
    return "\n".join(lines)


def render_web_search_directive(scope: SourceScope) -> str:
    """웹 검색을 **쓰라**는 지시. 허용 목록만으로는 금지문으로 읽힌다."""
    return "\n".join([
        "## 웹 검색 사용",
        "이 실행에서는 웹 검색을 쓸 수 있습니다. 로컬 자료만으로 답할 수 없는 부분은 검색으로 보완하세요.",
        "",
        "- 특히 **과거 사례**(지난 국면의 전개·수치), **정책 당국자 발언**, **1차 자료**(중앙은행 성명,",
        "  통계 기관 발표)는 로컬 자료에 거의 없습니다. 그 자리를 검색으로 채우세요.",
        "- 위 허용 목록 안에서만 씁니다. 목록 밖에서 본 내용은 근거로 쓰지 않습니다.",
        "- **웹에서 가져온 사실에는 URL을 함께 남기세요.** URL이 없으면 그 문장은 검증할 수 없습니다.",
        "- 로컬 자료로 확인된 것과 웹에서 새로 찾은 것을 구분해 서술하세요.",
        "- 검색해도 확인되지 않으면 확인되지 않았다고 쓰세요. 추정으로 메우지 마세요.",
        "- **웹에서 쓴 근거는 Source & Data Notes에 출처 이름과 URL을 남기세요.** 본문에 사실만 적고",
        "  URL을 어디에도 남기지 않으면 독자가 확인할 방법이 없습니다.",
    ])


_URL = re.compile(r"https?://[^\s<>\)\]\"']+")


def audit_urls(text: str, scope: SourceScope) -> dict:
    """생성된 본문의 URL을 목록과 대조한다.

    프롬프트로 부탁하는 것과 실제로 지킨 것은 다르다. 무엇이 목록 밖이었는지
    보고서 옆에 남겨야 다음에 목록을 고칠 수 있다.
    """
    seen: dict[str, str] = {}
    for url in _URL.findall(str(text or "")):
        seen.setdefault(url.rstrip(".,);"), "")
    rows = []
    for url in seen:
        tier, label = scope.classify(url)
        rows.append({"url": url, "tier": tier, "label": label})
    return {
        "checked": len(rows),
        "allowed": [row for row in rows if row["tier"] != REJECTED],
        "rejected": [row for row in rows if row["tier"] == REJECTED],
    }
