# 금융 PB Copilot — 스타터 패키지

KT Business Build 3일 실습용 배관임. **0에서 만들지 않되, 판단은 채워 넣는 구조**임.
GitHub을 쓰지 않으므로 이 패키지는 **Google 공유드라이브에서 ZIP으로 배포**됨.

---

## 1. 시작하기

```bash
# 1) 압축 해제한 폴더로 이동
cd kt-pb-copilot-starter

# 2) 환경 파일 생성 후 배부받은 API 키 입력
cp .env.example .env        # Windows:  copy .env.example .env

# 3) 기동
bash scripts/bootstrap.sh   # Windows:  scripts\bootstrap.bat

# 4) 로컬 저장소 초기화 (되돌리기의 전제)
git init && git add -A && git commit -m "실습 0 완료"
```

원격 저장소는 없음. **커밋은 로컬에만 남으며, 그것이 유일한 복구 수단임.**
STEP이 끝날 때마다 커밋하는 습관을 들일 것.

기동에 성공하면 다음이 출력됨.

```
[파싱] 12개 문서 / 추출 실패 의심 1건 → output/parse_fail.json
[청킹:fixed] …청크
[청킹:para] …청크
[청킹:semantic] …청크
[벡터] backend = sklearn
[색인] 완료 — …청크
```

---

## 2. 사용법

```bash
python3 src/rag.py bootstrap                 # 전체 재구축
python3 src/rag.py search "중도해지 수수료"    # 검색만
python3 src/rag.py ask "나루 ELS 제417회의 중도해지 수수료율은?"   # 검색 + 생성
```

Claude Code에서는 코드를 직접 타이핑하지 말고 **업무 언어로 지시**할 것.

```
"src/rag.py 의 parse_pdf 를 Vision 기반 파싱으로 바꿔줘.
 표는 markdown 표로 유지하고, 실패 페이지는 output/parse_fail.csv 에 기록해줘."
```

---

## 3. 폴더 구조

```
src/rag.py              전체 파이프라인 (파싱→청킹→메타→검색→생성)
data/docs/              상품설명서·약관 PDF 12건
data/structured/        고객 프로필 · 보유상품 · 거래내역 CSV
output/                 청크·색인·로그 산출물
notes/                  기록 양식을 채워 넣는 자리
```

---

## 4. 어디를 고치는가 — 실습별 지점

| 실습 | 고치는 함수 | 과제 |
|---|---|---|
| 실습 2 STEP 1 | `parse_pdf()` | 단순 텍스트 추출 → Vision 파싱. 표·2단·스캔본이 살아남는지 확인 |
| 실습 2 STEP 2 | `chunk_fixed / chunk_para / chunk_semantic` | 3종을 각각 실행해 비교하고 선택 근거를 남김 |
| 실습 2 STEP 3 | `extract_meta()` | 6개 필드를 채우고, 못 채운 청크를 목록으로 남김 |
| 실습 3 STEP 1~2 | `BM25` / `Vectors` | 두 경로를 각각 실행해 성격 차이를 관찰 |
| 실습 3 STEP 3 | `Engine.search()` | Hybrid 가중치 조정, Hit@5 측정 |
| 워크샵 1 STEP 3 | `generate()` / `SYSTEM` | 출력 형식 고정, 컨텍스트 구성 상위 k 결정 |

---

## 5. 알아둘 것

**파싱이 깨지는 것이 정상임.** 기본 구현은 단순 텍스트 추출이라 다음이 깨짐.

- 표 병합셀 → 수수료율이 엉뚱한 행에 붙음
- 2단 조판 약관 → 좌우 단이 한 문장으로 섞임
- 손익구조도 → 이미지뿐이라 아무것도 남지 않음
- 스캔본 1건 → **텍스트 레이어가 아예 없음**

이 실패를 기록하는 것이 실습 2의 산출물이며, Day 2 한계 진단의 재료임.

**벡터 백엔드는 3단 폴백임.** 어떤 환경에서도 기동되도록 설계함.

| backend | 방식 | 비고 |
|---|---|---|
| `st` | sentence-transformers 로컬 모델 | `models/embedding` 이 있을 때만 |
| `sklearn` | 문자 n-gram TF-IDF + LSA | **기본값.** 인터넷 없이 동작함 |
| `hash` | 순수 파이썬 해싱 벡터 | 최후의 보루 |

기본값(`sklearn`)은 문자 n-gram이라 조사·어미 변화를 어느 정도 흡수하지만
**진짜 의미 임베딩은 아님.** 이 한계 자체가 Day 2에서 다룰 재료임.

**메타데이터 필터링이 개정 이력 문제의 열쇠임.**

```python
eng.search("중도해지 수수료", where={'revision_date': '2026-03-01'})
```

같은 상품의 구버전·신버전 약관이 함께 색인되어 있음. 필터 없이 검색하면 둘 다 나옴.

---

## 6. 막혔을 때

공유드라이브 `90_체크포인트/` 에 단계별 복구용 ZIP이 있음.

| ZIP | 상태 | 복구 대상 |
|---|---|---|
| `D1-A_파싱완료.zip` | 파싱·청킹·메타데이터 완료 | 실습 3 진입 |
| `D1-B_인덱스완료.zip` | 색인 구축 완료 | 워크샵 1 진입 |
| `D1-C_MVPv1완성.zip` | RAG MVP v1 완성 | Day 2 시작 |

복구 절차는 각 ZIP 안의 `RESTORE.txt` 참조. 오래 막히면 즉시 호출할 것.

---

## 7. 데이터 고지

`data/` 의 모든 문서·고객 데이터는 **교육용으로 생성한 합성 데이터**임.
가상의 금융회사(나루은행 · 나루자산운용 · 나루생명)와 가상 인물이며,
실존하는 금융상품·약관·개인과 무관함. **실제 투자 판단에 사용할 수 없음.**
