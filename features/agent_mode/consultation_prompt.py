"""Rules fallback for consultation turns when no Agent CLI is available."""
from __future__ import annotations


def rules_fallback(user_message: str) -> str:
    topic = str(user_message or "").strip()[:300]
    return (
        f"질문을 이 상담의 현재 맥락에 연결해 검토하겠습니다. 현재 요청은 ‘{topic}’입니다.\n\n"
        "지금은 Agent 실행 환경을 사용할 수 없어 저장 자료의 구체 내용을 재서술하지 않습니다. "
        "판단할 때는 최근 변화가 기존 장기 thesis를 실제로 바꾸는지, 공식 확인이나 독립된 복수 출처가 있는지, "
        "반대 근거와 데이터 공백이 무엇인지 순서대로 확인하는 것이 좋습니다."
    )
