"""yfinance 심볼 후보.

한국 종목은 앱 전반에서 **bare 6자리 코드가 저장 규약**이다 — 회사 해석기와 워치리스트
(`_watchlist_ticker`)가 `.KS`/`.KQ` 접미사를 오히려 떼어 저장한다. yfinance는 bare 코드를
못 읽으므로(실측: `005930`은 404, `005930.KS`는 정상) provider 경계에서 접미사를 붙여야
하는데, 코드만으로는 KOSPI(.KS)/KOSDAQ(.KQ)을 알 수 없어 후보 둘을 차례로 시도한다 —
`sector_cache`·`portfolio/service`가 이미 같은 결정을 했다. 차트·지표·실적 세 서비스가
이 헬퍼 하나를 쓴다.
"""
from __future__ import annotations

import re


def yfinance_symbol_candidates(symbol) -> tuple[str, ...]:
    text = str(symbol or "").strip().upper()
    if re.fullmatch(r"\d{6}", text):
        return (f"{text}.KS", f"{text}.KQ")
    return (text,)
