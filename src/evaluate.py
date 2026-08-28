#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hit@k 측정. 실습 3 STEP 3 · 워크샵 1에서 사용함.

질의 파일 형식 (questions/*.csv 또는 xlsx):
    no, 질의, 정답문서          ← 정답문서는 파일명 앞 2자리. 여러 개면 콤마로 구분
사용:
    python3 src/evaluate.py questions/D1_실습3_질의10건_정답문서.xlsx
"""
import sys, os, csv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rag

MODES = ('bm25', 'vector', 'hybrid')


def load(path):
    rows = []
    if path.endswith('.xlsx'):
        from openpyxl import load_workbook
        ws = load_workbook(path).active
        vals = [[c.value for c in r] for r in ws.iter_rows()]
        hdr = None
        for r in vals:
            if r and r[0] == 'No':
                hdr = r
                continue
            if hdr and r and isinstance(r[0], int):
                d = dict(zip(hdr, r))
                q = d.get('질의') or d.get('질문')
                a = d.get('정답 문서')
                if q and a and a != '-':
                    rows.append((d['No'], q, str(a)))
    else:
        for d in csv.DictReader(open(path, encoding='utf-8-sig')):
            if d.get('정답문서', d.get('정답 문서', '-')) != '-':
                rows.append((d['no'], d['질의'], d.get('정답문서') or d['정답 문서']))
    return rows


def main(path, k=5):
    eng = rag.get_engine('para')
    rows = load(path)
    agg = {m: [] for m in MODES}
    print(f'\n질의 {len(rows)}건 · Hit@{k}\n' + '─' * 76)
    for no, q, ans in rows:
        want = set(a.strip() for a in ans.split(','))
        line = f'{str(no):>3}. '
        for m in MODES:
            got = {h['file'][:2] for h in eng.search(q, k=k, mode=m)}
            s = len(want & got) / len(want)
            agg[m].append(s)
            line += f'{m[:3]}={s:.2f} '
        mark = '○' if agg['hybrid'][-1] >= 1 else ('△' if agg['hybrid'][-1] > 0 else '×')
        print(line + f'{mark}  {q[:38]}')
    print('─' * 76)
    for m in MODES:
        print(f'  Hit@{k} [{m:6s}] = {sum(agg[m])/max(len(agg[m]),1):.2f}')
    print('\n※ 이 표를 「검색 방식별 강약 비교표」에 옮겨 적을 것.')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1
         else 'questions/D1_실습3_질의10건_정답문서.xlsx')
