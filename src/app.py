#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RAG 파이프라인 테스트용 간이 웹 UI. `python3 src/app.py` 로 실행함."""
from flask import Flask, request, jsonify, Response
import rag

app = Flask(__name__)

INDEX_HTML = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>금융 PB Copilot — RAG 테스트</title>
<style>
  :root {
    --bg: #f5f5f7; --panel: #ffffff; --border: rgba(0,0,0,0.07);
    --text: #1d1d1f; --muted: #86868b; --accent: #0071e3; --accent-soft: rgba(0,113,227,0.1);
    --red: #ff3b30; --radius: 18px;
    --shadow: 0 1px 2px rgba(0,0,0,0.04), 0 6px 24px rgba(0,0,0,0.05);
  }
  :root[data-theme="dark"] {
    --bg: #000000; --panel: #1c1c1e; --border: rgba(255,255,255,0.09);
    --text: #f5f5f7; --muted: #98989d; --accent: #2997ff; --accent-soft: rgba(41,151,255,0.16);
    --red: #ff453a;
    --shadow: 0 1px 2px rgba(0,0,0,0.3), 0 6px 24px rgba(0,0,0,0.35);
  }
  body { transition: background .2s, color .2s; }
  .theme-toggle {
    position: fixed; top: 24px; left: 24px; z-index: 50;
    width: 40px; height: 40px; border-radius: 50%; padding: 0;
    background: var(--panel); color: var(--text); border: 1px solid var(--border);
    box-shadow: var(--shadow); font-size: 17px; display: flex;
    align-items: center; justify-content: center; line-height: 1;
  }
  .theme-toggle:hover { opacity: 1; transform: scale(1.06); }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 56px 20px 80px; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Apple SD Gothic Neo",
                 "Malgun Gothic", sans-serif;
    -webkit-font-smoothing: antialiased;
  }
  .wrap { max-width: 720px; margin: 0 auto; }
  header { margin-bottom: 32px; }
  h1 {
    font-size: 30px; font-weight: 700; letter-spacing: -0.02em; margin: 0 0 6px;
  }
  .sub { color: var(--muted); font-size: 15px; line-height: 1.5; }
  .panel {
    background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius);
    box-shadow: var(--shadow); padding: 24px 26px; margin-bottom: 18px;
  }
  textarea {
    width: 100%; min-height: 64px; resize: vertical; padding: 12px 14px;
    border: 1px solid var(--border); border-radius: 12px; font-size: 15px;
    font-family: inherit; background: var(--bg); color: var(--text);
    transition: box-shadow .15s, border-color .15s;
  }
  textarea:focus {
    outline: none; border-color: var(--accent); box-shadow: 0 0 0 4px var(--accent-soft);
  }
  .row { display: flex; gap: 12px; margin-top: 14px; align-items: center; flex-wrap: wrap; }
  button {
    background: var(--accent); color: #fff; border: none; border-radius: 980px;
    padding: 10px 22px; font-size: 15px; font-weight: 500; cursor: pointer;
    transition: opacity .15s, transform .1s;
  }
  button:hover { opacity: 0.88; }
  button:active { transform: scale(0.97); }
  button:disabled { opacity: 0.4; cursor: default; transform: none; }
  label { font-size: 12.5px; color: var(--muted); font-weight: 500; }
  select {
    padding: 8px 12px; border-radius: 10px; border: 1px solid var(--border);
    background: var(--panel); color: var(--text); font-size: 14px; font-family: inherit;
  }
  .seg { display: inline-flex; background: var(--bg); border-radius: 10px; padding: 3px; gap: 2px; }
  .seg-btn {
    border: none; background: transparent; color: var(--text); font-size: 13.5px;
    padding: 6px 14px; border-radius: 8px; cursor: pointer; font-weight: 500;
    transition: background .15s, color .15s, box-shadow .15s;
  }
  .seg-btn.active { background: var(--panel); box-shadow: var(--shadow); color: var(--accent); }
  .filters { display: flex; gap: 16px; flex-wrap: wrap; }
  .filter-item { display: flex; flex-direction: column; gap: 5px; }
  h2 {
    font-size: 12.5px; color: var(--muted); margin: 0 0 14px; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.04em;
  }
  .hit {
    border: 1px solid var(--border); border-radius: 14px; padding: 14px 16px;
    margin-bottom: 10px; font-size: 13.5px; background: var(--bg);
    transition: box-shadow .15s, transform .1s;
  }
  .hit.clickable { cursor: pointer; }
  .hit.clickable:hover { box-shadow: var(--shadow); }
  .hit .meta { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; }
  .badge {
    background: var(--accent-soft); color: var(--accent); border-radius: 980px;
    padding: 3px 10px; font-size: 11.5px; font-weight: 600;
  }
  .badge.muted { background: var(--panel); color: var(--muted); border: 1px solid var(--border); }
  .hit .text { color: var(--text); opacity: 0.88; white-space: pre-wrap; line-height: 1.55; }
  .answer { white-space: pre-wrap; line-height: 1.7; font-size: 15px; }
  .empty { color: var(--muted); font-size: 13.5px; }
  .error { color: var(--red); font-size: 13.5px; }
  .spinner { font-size: 13px; color: var(--muted); }
  .hist-detail {
    display: none; margin-top: 12px; border-top: 1px solid var(--border); padding-top: 12px;
  }
  .hist-detail.open { display: block; }
  .hist-hit { font-size: 12.5px; margin-bottom: 6px; opacity: 0.85; }
  .hist-answer { margin-top: 10px; white-space: pre-wrap; font-size: 13px; line-height: 1.5; }
</style>
</head>
<body>
<button id="themeToggle" class="theme-toggle" onclick="toggleTheme()" title="라이트/다크 모드 전환">🌙</button>
<div class="wrap">
  <header>
    <h1>금융 PB Copilot</h1>
    <div class="sub">에이전트가 검색 도구를 스스로 골라 쓰고, 결과가 부족하면 스스로 판단해 다시 검색합니다(최대 <span id="maxSearches">2</span>회).</div>
  </header>

  <div class="panel">
    <h2>검색 도구 <span id="toolCount" class="badge muted">0</span></h2>
    <div id="tools" class="empty">불러오는 중…</div>
  </div>

  <div class="panel">
    <textarea id="q" placeholder="예: 나루 ELS 제417회의 중도해지 수수료율은?"></textarea>
    <div class="row">
      <label>Top K</label>
      <div class="seg" id="kSeg">
        <button type="button" class="seg-btn" data-k="3">3</button>
        <button type="button" class="seg-btn active" data-k="5">5</button>
        <button type="button" class="seg-btn" data-k="8">8</button>
        <button type="button" class="seg-btn" data-k="10">10</button>
      </div>
      <button id="btn" onclick="ask()">질문하기</button>
      <span id="status" class="spinner"></span>
    </div>
  </div>

  <div class="panel">
    <h2>메타데이터 필터</h2>
    <div id="filters" class="filters"></div>
  </div>

  <div class="panel">
    <h2>검색된 근거 · Top K</h2>
    <div id="agentTrace" style="display:none; margin-bottom:12px;"></div>
    <div id="hits" class="empty">아직 질문하지 않았습니다.</div>
  </div>

  <div class="panel">
    <h2>생성된 답변</h2>
    <div id="answer" class="empty">아직 질문하지 않았습니다.</div>
  </div>

  <div class="panel">
    <h2>검색 히스토리 <span id="histCount" class="badge muted">0</span></h2>
    <div class="sub" style="margin-bottom:12px;">항목을 클릭하면 그때의 근거·답변을 펼쳐서 비교할 수 있습니다.</div>
    <div id="history" class="empty">아직 기록이 없습니다.</div>
  </div>
</div>

<script>
function applyTheme(t) {
  document.documentElement.setAttribute('data-theme', t);
  document.getElementById('themeToggle').textContent = t === 'dark' ? '☀️' : '🌙';
  localStorage.setItem('theme', t);
}

function toggleTheme() {
  const cur = document.documentElement.getAttribute('data-theme') || 'light';
  applyTheme(cur === 'dark' ? 'light' : 'dark');
}

applyTheme(localStorage.getItem('theme')
  || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'));

const FIELD_LABEL = {
  product_id: '상품코드', doc_type: '문서유형', revision_date: '개정일',
  risk_grade: '위험등급', clause_no: '조항', target_segment: '대상세그먼트'
};
let HISTORY = [];

async function loadMeta() {
  const res = await fetch('/api/meta');
  const meta = await res.json();
  const el = document.getElementById('filters');
  el.innerHTML = Object.entries(meta).map(([field, values]) => `
    <div class="filter-item">
      <label>${FIELD_LABEL[field] || field}</label>
      <select id="f_${field}">
        <option value="">전체</option>
        ${values.map(v => `<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`).join('')}
      </select>
    </div>
  `).join('');
}

async function loadTools() {
  const res = await fetch('/api/tools');
  const data = await res.json();
  document.getElementById('maxSearches').textContent = data.max_searches;
  document.getElementById('toolCount').textContent = data.tools.length;
  document.getElementById('tools').innerHTML = data.tools.map(t => `
    <div class="hit">
      <div class="meta"><span class="badge">${escapeHtml(t.name)}</span></div>
      <div class="text">${escapeHtml(t.description)}</div>
    </div>
  `).join('');
}

function formatToolArgs(args) {
  const parts = [];
  if (args.query) parts.push(`검색어=${args.query}`);
  if (args.queries) parts.push(`검색어 변형=[${args.queries.join(', ')}]`);
  const filters = formatFilters({product_id: args.product_id, doc_type: args.doc_type, revision_date: args.revision_date});
  if (filters) parts.push(filters);
  return parts.join(' · ');
}

function formatTrace(trace) {
  return (trace || []).map((t, i) =>
    `<div style="margin-bottom:4px;"><span class="badge">검색 ${i + 1}</span> ` +
    `<span class="badge muted">${escapeHtml(t.tool)}</span> ${escapeHtml(formatToolArgs(t.args))} → ${t.result_count}건</div>`
  ).join('');
}

function getK() {
  return Number(document.querySelector('#kSeg .seg-btn.active').dataset.k);
}

document.getElementById('kSeg').addEventListener('click', e => {
  const btn = e.target.closest('.seg-btn');
  if (!btn) return;
  document.querySelectorAll('#kSeg .seg-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
});

function collectWhere() {
  const where = {};
  document.querySelectorAll('#filters select').forEach(sel => {
    if (sel.value) where[sel.id.slice(2)] = sel.value;
  });
  return where;
}

function formatFilters(filters) {
  return Object.entries(filters || {}).map(([k, v]) => `${FIELD_LABEL[k] || k}=${v}`).join(', ');
}

function renderHistory() {
  const el = document.getElementById('history');
  document.getElementById('histCount').textContent = HISTORY.length;
  if (!HISTORY.length) { el.innerHTML = '<div class="empty">아직 기록이 없습니다.</div>'; return; }
  el.innerHTML = HISTORY.map((h, i) => {
    const manualStr = formatFilters(h.where);
    const top = h.hits[0];
    const topSummary = top ? `${top.file} ${top.clause_no || ''} (score ${top.score.toFixed(3)})` : '결과 없음';
    return `
      <div class="hit clickable" onclick="toggleHist(${i})">
        <div class="meta">
          <span class="badge">#${HISTORY.length - i}</span>
          <span class="badge muted">k=${h.k}</span>
          <span class="badge muted">검색 ${h.searchCount}회</span>
          ${manualStr ? `<span class="badge muted">수동 필터: ${escapeHtml(manualStr)}</span>` : ''}
        </div>
        <div class="text"><b>${escapeHtml(h.q)}</b><br>Top1: ${escapeHtml(topSummary)}</div>
        <div id="hist_detail_${i}" class="hist-detail">
          ${formatTrace(h.trace)}
          ${h.hits.map(x => `<div class="hist-hit">
            [${x.score.toFixed(3)}] ${escapeHtml(x.file)} ${escapeHtml(x.clause_no || '')}
            — ${escapeHtml(x.text.slice(0, 80))}…</div>`).join('')}
          <div class="hist-answer">${escapeHtml(h.answer)}</div>
        </div>
      </div>
    `;
  }).join('');
}

function toggleHist(i) {
  document.getElementById(`hist_detail_${i}`).classList.toggle('open');
}

async function ask() {
  const q = document.getElementById('q').value.trim();
  const k = getK();
  const where = collectWhere();
  const btn = document.getElementById('btn');
  const status = document.getElementById('status');
  const hitsEl = document.getElementById('hits');
  const answerEl = document.getElementById('answer');
  if (!q) { return; }

  btn.disabled = true;
  status.textContent = '검색 중…';
  hitsEl.innerHTML = '';
  answerEl.innerHTML = '';

  try {
    const res = await fetch('/api/ask', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({question: q, k: Number(k), where})
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || '요청 실패');

    if (!data.hits.length) {
      hitsEl.innerHTML = '<div class="empty">검색된 청크가 없습니다.</div>';
    } else {
      hitsEl.innerHTML = data.hits.map(h => `
        <div class="hit">
          <div class="meta">
            <span class="badge">score ${h.score.toFixed(3)}</span>
            <span class="badge muted">${h.file}</span>
            ${h.clause_no ? `<span class="badge muted">${h.clause_no}</span>` : ''}
            ${h.revision_date ? `<span class="badge muted">개정 ${h.revision_date}</span>` : ''}
          </div>
          <div class="text">${escapeHtml(h.text)}</div>
        </div>
      `).join('');
    }
    answerEl.innerHTML = `<div class="answer">${escapeHtml(data.answer)}</div>`;

    const traceEl = document.getElementById('agentTrace');
    if (data.trace && data.trace.length) {
      traceEl.style.display = 'block';
      traceEl.innerHTML =
        `<div style="margin-bottom:6px;">에이전트 검색 로그 (${data.search_count}/${document.getElementById('maxSearches').textContent}회):</div>` +
        formatTrace(data.trace);
    } else {
      traceEl.style.display = 'none';
      traceEl.innerHTML = '';
    }

    HISTORY.unshift({
      q, k: Number(k), where, hits: data.hits, answer: data.answer,
      trace: data.trace, searchCount: data.search_count,
    });
    renderHistory();
  } catch (e) {
    answerEl.innerHTML = `<div class="error">오류: ${escapeHtml(e.message)}</div>`;
  } finally {
    btn.disabled = false;
    status.textContent = '';
  }
}

function escapeHtml(s) {
  return (s || '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

document.getElementById('q').addEventListener('keydown', e => {
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) ask();
});

loadMeta();
loadTools();
</script>
</body>
</html>
"""


@app.route('/')
def index():
    return Response(INDEX_HTML, mimetype='text/html')


@app.route('/api/meta')
def api_meta():
    return jsonify(rag.meta_values(rag.get_engine().chunks))


@app.route('/api/tools')
def api_tools():
    return jsonify({'tools': rag.list_tools(), 'max_searches': rag.MAX_SEARCHES})


@app.route('/api/ask', methods=['POST'])
def api_ask():
    data = request.get_json(force=True) or {}
    q = (data.get('question') or '').strip()
    k = int(data.get('k') or 5)
    ui_where = {f: v for f, v in (data.get('where') or {}).items() if v}
    if not q:
        return jsonify({'error': '질문을 입력하세요.'}), 400
    result = rag.agentic_ask(q, k=k, where=ui_where or None)
    return jsonify({
        'hits': result['hits'], 'answer': result['answer'],
        'trace': result['trace'], 'search_count': result['search_count'],
    })


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5050, debug=False)
