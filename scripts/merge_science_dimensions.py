#!/usr/bin/env python3
"""Merge SEP/DCI/CCC fields from data/sources/science_58_extracted.json
into data/science.json for each existing PE.

Scope:
  - For the 74 PEs already in science.json: copy seps/dcis/cccs from source.
  - MS-ESS3-5: exists in source but not in dst — insert as a full PE record
    (statement stripped of its "• MS-ESS3-5." source prefix). Source has empty
    clarification/AB so those keys are omitted; flagged below as a gap.
  - 15 PEs have at least one empty dimension in source — those land as []
    in dst. Flagged for later, not fixed here.
  - Bullet text is normalised:
      * leading Wingdings glyph (\\uf0a7) stripped from each bullet and intro
      * a single bullet string containing an internal glyph is split into N bullets
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'data' / 'sources' / 'science_58_extracted.json'
DST = ROOT / 'data' / 'science.json'
BULLET_GLYPH = ''


def clean_text(s: str) -> str:
    if not s:
        return s
    s = s.lstrip(BULLET_GLYPH + ' ')
    return s.strip()


def clean_bullets(bullets):
    """Strip leading glyph; split entries that pack multiple bullets via internal glyph."""
    out = []
    for b in bullets or []:
        b = b.strip()
        if not b:
            continue
        parts = [p.strip() for p in b.split(BULLET_GLYPH) if p.strip()]
        out.extend(parts)
    return out


def clean_sep(sep):
    return {
        'practice': sep.get('practice', ''),
        'intro': clean_text(sep.get('intro', '')),
        'bullets': clean_bullets(sep.get('bullets')),
    }


def clean_dci(dci):
    return {
        'code': dci.get('code', ''),
        'name': dci.get('name', ''),
        'bullets': clean_bullets(dci.get('bullets')),
    }


def clean_ccc(ccc):
    return {
        'concept': ccc.get('concept', ''),
        'intro': clean_text(ccc.get('intro', '')),
        'bullets': clean_bullets(ccc.get('bullets')),
    }


def strip_code_prefix(statement: str, code: str) -> str:
    """Remove leading '• <code>. ' or '• <code> ' artifacts from the extracted statement."""
    s = statement.lstrip()
    s = re.sub(r'^•\s*' + re.escape(code) + r'\.?\s*', '', s)
    return s.strip()


def build_pe_record_from_src(src_pe):
    """Construct a dst-shaped PE record from a src record (for MS-ESS3-5 insertion)."""
    code = src_pe['code']
    out = {
        'code': code,
        'statement': strip_code_prefix(src_pe.get('statement', ''), code),
    }
    if src_pe.get('clarification'):
        out['clarification'] = src_pe['clarification']
    if src_pe.get('assessment_boundary'):
        out['assessment_boundary'] = src_pe['assessment_boundary']
    out['seps'] = [clean_sep(s) for s in src_pe.get('seps') or []]
    out['dcis'] = [clean_dci(d) for d in src_pe.get('dcis') or []]
    out['cccs'] = [clean_ccc(c) for c in src_pe.get('cccs') or []]
    return out


def main():
    src = json.loads(SRC.read_text())
    dst = json.loads(DST.read_text())

    src_by_code = {pe['code']: pe for pe in src['pe_records']}
    dst_codes = set()

    merged = 0
    inserted = []
    empty_dim_pes = []   # PEs with at least one empty dimension
    not_in_src = []      # PEs in dst but not in src

    for disc_key, disc in dst.items():
        for topic in disc.get('topics', []):
            for pe in topic.get('pes', []):
                code = pe['code']
                dst_codes.add(code)
                src_pe = src_by_code.get(code)
                if not src_pe:
                    not_in_src.append(code)
                    pe['seps'] = []
                    pe['dcis'] = []
                    pe['cccs'] = []
                    continue
                pe['seps'] = [clean_sep(s) for s in src_pe.get('seps') or []]
                pe['dcis'] = [clean_dci(d) for d in src_pe.get('dcis') or []]
                pe['cccs'] = [clean_ccc(c) for c in src_pe.get('cccs') or []]
                merged += 1
                missing = [k for k in ('seps', 'dcis', 'cccs') if not pe[k]]
                if missing:
                    empty_dim_pes.append((code, missing))

    # Insert any PEs that exist in src but not in dst. For Session N, this is
    # just MS-ESS3-5; general logic so future extractor wins are absorbable.
    src_only = sorted(set(src_by_code) - dst_codes)
    for code in src_only:
        src_pe = src_by_code[code]
        topic_code = src_pe.get('topic_code')
        # Locate the matching topic in dst
        target_topic = None
        for disc in dst.values():
            for topic in disc.get('topics', []):
                if topic.get('code') == topic_code:
                    target_topic = topic
                    break
            if target_topic:
                break
        if not target_topic:
            print(f'!! Could not find topic {topic_code} in dst for {code} — skipping insert.')
            continue
        new_pe = build_pe_record_from_src(src_pe)
        target_topic['pes'].append(new_pe)
        # Sort PEs in this topic by numeric suffix so MS-ESS3-5 lands after -4
        target_topic['pes'].sort(key=lambda p: int(p['code'].rsplit('-', 1)[-1]))
        inserted.append((code, topic_code))
        missing = [k for k in ('seps', 'dcis', 'cccs') if not new_pe.get(k)]
        if missing:
            empty_dim_pes.append((code, missing))

    print(f'Merged dimensions into {merged} existing PEs.')
    if inserted:
        print(f'Inserted {len(inserted)} new PE(s):')
        for code, tc in inserted:
            print(f'  {code} into topic {tc}')
    print(f'\nPEs with at least one empty dimension ({len(empty_dim_pes)}):')
    for code, miss in empty_dim_pes:
        print(f'  {code}: empty {miss}')
    if not_in_src:
        print(f'\nPEs in science.json but not in extracted source: {not_in_src}')

    DST.write_text(json.dumps(dst, indent=2, ensure_ascii=False) + '\n')
    print(f'\nWrote {DST}')


if __name__ == '__main__':
    main()
