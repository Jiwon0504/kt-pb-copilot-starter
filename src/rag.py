#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KT Business Build — 금융 PB Copilot 스타터
파싱 → 청킹 → 메타데이터 → BM25/Vector/Hybrid 검색 → 생성

배관만 제공함. 판단(청킹 전략·메타데이터 설계·가중치·컨텍스트 구성)은 수강생이 채움.
Claude Code에 "이 파일의 XXX를 이렇게 바꿔줘"라고 지시하며 진행하면 됨.
"""
from __future__ import annotations
import os, re, json, math, glob, pickle, unicodedata, hashlib
from collections import Counter, defaultdict
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, 'data', 'docs')
OUTD = os.path.join(ROOT, 'output')
os.makedirs(OUTD, exist_ok=True)


# ════════════════════════════════════════════════════════════
# 1. 파싱
# ════════════════════════════════════════════════════════════
EMPTY_TEXT_THRESHOLD = 30  # 이보다 짧으면 텍스트 레이어가 없다고 판단함


def _vision_ocr(img) -> str:
    """텍스트 레이어가 없는 스캔본 페이지를 Claude Vision으로 옮겨 적음.
    ★단순 텍스트 추출이 실패한 페이지에서만 호출됨 — 페이지당 API 호출 1회."""
    import base64, io
    key = os.getenv('ANTHROPIC_API_KEY')
    if not key:
        return ''
    try:
        import anthropic
    except ImportError:
        return ''
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue()).decode()
    cl = anthropic.Anthropic(api_key=key)
    r = cl.messages.create(
        model=os.getenv('MODEL', 'claude-sonnet-4-5'),
        max_tokens=2000,
        messages=[{'role': 'user', 'content': [
            {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png', 'data': b64}},
            {'type': 'text', 'text': (
                '이 이미지는 금융상품 문서의 한 페이지임. 페이지 맨 위 정보 표시줄(상품코드·문서구분·개정일·'
                '위험등급 등)과 박스·표를 포함해 보이는 텍스트를 위에서부터 빠짐없이 그대로 옮겨 적을 것. '
                '표는 markdown 표로 유지하고, 임의로 내용을 추가·해석·요약·생략하지 말 것.'
            )},
        ]}])
    return r.content[0].text


def parse_pdf(path: str) -> list[dict]:
    """PDF → 페이지별 텍스트.
    단순 텍스트 추출을 우선 시도하고, 텍스트 레이어가 없는 페이지(스캔본 등)는
    페이지를 이미지로 렌더링해 Claude Vision으로 옮겨 적음 (ANTHROPIC_API_KEY 필요).
    표·2단 조판은 여전히 단순 추출 기준으로는 깨질 수 있음."""
    pages = []
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            for i, pg in enumerate(pdf.pages, 1):
                text = pg.extract_text() or ''
                if len(text.strip()) < EMPTY_TEXT_THRESHOLD:
                    text = _vision_ocr(pg.to_image(resolution=200).original) or text
                pages.append({'page': i, 'text': text})
        return pages
    except ImportError:
        pass
    try:
        from pypdf import PdfReader
        r = PdfReader(path)
        for i, pg in enumerate(r.pages, 1):
            pages.append({'page': i, 'text': pg.extract_text() or ''})
        return pages
    except ImportError:
        raise SystemExit('pdfplumber 또는 pypdf 가 필요함:  pip install pdfplumber')


def parse_all() -> list[dict]:
    out, fails = [], []
    for p in sorted(glob.glob(os.path.join(DOCS, '*.pdf'))):
        fn = os.path.basename(p)
        pages = parse_pdf(p)
        empty = [pg['page'] for pg in pages if len(pg['text'].strip()) < EMPTY_TEXT_THRESHOLD]
        if empty:
            fails.append({'file': fn, 'pages': empty, 'reason': '텍스트 추출 결과 없음/부족'})
        out.append({'file': fn, 'pages': pages})
    with open(os.path.join(OUTD, 'parse_fail.json'), 'w', encoding='utf-8') as f:
        json.dump(fails, f, ensure_ascii=False, indent=2)
    print(f'[파싱] {len(out)}개 문서 / 추출 실패 의심 {len(fails)}건 → output/parse_fail.json')
    return out


# ════════════════════════════════════════════════════════════
# 2. 청킹  ─ 3종. 실습 2 STEP 2에서 비교함
# ════════════════════════════════════════════════════════════
def chunk_fixed(text: str, size: int = 600, overlap: int = 80) -> list[str]:
    text = re.sub(r'\s+', ' ', text).strip()
    out, i = [], 0
    while i < len(text):
        out.append(text[i:i + size])
        i += size - overlap
    return [c for c in out if c.strip()]


def chunk_para(text: str, min_len: int = 380, max_len: int = 900) -> list[str]:
    """조항 번호(제N조) · 절 제목(1. …) · 표 제목 · 빈 줄 기준.
    금융 문서 구조에 맞춘 분할이며, 너무 긴 조각은 max_len으로 다시 자름."""
    parts = re.split(
        r'(?=제\s?\d+\s?조)'          # 약관 조항
        r'|(?=^\s*\d{1,2}\.\s)'       # 설명서 절 제목
        r'|(?=\[표\s?\d)'             # 표 제목
        r'|(?=^\s*[가-하]\.\s)'       # 가. 나. 다.
        r'|\n{2,}', text, flags=re.M)
    merged, buf = [], ''
    for p in parts:
        p = (p or '').strip()
        if not p:
            continue
        if len(buf) + len(p) < min_len:
            buf = (buf + '\n' + p).strip()
        else:
            if buf:
                merged.append(buf)
            buf = p
    if buf:
        merged.append(buf)
    out = []
    for m in merged:                  # 과대 청크 재분할
        if len(m) <= max_len:
            out.append(m)
        else:
            out.extend(chunk_fixed(m, size=max_len, overlap=100))
    return out


def chunk_semantic(text: str, size: int = 700) -> list[str]:
    """문장 경계를 지키면서 크기를 맞춤. 완전한 시맨틱 청킹은 아니며,
    실습 2에서 임베딩 기반으로 고도화하는 것이 과제임."""
    sents = re.split(r'(?<=[.。!?])\s+|\n', text)
    out, buf = [], ''
    for s in sents:
        s = s.strip()
        if not s:
            continue
        if len(buf) + len(s) + 1 <= size:
            buf = (buf + ' ' + s).strip()
        else:
            if buf:
                out.append(buf)
            buf = s
    if buf:
        out.append(buf)
    return out


CHUNKERS = {'fixed': chunk_fixed, 'para': chunk_para, 'semantic': chunk_semantic}


# ════════════════════════════════════════════════════════════
# 3. 메타데이터  ─ 실습 2 STEP 3에서 확장함
# ════════════════════════════════════════════════════════════
META_FIELDS = ['product_id', 'doc_type', 'revision_date',
               'risk_grade', 'clause_no', 'target_segment']

RE_PID = re.compile(r'\b((?:ELS|FND|DEP|PEN|ISA)-\d{4}-\d{4}|COMMON-\d{3})\b')
# 문서 머리말의 "개정일 YYYY-MM-DD" 를 우선 사용함.
# ★상품코드(ELS-2026-0417)가 날짜처럼 보이므로 일반 날짜 정규식을 쓰면 오추출됨 — 주의.
RE_REV = re.compile(r'개정일\s*(20\d{2})-(\d{2})-(\d{2})')
RE_CLA = re.compile(r'제\s?(\d+)\s?조(?:\s?제?\s?(\d+)\s?항)?')
RE_GRD = re.compile(r'([1-5])\s?등급')


def extract_meta(chunk: str, doc_head: str) -> dict:
    """★기본 구현임. 놓치는 청크가 많은 것이 정상이며,
       채우지 못한 필드를 목록으로 남기는 것이 실습 2의 산출물임."""
    src = doc_head + '\n' + chunk
    m = {k: None for k in META_FIELDS}
    if (x := RE_PID.search(src)):
        m['product_id'] = x.group(1)
    for t in ('상품설명서', '간이투자설명서', '투자설명서', '약관', '안내서'):
        if t in doc_head:
            m['doc_type'] = t
            break
    if (x := RE_REV.search(doc_head)):
        m['revision_date'] = f'{x.group(1)}-{int(x.group(2)):02d}-{int(x.group(3)):02d}'
    if (x := RE_GRD.search(doc_head)):
        m['risk_grade'] = f'{x.group(1)}등급'
    if (x := RE_CLA.search(chunk)):
        m['clause_no'] = f'제{x.group(1)}조' + (f' 제{x.group(2)}항' if x.group(2) else '')
    for t in ('고액자산가', '일반', '공통'):
        if t in doc_head:
            m['target_segment'] = t
            break
    return m


def build_chunks(strategy: str = 'para') -> list[dict]:
    docs = parse_all()
    fn_chunk = CHUNKERS[strategy]
    chunks, miss = [], Counter()
    for d in docs:
        full = '\n'.join(p['text'] for p in d['pages'])
        head = full[:600]
        for ci, c in enumerate(fn_chunk(full)):
            meta = extract_meta(c, head)
            for k, v in meta.items():
                if v is None:
                    miss[k] += 1
            chunks.append({'id': f'{d["file"]}#{strategy}#{ci}', 'file': d['file'],
                           'text': c, **meta})
    path = os.path.join(OUTD, f'chunks_{strategy}.json')
    json.dump(chunks, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'[청킹:{strategy}] {len(chunks)}청크 / 평균 {sum(len(c["text"]) for c in chunks)//max(len(chunks),1)}자 → {path}')
    if miss:
        print('  메타데이터 미채움:', dict(miss))
    return chunks


# ════════════════════════════════════════════════════════════
# 4. 검색 ─ BM25 (Kiwi 형태소 분석 토크나이저)
# ════════════════════════════════════════════════════════════
_KIWI = None
# 체언·어근·외래어·숫자·용언 어간만 남김. 조사(JKS/JKO…)·어미(EC/EF…)는 제외되어
# "중도해지"와 "중도에 해지하다"처럼 조사·어미만 다른 표현이 같은 토큰으로 매칭됨.
_KEEP_TAGS = {'NNG', 'NNP', 'NNB', 'NR', 'NP', 'VV', 'VA', 'VX', 'XR', 'SL', 'SH', 'SN'}


def _kiwi():
    global _KIWI
    if _KIWI is None:
        try:
            from kiwipiepy import Kiwi
        except ImportError:
            raise SystemExit('kiwipiepy가 필요함: pip install kiwipiepy')
        _KIWI = Kiwi()
    return _KIWI


def tok(s: str) -> list[str]:
    s = unicodedata.normalize('NFKC', s)
    return [t.form.lower() for t in _kiwi().tokenize(s) if t.tag in _KEEP_TAGS]


class BM25:
    def __init__(self, docs: list[str], k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        self.toks = [tok(d) for d in docs]
        self.N = len(self.toks)
        self.len = [len(t) for t in self.toks]
        self.avg = sum(self.len) / max(self.N, 1)
        df = Counter()
        for t in self.toks:
            df.update(set(t))
        self.idf = {w: math.log(1 + (self.N - c + 0.5) / (c + 0.5)) for w, c in df.items()}
        self.tf = [Counter(t) for t in self.toks]

    def search(self, q: str, k=5) -> list[tuple[int, float]]:
        qt = tok(q)
        sc = [0.0] * self.N
        for i in range(self.N):
            s = 0.0
            for w in qt:
                f = self.tf[i].get(w, 0)
                if not f:
                    continue
                s += self.idf.get(w, 0) * f * (self.k1 + 1) / (
                    f + self.k1 * (1 - self.b + self.b * self.len[i] / max(self.avg, 1)))
            sc[i] = s
        return sorted(enumerate(sc), key=lambda x: -x[1])[:k]


# ════════════════════════════════════════════════════════════
# 5. Engine  ─ BM25 + 최신성 가중치 + 메타데이터 필터링
# ════════════════════════════════════════════════════════════
def minmax(pairs, n):
    d = [0.0] * n
    if not pairs:
        return d
    vs = [v for _, v in pairs]
    lo, hi = min(vs), max(vs)
    for i, v in pairs:
        d[i] = (v - lo) / (hi - lo) if hi > lo else 0.0
    return d


def _filename_text(fn: str) -> str:
    """파일명을 검색 가능한 텍스트로 바꿈 (번호 접두어·확장자 제거, '_' → 공백).
    예: '07_나루연금저축보험_상품설명서.pdf' → '나루연금저축보험 상품설명서'"""
    name = re.sub(r'\.pdf$', '', fn, flags=re.I)
    name = re.sub(r'^\d+_', '', name)
    return name.replace('_', ' ')


def _parse_date(s: str | None):
    if not s:
        return None
    try:
        y, m, d = (int(x) for x in s.split('-'))
        return date(y, m, d)
    except (ValueError, TypeError):
        return None


class Engine:
    # 최신성 가중치. 0에 가까울수록 순수 BM25, 1에 가까울수록 날짜만으로 순위가 결정됨.
    RECENCY_WEIGHT = 0.15
    # 반감기(일). 코퍼스 내 최신 개정일 기준 이만큼 지난 문서는 최신성 점수가 절반이 됨.
    RECENCY_HALF_LIFE_DAYS = 180

    def __init__(self, chunks: list[dict]):
        self.chunks = chunks
        # 파일명도 검색 대상에 포함시킴 — 청크 본문에는 없지만 파일명에만 있는 상품명·문서종류
        # 키워드(예: "예금거래기본약관")로도 찾을 수 있어야 함.
        corpus = [f"{_filename_text(c['file'])} {c['text']}" for c in chunks]
        self.bm25 = BM25(corpus)
        self.recency = self._compute_recency(chunks)

    def _compute_recency(self, chunks: list[dict]) -> list[float]:
        """revision_date 기반 최신성 점수(0~1). 지수 감쇠(exponential decay)를 씀.
        ★단순 날짜 내림차순 정렬이 아니라 감쇠 함수를 쓰는 이유: 반감기 이내의 문서끼리는
          점수 차이가 작아 BM25 관련도가 여전히 순위를 주도하고, 아주 오래된 문서만
          확실히 밀려나게 하기 위함 — 관련도와 최신성이 함께 작동하도록 함.
        revision_date를 못 채운 청크(추출 실패)는 중립값(0.5)을 줘서 불이익을 주지 않음."""
        dates = [_parse_date(c.get('revision_date')) for c in chunks]
        known = [d for d in dates if d]
        if not known:
            return [0.5] * len(chunks)
        newest = max(known)
        lam = math.log(2) / self.RECENCY_HALF_LIFE_DAYS
        return [math.exp(-lam * (newest - d).days) if d else 0.5 for d in dates]

    def _finalize(self, rel: list[float], k: int, where: dict | None) -> list[dict]:
        """관련도(rel, 0~1)에 최신성을 섞고 메타데이터 필터링 후 top-k를 뽑음.
        search()/search_multi() 둘 다 관련도 계산 방식만 다르고 나머지는 같아 공유함."""
        n = len(self.chunks)
        w = self.RECENCY_WEIGHT
        sc = [(1 - w) * rel[i] + w * self.recency[i] for i in range(n)]
        idx = sorted(range(n), key=lambda i: -sc[i])
        out = []
        for i in idx:
            c = self.chunks[i]
            if where and any(c.get(f) != v for f, v in where.items()):
                continue          # ← 메타데이터 필터링. Day 2 개정 이력 대응의 핵심임
            out.append({**c, 'score': round(sc[i], 4)})
            if len(out) >= k:
                break
        return out

    def search(self, q: str, k=5, where: dict | None = None) -> list[dict]:
        n = len(self.chunks)
        rel = minmax(self.bm25.search(q, n), n)
        return self._finalize(rel, k, where)

    def search_multi(self, queries: list[str], k=5, where: dict | None = None) -> list[dict]:
        """여러 표현의 질의를 각각 BM25로 검색하고 RRF(Reciprocal Rank Fusion)로 합침.
        ★BM25는 어휘가 정확히 일치해야 걸리므로, 같은 의도라도 표현(동의어·어순·전문용어/일상어)이
          다르면 놓칠 수 있음 — 질의 변형마다 순위를 매긴 뒤 순위 기반으로 합산하면 점수 스케일이
          달라도 안정적으로 융합되고, 여러 변형에서 공통으로 상위에 오르는 청크가 유리해짐."""
        n = len(self.chunks)
        fused = [0.0] * n
        for q in queries:
            for rank, (i, sc) in enumerate(self.bm25.search(q, n), 1):
                if sc > 0:
                    fused[i] += 1.0 / (60 + rank)
        rel = minmax(list(enumerate(fused)), n)
        return self._finalize(rel, k, where)


# ════════════════════════════════════════════════════════════
# 6. Agentic RAG ─ 검색을 '도구'로 쪼개고, 에이전트가 스스로 골라 쓰며
#    검색 결과를 스스로 평가해 재검색(최대 MAX_SEARCHES회) 여부를 판단함
# ════════════════════════════════════════════════════════════
FILTER_FIELDS = ['product_id', 'doc_type', 'revision_date', 'risk_grade', 'target_segment']
MAX_SEARCHES = 2  # 에이전트가 한 번의 질문에 검색 도구를 쓸 수 있는 최대 횟수


def meta_values(chunks: list[dict], fields: list[str] = META_FIELDS) -> dict:
    return {f: sorted({c.get(f) for c in chunks if c.get(f)}) for f in fields}


# ── 도구 레지스트리 ──────────────────────────────────────────
# 검색 알고리즘을 추가하려면: 아래 형태로 @register_tool 데코레이터를 단 함수를 하나 더 적으면 됨.
# 수정하려면: 해당 함수 본문(또는 build_schema)만 바꾸면 됨. 삭제하려면: 함수와 데코레이터를 지우면 됨.
# 이 등록만으로 (1) 에이전트가 호출할 수 있는 도구, (2) /api/tools 웹 도구 목록에 자동으로 반영됨.
TOOLS: dict[str, dict] = {}


def register_tool(name: str, description: str, build_schema):
    """build_schema(values) -> JSON Schema. values는 meta_values()가 만든 {필드: 가능한 값 목록}."""
    def deco(fn):
        TOOLS[name] = {'name': name, 'description': description, 'build_schema': build_schema, 'fn': fn}
        return fn
    return deco


def list_tools() -> list[dict]:
    """웹 UI '검색 도구' 패널에 노출할 도구 목록."""
    return [{'name': t['name'], 'description': t['description']} for t in TOOLS.values()]


def _filter_schema(values: dict) -> dict:
    return {
        'product_id': {'enum': values['product_id'] + [None]},
        'doc_type': {'enum': values['doc_type'] + [None]},
        'revision_date': {'enum': values['revision_date'] + [None]},
    }


def _merge_where(manual_where, product_id=None, doc_type=None, revision_date=None,
                  risk_grade=None, target_segment=None):
    auto = {f: v for f, v in
            {'product_id': product_id, 'doc_type': doc_type, 'revision_date': revision_date,
             'risk_grade': risk_grade, 'target_segment': target_segment}.items() if v}
    return {**auto, **(manual_where or {})} or None


@register_tool(
    'bm25_search',
    '단일 검색어로 BM25(Kiwi 형태소 분석) + 최신성 가중치 검색을 함. 검색어 표현이 명확할 때 적합함.',
    lambda values: {
        'type': 'object',
        'properties': {'query': {'type': 'string', 'description': '검색어'}, **_filter_schema(values)},
        'required': ['query', 'product_id', 'doc_type', 'revision_date'],
    },
)
def _tool_bm25_search(engine, query, product_id=None, doc_type=None, revision_date=None,
                       k=5, manual_where=None):
    where = _merge_where(manual_where, product_id, doc_type, revision_date)
    return engine.search(query, k=k, where=where)


@register_tool(
    'multi_query_search',
    '의미는 같지만 표현이 다른 검색어 여러 개(동의어·어순·전문용어/일상어 변형)로 동시에 검색해 '
    'RRF(Reciprocal Rank Fusion)로 합침. 질문이 포괄적이거나 표현이 문서와 일치할지 불확실할 때 적합함.',
    lambda values: {
        'type': 'object',
        'properties': {
            'queries': {'type': 'array', 'items': {'type': 'string'}, 'description': '같은 의도의 검색어 변형 2~5개'},
            **_filter_schema(values),
        },
        'required': ['queries', 'product_id', 'doc_type', 'revision_date'],
    },
)
def _tool_multi_query_search(engine, queries, product_id=None, doc_type=None, revision_date=None,
                              k=5, manual_where=None):
    where = _merge_where(manual_where, product_id, doc_type, revision_date)
    return engine.search_multi(queries, k=k, where=where)


def _metadata_filter_schema(values: dict) -> dict:
    """metadata_filter_search 전용 스키마. 검색어(query/queries) 없이 필터 필드만 받음."""
    return {
        'product_id': {'enum': values['product_id'] + [None]},
        'doc_type': {'enum': values['doc_type'] + [None]},
        'revision_date': {'enum': values['revision_date'] + [None]},
        'risk_grade': {'enum': values['risk_grade'] + [None]},
        'target_segment': {'enum': values['target_segment'] + [None]},
    }


@register_tool(
    'metadata_filter_search',
    '검색어 없이 상품코드·문서유형·개정일·위험등급·대상세그먼트 조건만으로 문서를 걸러낼 때 씀. '
    '내용을 찾는 질문(예: 수수료율이 얼마인지)이 아니라 "3등급이면서 고액자산가 대상인 상품이 뭔지", '
    '"이 상품 관련 문서가 뭐가 있는지", "가장 최근 개정본이 어떤 버전인지"처럼 조건에 맞는 문서·버전 '
    '자체를 찾는 질문에 적합함. 결과는 키워드 관련도가 아니라 최신순으로 정렬됨.',
    lambda values: {
        'type': 'object',
        'properties': _metadata_filter_schema(values),
        'required': ['product_id', 'doc_type', 'revision_date', 'risk_grade', 'target_segment'],
    },
)
def _tool_metadata_filter_search(engine, product_id=None, doc_type=None, revision_date=None,
                                  risk_grade=None, target_segment=None, k=5, manual_where=None):
    where = _merge_where(manual_where, product_id=product_id, doc_type=doc_type,
                          revision_date=revision_date, risk_grade=risk_grade,
                          target_segment=target_segment)
    # 검색어가 없으므로 모든 청크의 관련도를 동일하게 두고, 필터링과 최신성만으로 순위를 매김
    # (bm25_search/multi_query_search와 동일한 Engine._finalize를 그대로 재사용함)
    rel = [1.0] * len(engine.chunks)
    return engine._finalize(rel, k, where)


def _anthropic_tools(values: dict) -> list[dict]:
    return [{'name': t['name'], 'description': t['description'], 'input_schema': t['build_schema'](values)}
            for t in TOOLS.values()]


# ── 에이전트 루프 ────────────────────────────────────────────
AGENT_SYSTEM = f"""당신은 금융 PB Copilot의 검색 에이전트임. 아래 도구로 문서를 찾아 질문에 답함.

질문을 받으면 답하기 전에 반드시 검색 도구를 최소 1회 사용할 것. 도구의 입력 스키마에 나오는
필터 값 목록(product_id 등)은 필터링에만 쓰는 목록이며 그 자체가 답이 아님 — 목록만 보고 추측해서
답하지 말고 항상 실제 검색 결과에 근거해 답할 것.

검색 도구는 최대 {MAX_SEARCHES}번까지 쓸 수 있음. 도구를 쓴 뒤에는 결과를 스스로 평가할 것:
- 질문에 답하기 충분하면 더 검색하지 말고 즉시 최종 답변을 낼 것.
- 부족하면 다른 검색어·다른 도구·다른 메타데이터 필터로 한 번 더 검색할 것.
- {MAX_SEARCHES}번을 다 썼으면(더 이상 도구를 쓸 수 없음) 그때까지 찾은 근거만으로 최선의 답을 낼 것.
검색 결과에 없는 내용을 지어내 답하지 말 것 — 근거가 없으면 "제공된 문서에서 확인되지 않음"이라고 답할 것.
수익을 단정하는 표현을 쓰지 말 것.

최종 답변은 반드시 아래 3단 형식으로 낼 것:
[제안] 한두 문장으로 결론
[근거] 문서 내용을 인용하며 설명
[출처] 문서명과 조항 번호"""


# ── 캐싱 ─────────────────────────────────────────────────────
# Workshop 요구사항: 캐싱 테이블 참고 로직. 동일 질문(+k+메타데이터 필터)이 다시 들어오면
# Claude를 재호출하지 않고 저장된 결과를 그대로 재사용함. 외부 DB 없이 로컬 JSON 파일로 최소 구현함.
CACHE_PATH = os.path.join(OUTD, 'qa_cache.json')
_CACHE: dict | None = None


def _load_cache() -> dict:
    global _CACHE
    if _CACHE is None:
        if os.path.exists(CACHE_PATH):
            _CACHE = json.load(open(CACHE_PATH, encoding='utf-8'))
        else:
            _CACHE = {}
    return _CACHE


def _save_cache() -> None:
    json.dump(_CACHE, open(CACHE_PATH, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


def _cache_key(question: str, k: int, where: dict | None) -> str:
    """question+k+where 조합을 정규화해 SHA-256으로 해시함 — 필터가 다르면 별개 캐시로 취급됨."""
    payload = json.dumps({'q': question.strip(), 'k': k, 'where': where or {}},
                          sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def _cache_get(key: str) -> dict | None:
    return _load_cache().get(key)


def _cache_set(key: str, result: dict) -> None:
    cache = _load_cache()
    cache[key] = result
    _save_cache()


# ── 가드레일 ─────────────────────────────────────────────────
# Workshop 요구사항: Input/Output Guardrail. agentic_ask()의 진입점/반환 직전에만 적용하고
# 검색 도구·Engine 등 다른 RAG 로직은 건드리지 않음(규칙 기반 — 애매한 질문은 AGENT_SYSTEM의
# 소프트 방어(근거 기반 답변 강제, 수익 단정 금지 지시)가 2차로 받쳐줌).
_INPUT_GUARDRAIL_REFUSAL = (
    '[제안] 이 서비스는 금융상품 문서에 근거한 질의응답 전용입니다. '
    '금융상품·약관·수수료·조항 등과 관련된 질문을 입력해 주세요.\n'
    '[근거] -\n[출처] -'
)

# 금융/PB 업무와 무관한 잡담·일반 지식 질문, 시스템 지침을 캐내려는 질문의 신호 키워드
_OFFTOPIC_PATTERNS = [
    r'날씨', r'맛집', r'점심\s*(뭐|추천)', r'저녁\s*(뭐|추천)',
    r'너는\s*무슨\s*(모델|ai|인공지능)', r'너\s*누구', r'너에\s*대해\s*알려',
    r'시스템\s*프롬프트', r'system\s*prompt',
    r'이전\s*(지시|지침|명령).{0,10}(무시|잊)', r'ignore\s*(previous|all)\s*instructions',
    r'농담\s*(해|하나)', r'오늘\s*기분', r'파이썬\s*(코드|짜)', r'코드\s*짜줘',
]
_OFFTOPIC_RE = re.compile('|'.join(_OFFTOPIC_PATTERNS), re.IGNORECASE)


def check_input_guardrail(question: str) -> str | None:
    """금융 PB 업무와 무관하거나 시스템 지침을 캐내려는 질문을 검색 이전에 차단함.
    차단 대상이면 안내 답변(3단 형식) 문자열을 반환하고, 통과하면 None을 반환함."""
    if not question.strip():
        return _INPUT_GUARDRAIL_REFUSAL
    if _OFFTOPIC_RE.search(question):
        return _INPUT_GUARDRAIL_REFUSAL
    return None


# 수익 보장/투자 권유성 확정 표현의 신호 키워드
_RISKY_PATTERNS = [
    r'무조건\s*(오릅니다|오른다|수익|이익)',
    r'수익(을|이)?\s*보장',
    r'원금\s*보장',
    r'지금\s*(사세요|매수하세요|가입하세요|투자하세요)',
    r'확실한\s*투자처',
    r'안전한\s*투자처',
    r'무조건\s*추천',
    r'100\s*%\s*수익',
]
_RISKY_RE = re.compile('|'.join(_RISKY_PATTERNS))
_RISKY_DISCLAIMER = ('\n\n[유의] 위 답변 중 수익 보장/단정으로 해석될 수 있는 표현이 발견되어 '
                     '해당 부분을 삭제했습니다. 실제 투자 판단은 반드시 상품설명서·약관 원문을 확인하시기 바랍니다.')
_NO_EVIDENCE_NOTICE = '\n\n[유의] 검색된 근거 문서가 없어 답변의 신뢰도가 낮을 수 있습니다.'


def apply_output_guardrail(answer: str, hits: list[dict]) -> str:
    """생성된 답변을 반환하기 직전에 검사함.
    1) 수익 보장/투자 권유성 확정 표현이 있는 문장을 제거하고 유의 문구를 덧붙임.
    2) 근거(hits)가 전혀 없는데 이미 '확인되지 않음'류로 스스로 밝히지 않은 경우 근거 부족 경고를 덧붙임."""
    cleaned = answer
    if _RISKY_RE.search(cleaned):
        sentences = re.split(r'(?<=[.!?])\s+|\n', cleaned)
        sentences = [s for s in sentences if s and not _RISKY_RE.search(s)]
        cleaned = ' '.join(sentences).strip() + _RISKY_DISCLAIMER
    if not hits and '확인되지 않음' not in cleaned and '알 수 없' not in cleaned:
        cleaned += _NO_EVIDENCE_NOTICE
    return cleaned


def agentic_ask(question: str, k: int = 5, where: dict | None = None) -> dict:
    """Agentic RAG 루프.
    ★고정된 파이프라인(질의 재작성→검색→생성)이 아니라, 에이전트가 TOOLS에서 검색 알고리즘을
      스스로 고르고, 매 검색 후 결과가 충분한지 스스로 평가해 재검색(최대 MAX_SEARCHES회) 또는
      최종 답변 중 하나를 선택함 — 이 판단 자체가 자기평가(self-evaluation) 루프임.
    반환: {'answer', 'hits'(모든 검색을 합친 근거, 점수순 top-k), 'trace'(도구 호출 기록), 'search_count'}.
    ANTHROPIC_API_KEY가 없으면 bm25_search 1회 + generate()로 폴백함(도구 호출 없이)."""
    refusal = check_input_guardrail(question)
    if refusal is not None:
        return {'answer': refusal, 'hits': [], 'trace': [], 'search_count': 0}

    cache_key = _cache_key(question, k, where)
    cached = _cache_get(cache_key)
    if cached is not None:
        return {**cached, 'cached': True}

    eng = get_engine()
    key = os.getenv('ANTHROPIC_API_KEY')
    if not key:
        hits = eng.search(question, k=k, where=where)
        result = {'answer': apply_output_guardrail(generate(question, hits), hits),
                  'hits': hits, 'trace': [], 'search_count': 0}
        _cache_set(cache_key, result)
        return {**result, 'cached': False}
    import anthropic

    values = meta_values(eng.chunks, FILTER_FIELDS)
    all_tools = _anthropic_tools(values)
    cl = anthropic.Anthropic(api_key=key)
    messages = [{'role': 'user', 'content': question}]
    trace, search_count = [], 0
    hits_by_id: dict[str, dict] = {}   # 검색을 여러 번 해도 최종 답변의 근거로 전부 남게 누적함

    def top_hits():
        return sorted(hits_by_id.values(), key=lambda h: -h['score'])[:k]

    for _ in range(MAX_SEARCHES + 2):   # 검색 최대 MAX_SEARCHES회 + 평가/최종답변 턴 여유
        tools = all_tools if search_count < MAX_SEARCHES else []
        extra = {}
        if tools:
            extra['tools'] = tools
            # 첫 턴은 반드시 검색하게 강제함 — 그 외엔 자기평가로 재검색/답변을 스스로 고름.
            if search_count == 0:
                extra['tool_choice'] = {'type': 'any'}
        r = cl.messages.create(
            model=os.getenv('MODEL', 'claude-sonnet-4-5'), max_tokens=1200,
            system=AGENT_SYSTEM, messages=messages, **extra)
        messages.append({'role': 'assistant', 'content': r.content})
        tool_uses = [b for b in r.content if b.type == 'tool_use']
        if not tool_uses:
            answer = ''.join(b.text for b in r.content if b.type == 'text')
            hits = top_hits()
            result = {'answer': apply_output_guardrail(answer, hits), 'hits': hits,
                      'trace': trace, 'search_count': search_count}
            _cache_set(cache_key, result)
            return {**result, 'cached': False}

        results = []
        for tu in tool_uses:
            tool = TOOLS.get(tu.name)
            if tool is None:
                results.append({'type': 'tool_result', 'tool_use_id': tu.id,
                                 'content': '알 수 없는 도구', 'is_error': True})
                continue
            args = dict(tu.input)
            for f in list(args):   # 해당 도구가 실제로 받은 필드만 검사함(도구마다 필드 구성이 다름)
                if f in values and args[f] not in values[f]:
                    args[f] = None          # 목록 밖 값(환각)은 무시함
            hits = tool['fn'](eng, k=k, manual_where=where, **args)
            search_count += 1
            trace.append({'tool': tu.name, 'args': args, 'result_count': len(hits)})
            for h in hits:
                prev = hits_by_id.get(h['id'])
                if prev is None or h['score'] > prev['score']:
                    hits_by_id[h['id']] = h
            summary = '\n'.join(
                f'[{h["score"]:.3f}] {h["file"]} {h.get("clause_no") or ""} — {h["text"][:200]}'
                for h in hits) or '(검색 결과 없음)'
            results.append({'type': 'tool_result', 'tool_use_id': tu.id, 'content': summary})
        messages.append({'role': 'user', 'content': results})

    # 루프 상한에 도달 — 마지막까지 모은 근거로 마무리 답변을 생성함
    hits = top_hits()
    result = {'answer': apply_output_guardrail(generate(question, hits), hits),
              'hits': hits, 'trace': trace, 'search_count': search_count}
    _cache_set(cache_key, result)
    return {**result, 'cached': False}


# ════════════════════════════════════════════════════════════
# 7. 생성 ─ Claude API
# ════════════════════════════════════════════════════════════
SYSTEM = """당신은 PB(프라이빗뱅커) 상담을 지원하는 어시스턴트임.
제공된 문서 발췌에 근거해서만 답하고, 문서에 없는 내용은 "제공된 문서에서 확인되지 않음"이라고 답할 것.
수익을 단정하는 표현을 쓰지 말 것.

반드시 아래 3단 형식으로 답할 것:
[제안] 한두 문장으로 결론
[근거] 문서 내용을 인용하며 설명
[출처] 문서명과 조항 번호"""


def generate(question: str, hits: list[dict], model: str | None = None) -> str:
    ctx = '\n\n'.join(
        f'--- 발췌 {i+1} | {h["file"]} | {h.get("clause_no") or "-"} | '
        f'개정일 {h.get("revision_date") or "-"}\n{h["text"][:1200]}'
        for i, h in enumerate(hits))
    prompt = f'[문서 발췌]\n{ctx}\n\n[질문]\n{question}'
    try:
        import anthropic
    except ImportError:
        return '(anthropic 패키지 없음 — pip install anthropic)\n\n' + prompt[:1500]
    key = os.getenv('ANTHROPIC_API_KEY')
    if not key:
        return '(ANTHROPIC_API_KEY 미설정 — .env 확인)\n\n' + prompt[:1500]
    cl = anthropic.Anthropic(api_key=key)
    r = cl.messages.create(
        model=model or os.getenv('MODEL', 'claude-sonnet-4-5'),
        max_tokens=1200, system=SYSTEM,
        messages=[{'role': 'user', 'content': prompt}])
    return r.content[0].text


# ════════════════════════════════════════════════════════════
# 8. CLI
# ════════════════════════════════════════════════════════════
_ENGINE = None


def get_engine(strategy='para'):
    global _ENGINE
    if _ENGINE is None:
        p = os.path.join(OUTD, f'chunks_{strategy}.json')
        chunks = json.load(open(p, encoding='utf-8')) if os.path.exists(p) else build_chunks(strategy)
        _ENGINE = Engine(chunks)
    return _ENGINE


def ask(q: str, k=5, where: dict | None = None, show=True):
    result = agentic_ask(q, k=k, where=where)
    if show:
        print('\n' + '=' * 68)
        print('질문:', q)
        for i, t in enumerate(result['trace'], 1):
            print(f'  [검색 {i}/{MAX_SEARCHES}] {t["tool"]}({t["args"]}) → {t["result_count"]}건')
        print('-' * 68)
        for h in result['hits']:
            print(f'  [{h["score"]:.3f}] {h["file"]} {h.get("clause_no") or ""} '
                  f'| {h["text"][:60].strip()}…')
        print('-' * 68)
        print(result['answer'])
    return result['hits'], result['answer']


if __name__ == '__main__':
    import sys
    a = sys.argv[1:]
    if not a or a[0] == 'bootstrap':
        for s in ('fixed', 'para', 'semantic'):
            build_chunks(s)
        eng = get_engine()
        print(f'[색인] 완료 — {len(eng.chunks)}청크')
        ask('A상품 중도해지 수수료율과 근거 조항은?')
    elif a[0] == 'ask':
        ask(' '.join(a[1:]))
    elif a[0] == 'search':
        for h in get_engine().search(' '.join(a[1:]), k=5):
            print(f'[{h["score"]:.3f}] {h["file"]} {h.get("clause_no") or ""}\n    {h["text"][:140]}…')
    else:
        print(__doc__)
