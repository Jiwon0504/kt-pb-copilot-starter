#!/usr/bin/env bash
# 스타터 기동 스크립트 — 파싱 → 청킹 3종 → 색인 → 샘플 질문 1건
set -e
cd "$(dirname "$0")/.."
echo "── 1) 의존성 확인"
python3 -m pip install -q -r requirements.txt || echo "  (설치 실패 — 오프라인이면 무시하고 계속)"
echo "── 2) .env 확인"
[ -f .env ] || { cp .env.example .env; echo "  .env 를 생성했음. API 키를 채운 뒤 다시 실행할 것"; }
echo "── 3) 문서 확인"
ls -1 data/docs/*.pdf 2>/dev/null | wc -l | xargs -I{} echo "  PDF {}건"
echo "── 4) 파싱 · 청킹 · 색인"
python3 -W ignore src/rag.py bootstrap
echo ""
echo "✓ 완료.  다음 명령으로 질문할 수 있음:"
echo "    python3 src/rag.py ask \"나루 ELS 제417회의 중도해지 수수료율은?\""
