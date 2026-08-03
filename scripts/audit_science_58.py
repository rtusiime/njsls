#!/usr/bin/env python3
"""Audit which PE records in science_58_extracted.json have empty/suspiciously-short
SEP, DCI, or CCC arrays. Outputs a sorted list grouped by issue so we know exactly
which pages of the source PDF need re-extraction with adjusted column boundaries."""
import json, sys, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'data' / 'sources' / 'science_58_extracted.json'

# A "bullet" or "intro" is considered too thin if its joined text is shorter than this
MIN_TEXT_LEN = 25

def bullet_text(b):
    """Return joined text of an SEP/DCI/CCC item for length sanity checks."""
    if isinstance(b, str):
        return b
    parts = []
    for k in ('intro', 'practice', 'concept', 'name', 'code'):
        v = b.get(k)
        if v: parts.append(str(v))
    for bl in b.get('bullets', []) or []:
        parts.append(str(bl))
    return ' '.join(parts).strip()

def main():
    d = json.loads(SRC.read_text())
    issues = []
    for pe in d['pe_records']:
        code = pe['code']
        row = {'code': code, 'topic': pe['topic_code'], 'grade': pe['grade'], 'problems': []}
        for field in ('seps', 'dcis', 'cccs'):
            arr = pe.get(field) or []
            if not arr:
                row['problems'].append(f'{field}: EMPTY')
            else:
                # Check for items with bullets but no content, or content shorter than threshold
                thin = []
                for i, item in enumerate(arr):
                    t = bullet_text(item)
                    if len(t) < MIN_TEXT_LEN:
                        thin.append(f'{field}[{i}] len={len(t)} "{t[:40]}"')
                if thin:
                    row['problems'].append(f'{field}: thin -> {"; ".join(thin)}')
        if row['problems']:
            issues.append(row)

    print(f'Total PE records: {len(d["pe_records"])}')
    print(f'PE records with issues: {len(issues)}\n')

    # Group by topic so we see page clusters
    by_topic = {}
    for r in issues:
        by_topic.setdefault(r['topic'], []).append(r)
    for topic in sorted(by_topic):
        print(f'--- {topic} ({len(by_topic[topic])} PEs) ---')
        for r in by_topic[topic]:
            print(f'  {r["code"]}:')
            for p in r['problems']:
                print(f'    {p}')
        print()

    # Summary counts
    n_empty = {'seps':0,'dcis':0,'cccs':0}
    n_thin  = {'seps':0,'dcis':0,'cccs':0}
    for r in issues:
        for p in r['problems']:
            for f in n_empty:
                if p.startswith(f'{f}: EMPTY'): n_empty[f] += 1
                elif p.startswith(f'{f}: thin'): n_thin[f] += 1
    print('Summary:')
    for f in ('seps','dcis','cccs'):
        print(f'  {f}: {n_empty[f]} empty, {n_thin[f]} thin')

if __name__ == '__main__':
    main()
