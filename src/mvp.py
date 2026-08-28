#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RAG MVP v1 — 워크샵 1 STEP 3. 질문 세트를 끝까지 실행하고 응답을 저장함.

사용:
    python3 src/mvp.py                                  # 기본 질문 세트
    python3 src/mvp.py questions/내_질문세트.xlsx        # 직접 만든 세트
"""
import sys, os, json, csv, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rag
from evaluate import load

OUT = os.path.join(rag.ROOT, 'output')


def run(path, k=None, latest_only=False):
    k = k or int(os.getenv('TOP_K', '5'))
    eng = rag.get_engine('para')
    rows = load(path)
    print(f'질문 {len(rows)}건 실행 — top_k={k}'
          + ('  [최신 개정본만 검색]' if latest_only else ''))
    results = []
    for no, q, ans in rows:
        where = None
        if latest_only:
            # ★Day 2에서 다룰 지점 — 같은 상품의 구버전 약관을 제외함
            where = {}
        hits = eng.search(q, k=k, where=where or None)
        answer = rag.generate(q, hits)
        results.append({'no': no, 'question': q, 'answer_file': ans,
                        'retrieved': [{'file': h['file'], 'clause': h.get('clause_no'),
                                       'rev': h.get('revision_date'),
                                       'score': h['score']} for h in hits],
                        'answer': answer})
        ok = ans and any(h['file'][:2] in ans for h in hits)
        print(f'  {str(no):>3}. {"○" if ok else "×"}  {q[:44]}')
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M')
    jp = os.path.join(OUT, f'mvp_run_{stamp}.json')
    json.dump(results, open(jp, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    cp = os.path.join(OUT, f'mvp_run_{stamp}.csv')
    with open(cp, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['no', '질문', '정답문서', '회수문서', '응답'])
        for r in results:
            w.writerow([r['no'], r['question'], r['answer_file'],
                        ' / '.join(h['file'][:2] for h in r['retrieved']),
                        r['answer']])
    print(f'\n저장: {jp}\n      {cp}')
    print('※ CSV를 열어 응답에 출처가 붙어 있는지 확인할 것 — 워크샵 1 완료 조건임.')
    return results


if __name__ == '__main__':
    a = [x for x in sys.argv[1:] if not x.startswith('-')]
    run(a[0] if a else 'questions/D1_실습3_질의10건_정답문서.xlsx',
        latest_only='--latest' in sys.argv)
