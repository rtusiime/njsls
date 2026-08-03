#!/usr/bin/env python3
"""Second-pass patch for science_58_extracted.json.

The main extract_science_58.py uses fixed column boundaries (SEP_MAX=200, DCI_MAX=395)
which work for most pages but drop bullets on a handful of pages where the table
layout differs. This script targets ONLY the 16 PEs flagged by audit_science_58.py
and re-extracts their missing SEP/DCI/CCC bullets from the source PDF.

Strategy per problem topic:
  1. Locate the topic's PDF pages.
  2. For each page, find the foundation table bbox.
  3. Detect column x-boundaries dynamically from the column headers
     ("Science and Engineering Practices", "Disciplinary Core Ideas",
      "Crosscutting Concepts").
  4. Re-parse bullets per column.
  5. Attribute bullets to PEs by scanning bullet text for *any* mention of a
     PE code (not just parenthesized) — handles cases where parens straddle a
     line wrap.
  6. Patch only fields that were empty in the original extraction (don't
     overwrite content that's already there).
"""
import json, re
from pathlib import Path
from collections import defaultdict
import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
PDF = '/Users/ktusiime/Desktop/DLA/Forge/curriculum/Challenges/NJSLS_Standards/NJSLS-Science_5-8.pdf'
SRC = ROOT / 'data' / 'sources' / 'science_58_extracted.json'

TOPIC_RE = re.compile(r'^((?:MS|HS|3-5|6-8|9-12|[1-5]))-(PS|LS|ESS|ETS)(\d+):\s*(.+)')
# Any PE-code anywhere in text (parenthesized or bare)
PE_CODE_ANY = re.compile(r'((?:MS|HS|3-5|6-8|9-12|[1-5])-(?:PS|LS|ESS|ETS)\d+-\d+)')
DCI_HEADER = re.compile(r'^([A-Z]{2,3}\d+\.[A-Z])\s*:?\s*(.*)$')

SEP_NAMES = [
    'Asking Questions and Defining Problems',
    'Developing and Using Models',
    'Planning and Carrying Out Investigations',
    'Planning and Carrying out Investigations',
    'Analyzing and Interpreting Data',
    'Using Mathematics and Computational Thinking',
    'Constructing Explanations and Designing Solutions',
    'Engaging in Argument from Evidence',
    'Obtaining, Evaluating, and Communicating Information',
]
CCC_NAMES = [
    'Patterns', 'Cause and Effect', 'Scale, Proportion, and Quantity',
    'Systems and System Models', 'Energy and Matter',
    'Structure and Function', 'Stability and Change',
]


def find_topic_page_ranges(pdf):
    """Return {topic_code: [page_index, ...]} — pages where each topic's content lives."""
    topic_pages = defaultdict(list)
    current = None
    for i, page in enumerate(pdf.pages):
        txt = page.extract_text() or ''
        # Topic header on this page? Look in top 8 lines.
        for ln in txt.splitlines()[:8]:
            m = TOPIC_RE.match(ln.strip())
            if m:
                current = f"{m.group(1)}-{m.group(2)}{m.group(3)}"
                break
        if current:
            topic_pages[current].append(i)
    return topic_pages


def detect_column_boundaries(page, table_bbox):
    """Find x-boundaries of the 3 columns by locating the column header words.
    Headers are "Science and Engineering Practices", "Disciplinary Core Ideas",
    "Crosscutting Concepts". They appear at the top of the table.
    Returns (sep_max, dci_max) — centerpoint thresholds.
    """
    words = page.extract_words()
    # Look near the top of the table bbox
    header_band = [w for w in words if table_bbox[1] <= w['top'] <= table_bbox[1] + 25]
    sci_x = dis_x = cross_x = None
    for w in header_band:
        if w['text'] == 'Science': sci_x = w['x0']
        elif w['text'] == 'Disciplinary': dis_x = w['x0']
        elif w['text'] == 'Crosscutting': cross_x = w['x0']
    # Fall back to fixed boundaries if headers not found (continuation page)
    if dis_x is None or cross_x is None:
        return 230, 405
    # Boundaries placed midway between adjacent header starts
    sep_max = (sci_x + dis_x) / 2 if sci_x else dis_x - 30
    dci_max = (dis_x + cross_x) / 2
    return sep_max, dci_max


def extract_table_lines(page, table_bbox, sep_max, dci_max):
    """Return dict {col: [line_text, ...]} preserving blank-line gaps."""
    words = page.extract_words()
    in_table = [w for w in words if table_bbox[1] <= w['top'] < table_bbox[3]]
    cols = {'SEP': [], 'DCI': [], 'CCC': []}
    for w in in_table:
        cx = (w['x0'] + w['x1']) / 2
        if cx < sep_max: cols['SEP'].append(w)
        elif cx < dci_max: cols['DCI'].append(w)
        else: cols['CCC'].append(w)
    out = {}
    for label, ws in cols.items():
        # Group into lines by rounded y
        rows = defaultdict(list)
        for w in ws:
            rows[round(w['top'])].append(w)
        ys = sorted(rows)
        lines, prev = [], None
        for y in ys:
            if prev is not None and (y - prev) > 14:
                lines.append('')  # blank-line separator
            line = ' '.join(w['text'] for w in sorted(rows[y], key=lambda w: w['x0']))
            lines.append(line)
            prev = y
        out[label] = lines
    return out


def lines_to_blocks(lines):
    blocks, cur = [], []
    for ln in lines:
        if ln.strip():
            cur.append(ln.strip())
        else:
            if cur: blocks.append(' '.join(cur)); cur = []
    if cur: blocks.append(' '.join(cur))
    return blocks


def split_by_headers(blocks, header_names):
    """Split blocks into sections by matching leading header. Returns
    [{header, body: [blocks...]}, ...] including possible orphan {header:'', body:...}."""
    sections, cur = [], None
    for b in blocks:
        bnorm = re.sub(r'\s+', ' ', b).strip()
        matched = None
        for h in header_names:
            if bnorm == h or bnorm.startswith(h + ' ') or bnorm.startswith(h + ':'):
                matched = h; break
        if matched:
            if cur: sections.append(cur)
            tail = bnorm[len(matched):].lstrip(' :').strip()
            cur = {'header': matched, 'body': [tail] if tail else []}
        else:
            if cur is None: cur = {'header': '', 'body': []}
            cur['body'].append(b)
    if cur: sections.append(cur)
    return sections


def split_dci_sections(blocks):
    """DCI uses dynamic headers like 'PS1.A: Structure and Properties of Matter'."""
    sections, cur = [], None
    for b in blocks:
        bnorm = re.sub(r'\s+', ' ', b).strip()
        m = DCI_HEADER.match(bnorm)
        if m and len(m.group(2)) > 3:  # require a name to avoid false positives
            if cur: sections.append(cur)
            cur = {'header': m.group(1), 'name': m.group(2).strip(), 'body': []}
        else:
            if cur is None: cur = {'header': '', 'name': '', 'body': []}
            cur['body'].append(b)
    if cur: sections.append(cur)
    return sections


def attribute_to_pes(body_blocks, valid_pe_codes):
    """For each body block, find any PE codes mentioned and treat the block as
    a bullet attributed to those codes. Strip the codes from the text.
    Returns [{text, pe_codes:[...]}, ...]. Blocks with no PE codes that appear
    after a coded block are attached as continuation of the previous bullet."""
    bullets = []
    intro_parts = []
    for b in body_blocks:
        codes = [c for c in PE_CODE_ANY.findall(b) if c in valid_pe_codes]
        # Clean the text — strip parenthesized PE codes
        clean = re.sub(r'\(\s*(?:MS|HS|3-5|6-8|9-12|[1-5])-(?:PS|LS|ESS|ETS)\d+-\d+\s*\)', '', b)
        # Also strip bare codes that survived (rare — only when not parenthesized)
        clean = re.sub(r'\s*' + PE_CODE_ANY.pattern + r'\s*$', '', clean).strip().rstrip(',').strip()
        if codes:
            bullets.append({'text': clean, 'pe_codes': sorted(set(codes))})
        elif bullets:
            # continuation of prior bullet (continuation might be on a follow-up page)
            bullets[-1]['text'] = (bullets[-1]['text'] + ' ' + clean).strip()
        else:
            intro_parts.append(clean)
    intro = ' '.join(intro_parts).strip()
    return intro, bullets


def split_bullets_on_glyph(text):
    """A single 'block' may pack multiple bullets if blank-line detection failed.
    Split on the NGSS bullet glyph  (Wingdings) when present."""
    if '' not in text:
        return [text]
    parts = [p.strip() for p in text.split('') if p.strip()]
    return parts


def process_topic_pages(pdf, page_indices, valid_pe_codes):
    """Process all pages for one topic; accumulate column lines, then parse."""
    accum = {'SEP': [], 'DCI': [], 'CCC': []}
    for pi in page_indices:
        page = pdf.pages[pi]
        tables = page.find_tables()
        if not tables:
            continue
        bbox = tables[0].bbox
        sep_max, dci_max = detect_column_boundaries(page, bbox)
        cols = extract_table_lines(page, bbox, sep_max, dci_max)
        for label in ('SEP', 'DCI', 'CCC'):
            accum[label].extend(cols[label])
            accum[label].append('')  # blank between pages

    # Drop literal column-header lines from each accumulated column
    headers_to_drop = {
        'SEP': 'Science and Engineering Practices',
        'DCI': 'Disciplinary Core Ideas',
        'CCC': 'Crosscutting Concepts',
    }
    for label, hdr in headers_to_drop.items():
        accum[label] = [ln for ln in accum[label] if hdr not in ln]

    sep_blocks = lines_to_blocks(accum['SEP'])
    dci_blocks = lines_to_blocks(accum['DCI'])
    ccc_blocks = lines_to_blocks(accum['CCC'])

    # Split blocks on bullet glyph to break joined bullets
    sep_blocks = [b for big in sep_blocks for b in split_bullets_on_glyph(big)]
    dci_blocks = [b for big in dci_blocks for b in split_bullets_on_glyph(big)]
    ccc_blocks = [b for big in ccc_blocks for b in split_bullets_on_glyph(big)]

    # Parse sections
    sep_sections = split_by_headers(sep_blocks, SEP_NAMES)
    ccc_sections = split_by_headers(ccc_blocks, CCC_NAMES)
    dci_sections = split_dci_sections(dci_blocks)

    # Build PE -> field bullets
    pe_seps = defaultdict(list)
    pe_dcis = defaultdict(list)
    pe_cccs = defaultdict(list)

    for s in sep_sections:
        if not s['header']: continue
        intro, bullets = attribute_to_pes(s['body'], valid_pe_codes)
        for b in bullets:
            for pc in b['pe_codes']:
                pe_seps[pc].append({
                    'practice': s['header'].replace('Planning and Carrying out Investigations',
                                                  'Planning and Carrying Out Investigations'),
                    'intro': intro,
                    'bullets': [b['text']],
                })

    for s in ccc_sections:
        if not s['header']: continue
        intro, bullets = attribute_to_pes(s['body'], valid_pe_codes)
        for b in bullets:
            for pc in b['pe_codes']:
                pe_cccs[pc].append({
                    'concept': s['header'],
                    'intro': intro,
                    'bullets': [b['text']],
                })

    for s in dci_sections:
        if not s['header']: continue
        intro, bullets = attribute_to_pes(s['body'], valid_pe_codes)
        for b in bullets:
            for pc in b['pe_codes']:
                pe_dcis[pc].append({
                    'code': s['header'],
                    'name': s['name'],
                    'bullets': [b['text']],
                })

    return pe_seps, pe_dcis, pe_cccs


def main():
    data = json.loads(SRC.read_text())
    pe_records = data['pe_records']
    by_code = {pe['code']: pe for pe in pe_records}

    # Find PEs needing patching
    problem_pes = {}
    for pe in pe_records:
        missing = []
        if not pe.get('seps'): missing.append('seps')
        if not pe.get('dcis'): missing.append('dcis')
        if not pe.get('cccs'): missing.append('cccs')
        # Thin DCI single-bullet
        for dci in pe.get('dcis') or []:
            joined = ' '.join([dci.get('name', ''), dci.get('code','')] + (dci.get('bullets') or []))
            if len(joined.strip()) < 30 and 'dcis_thin' not in missing:
                missing.append('dcis_thin')
        if missing:
            problem_pes[pe['code']] = (pe['topic_code'], missing)

    problem_topics = sorted({tc for tc, _ in problem_pes.values()})
    print(f'Patching {len(problem_pes)} PEs across {len(problem_topics)} topics:')
    for pc, (tc, miss) in problem_pes.items():
        print(f'  {pc} ({tc}): {miss}')

    with pdfplumber.open(PDF) as pdf:
        topic_pages = find_topic_page_ranges(pdf)
        all_topic_codes_in_pdf = set(topic_pages.keys())

        patches_applied = []
        for tc in problem_topics:
            if tc not in topic_pages:
                print(f'\n!! Topic {tc} not found in PDF — skipping')
                continue
            page_indices = topic_pages[tc]
            valid_pe_codes = {pe['code'] for pe in pe_records if pe['topic_code'] == tc}
            print(f'\n>>> Re-extracting {tc} from pages {[p+1 for p in page_indices]} (PEs={sorted(valid_pe_codes)})')

            pe_seps, pe_dcis, pe_cccs = process_topic_pages(pdf, page_indices, valid_pe_codes)

            # Apply patches: fill only empty fields
            for pc in valid_pe_codes:
                pe = by_code[pc]
                if not pe.get('seps') and pe_seps.get(pc):
                    pe['seps'] = pe_seps[pc]
                    patches_applied.append(f'{pc}.seps += {len(pe_seps[pc])} sections')
                if not pe.get('dcis') and pe_dcis.get(pc):
                    pe['dcis'] = pe_dcis[pc]
                    patches_applied.append(f'{pc}.dcis += {len(pe_dcis[pc])} sections')
                if not pe.get('cccs') and pe_cccs.get(pc):
                    pe['cccs'] = pe_cccs[pc]
                    patches_applied.append(f'{pc}.cccs += {len(pe_cccs[pc])} sections')
                # Also patch thin DCIs
                existing_dcis = pe.get('dcis') or []
                if existing_dcis:
                    for i, d in enumerate(existing_dcis):
                        joined = ' '.join([d.get('name',''), d.get('code','')] + (d.get('bullets') or []))
                        if len(joined.strip()) < 30 and pe_dcis.get(pc):
                            # Replace whole list with re-extracted
                            pe['dcis'] = pe_dcis[pc]
                            patches_applied.append(f'{pc}.dcis REPLACED (was thin) -> {len(pe_dcis[pc])} sections')
                            break

    print(f'\n{len(patches_applied)} patches applied:')
    for p in patches_applied: print(f'  {p}')

    SRC.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f'\nWrote {SRC}')

    # Re-audit
    print('\n--- Post-patch audit ---')
    still_empty = []
    for pe in pe_records:
        miss = []
        for f in ('seps','dcis','cccs'):
            if not pe.get(f): miss.append(f)
        if miss:
            still_empty.append((pe['code'], miss))
    if still_empty:
        print(f'Still empty after patch ({len(still_empty)}):')
        for c, m in still_empty: print(f'  {c}: {m}')
    else:
        print('All PEs now have SEP+DCI+CCC populated.')


if __name__ == '__main__':
    main()
