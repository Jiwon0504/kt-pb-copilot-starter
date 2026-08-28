# CLAUDE.md

이 파일은 Claude Code가 이 프로젝트에서 작업할 때 따라야 할 규칙과 맥락을 담고 있습니다.

## 1. Project Overview

- 금융 PB(프라이빗뱅커) 업무를 지원하는 **Agentic RAG 기반 Copilot** 프로젝트임
- 금융상품 PDF 문서(상품설명서·약관·안내서 등)를 근거로, PB의 자연어 질문에 **문서 근거 기반 답변**을 제공하는 서비스임
- KT Business Build 실습용 스타터 패키지이며, 배관(파이프라인)은 제공되고 판단(청킹 전략·메타데이터 설계·검색 도구 설계 등)은 계속 채워나가는 구조임

## 2. Architecture

- Python / Flask 기반 웹 애플리케이션
- `src/rag.py` — RAG 및 Agentic RAG 핵심 로직 전체를 담당 (파싱, 청킹, 메타데이터 추출, 검색 엔진, 에이전트 루프, 답변 생성)
- `src/app.py` — 웹 UI(Flask 라우트) 및 API(`/api/meta`, `/api/tools`, `/api/ask`) 담당. 실제 검색/생성 로직은 `rag.py`를 호출만 함
- 전체 흐름: 금융상품 PDF → **파싱**(`parse_pdf`/`parse_all`) → **청킹**(`chunk_fixed`/`chunk_para`/`chunk_semantic`) → **메타데이터 추출**(`extract_meta`) → **검색**(`Engine` + 도구) → **Agent**(`agentic_ask`, 도구 선택·재검색 판단) → **Claude 답변 생성**(`generate`)
- 현재 Agentic RAG 검색 도구(Tool)는 `rag.py`의 `register_tool` 데코레이터로 등록되며, 총 3개임: `bm25_search`, `multi_query_search`, `metadata_filter_search`
- 도구를 추가/수정/삭제하려면 `@register_tool` 데코레이터가 붙은 함수를 추가/수정/삭제하면 됨 — 등록 즉시 에이전트가 쓸 수 있는 도구 목록과 웹 UI `/api/tools` 목록에 자동 반영됨

## 3. RAG Principles

- 금융상품 관련 답변은 **검색된 문서를 우선적인 근거**로 사용함
- 검색 근거가 부족한 경우 내용을 추측하거나 지어내지 않음 ("제공된 문서에서 확인되지 않음"으로 답함)
- BM25(`bm25_search`) / Multi Query(`multi_query_search`) / Metadata Filter(`metadata_filter_search`)는 서로 역할이 다름
  - `bm25_search`: 검색어 표현이 명확한 **내용 검색**
  - `multi_query_search`: 표현이 다를 수 있는 질문에 대해 여러 변형으로 동시 검색 후 RRF로 융합
  - `metadata_filter_search`: 검색어 없이 상품코드·문서유형·개정일·위험등급·대상세그먼트 **조건으로만 필터링**
- Agent가 질문 성격에 맞는 검색 도구를 스스로 선택하도록 설계되어 있음 (도구 선택은 각 도구의 `description` 문구가 결정하므로, 도구를 추가/수정할 때는 description을 명확히 구분되게 작성함)
- Agent는 필요 시 추가 검색을 할 수 있으나, 검색 횟수 제한(`MAX_SEARCHES`)을 반드시 준수함

## 4. Development Rules

- 코드를 수정하기 전에 관련 파일과 기존 구조를 먼저 확인함
- 기존 기능을 불필요하게 변경하지 않음
- 변경 범위를 최소화함
- 새 기능을 만들기 전에 기존 함수/구조(`Engine`, `register_tool`, `_merge_where`, `meta_values` 등)를 재사용할 수 있는지 먼저 검토함
- 코드를 수정한 후에는 문법 오류(`python3 -m py_compile` 등)와 기존 기능의 정상 작동 여부를 확인함
- 설계가 필요한 작업에서는 바로 코드를 수정하지 말고 먼저 설계안을 제시함

## 5. Financial Domain Rules

- 금융상품 정보는 근거 없이 생성하지 않음
- 상품의 조건, 위험등급, 대상 고객 등의 정보는 검색된 데이터와 metadata(`product_id`, `doc_type`, `revision_date`, `risk_grade`, `target_segment`, `clause_no`)를 기준으로 함
- 투자 판단이나 상품 적합성을 근거 없이 단정하지 않음 (수익을 단정하는 표현 금지)

## 6. Working Style

- 사용자는 초보 개발자이므로, 중요한 코드 변경은 **무엇을 왜 변경하는지** 설명함
- 전문 용어를 사용할 경우 간단한 설명을 함께 제공함
- 작업 전 현재 상태와 변경 계획을 간단히 설명함
- 작업 후 수정된 파일, 주요 변경 내용, 테스트 방법을 요약함
