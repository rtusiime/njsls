"""Extract 5-8 NJSLS Science (PEs + foundation box) from the PDF using pdfplumber.

Source: curriculum/Challenges/NJSLS_Standards/NJSLS-Science_5-8.pdf
Output: data/sources/science_58_extracted.json

Approach: for each page, find the foundation table's bbox via pdfplumber, then
crop into 3 vertical columns (SEP/DCI/CCC) using word centerpoints. Outside the
table area, scan plain text for topic headers, PE bullets, and connections.
"""
import json, re
from pathlib import Path
from collections import defaultdict
import pdfplumber

PDF = '/Users/ktusiime/Desktop/DLA/Forge/curriculum/Challenges/NJSLS_Standards/NJSLS-Science_5-8.pdf'
OUT = Path(__file__).parent.parent / 'data' / 'sources' / 'science_58_extracted.json'

# Topic prefix can be a grade digit or a band like MS / 6-8 / 3-5
TOPIC_RE = re.compile(r'^((?:MS|HS|3-5|6-8|9-12|[1-5]))-(PS|LS|ESS|ETS)(\d+):\s*(.+?)(?:\s+Students who demonstrate.*)?$')
PE_RE = re.compile(r'^[•●]?\s*((?:MS|HS|3-5|6-8|9-12|[1-5])-(?:PS|LS|ESS|ETS)\d+-\d+)\s+(.*)$')
PE_CODE_TAG = re.compile(r'\(\s*((?:MS|HS|3-5|6-8|9-12|[1-5])-?(?:PS|LS|ESS|ETS)\d+-?\s*\d+)\s*\)')
DCI_HEADER = re.compile(r'^([A-Z]{2,3}\d+\.[A-Z])\s*:\s*(.+)$')
PE_BULLET = re.compile(r'^[•●]\s*((?:MS|HS|3-5|6-8|9-12|[1-5])-(?:PS|LS|ESS|ETS)\d+-\d+)')

GRADE_HEADERS = {'Grade 5':'5', 'Grade 6':'6', 'Grade 7':'7', 'Grade 8':'8', 'Middle School':'MS'}

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
SUBSECTION_HEADERS = [
    'Connections to Nature of Science',
    'Connections to Engineering, Technology, and Applications of Science',
    'Scientific Knowledge is Based on Empirical Evidence',
    'Scientific Investigations Use a Variety of Methods',
    'Scientific Knowledge Assumes an Order and Consistency in Natural Systems',
    'Science Models, Laws, Mechanisms, and Theories Explain Natural Phenomena',
    'Science is a Way of Knowing',
    'Science is a Human Endeavor',
    'Science Addresses Questions About the Natural and Material World',
    'Interdependence of Science, Engineering, and Technology',
    'Influence of Engineering, Technology, and Science on Society and the Natural World',
]
# Column x-centerpoint thresholds (PDF page width 612)
SEP_MAX = 200
DCI_MAX = 395


def normalize_pe_code(c):
    return c.replace(' ', '-').replace('--', '-')


def normalize_practice(p):
    return 'Planning and Carrying Out Investigations' if p == 'Planning and Carrying out Investigations' else p


def extract_column_lines(page, bbox):
    """Return dict {SEP/DCI/CCC: [text_line_or_blank, ...]}. Blank lines preserved as ''."""
    words = page.extract_words(keep_blank_chars=False)
    table_words = [w for w in words if w['top'] >= bbox[1] and w['top'] < bbox[3]]
    cols = {'SEP': [], 'DCI': [], 'CCC': []}
    for w in table_words:
        cx = (w['x0'] + w['x1']) / 2
        if cx < SEP_MAX:
            cols['SEP'].append(w)
        elif cx < DCI_MAX:
            cols['DCI'].append(w)
        else:
            cols['CCC'].append(w)
    out = {}
    for label, ws in cols.items():
        rows = defaultdict(list)
        for w in ws:
            rows[round(w['top'])].append(w)
        ys = sorted(rows)
        lines = []
        prev_y = None
        for y in ys:
            if prev_y is not None and (y - prev_y) > 14:  # detect blank lines via large y gaps
                lines.append('')
            line = ' '.join(w['text'] for w in sorted(rows[y], key=lambda w: w['x0']))
            lines.append(line)
            prev_y = y
        out[label] = lines
    return out


def lines_to_blocks(lines):
    """Group consecutive non-empty lines into 'blocks' (a block = a paragraph or bullet)."""
    blocks = []
    cur = []
    for ln in lines:
        if ln.strip():
            cur.append(ln.strip())
        else:
            if cur:
                blocks.append(' '.join(cur))
                cur = []
    if cur:
        blocks.append(' '.join(cur))
    return blocks


def split_blocks_by_known_headers(blocks, header_set, alt_header_set=()):
    """blocks is a list of paragraphs (already joined from wrap lines).
    Split into sections by leading header match. A header block may be one paragraph
    or a header that wraps over 2 blocks (rare here since we already joined wraps).
    """
    # Skip column header ("Science and Engineering Practices" etc.) if it's the first block
    sections = []
    cur = None
    for b in blocks:
        bnorm = re.sub(r'\s+', ' ', b).strip()
        matched_header = None
        is_sub = False
        for h in header_set:
            if bnorm == h or bnorm.startswith(h + ' ') or bnorm.startswith(h + ':'):
                matched_header = h
                break
        if not matched_header:
            for h in alt_header_set:
                if bnorm == h or bnorm.startswith(h + ' ') or bnorm.startswith(h + ':'):
                    matched_header = h
                    is_sub = True
                    break
        if matched_header:
            if cur:
                sections.append(cur)
            tail = bnorm[len(matched_header):].lstrip(' :').strip()
            cur = {'header': matched_header, 'tail': tail, 'body': [], 'is_subsection': is_sub}
        else:
            if cur is None:
                # orphan content before any header (e.g., a continuation from prior page)
                cur = {'header': '', 'tail': '', 'body': [], 'is_subsection': False}
            cur['body'].append(b)
    if cur:
        sections.append(cur)
    return sections


def attribute_bullets(blocks):
    """Given list of body blocks for a section, split into (intro_text, bullets[]).
    A bullet is any block ending with one or more (PE-CODE) markers. Intro is the
    block(s) preceding the first bullet, joined into one paragraph.
    """
    intro_parts = []
    bullets = []
    for b in blocks:
        if PE_CODE_TAG.search(b):
            # split this block in case it contains multiple bullets concatenated
            # Split by closing-paren immediately followed by another bullet pattern
            # Simpler: each bullet ends at the LAST PE-code in a contiguous trailing-PE-codes run
            # In practice each block from blank-line splitting IS one bullet.
            codes = [normalize_pe_code(m.group(1)) for m in PE_CODE_TAG.finditer(b)]
            text = PE_CODE_TAG.sub('', b).strip().rstrip(',').strip()
            bullets.append({'text': text, 'pe_codes': codes})
        else:
            if not bullets:
                intro_parts.append(b)
            else:
                # block with no PE code that comes after bullets is unusual; treat as continuation of last bullet
                if bullets:
                    bullets[-1]['text'] = (bullets[-1]['text'] + ' ' + b).strip()
                else:
                    intro_parts.append(b)
    return ' '.join(intro_parts).strip(), bullets


def parse_sep_col(blocks):
    sections = split_blocks_by_known_headers(blocks, SEP_NAMES, SUBSECTION_HEADERS)
    out = []
    for s in sections:
        body = ([s['tail']] if s['tail'] else []) + s['body']
        intro, bullets = attribute_bullets(body)
        out.append({
            'practice': normalize_practice(s['header']),
            'intro': intro,
            'bullets': bullets,
            'is_subsection': s['is_subsection'],
        })
    return out


def parse_ccc_col(blocks):
    sections = split_blocks_by_known_headers(blocks, CCC_NAMES, SUBSECTION_HEADERS)
    out = []
    for s in sections:
        body = ([s['tail']] if s['tail'] else []) + s['body']
        intro, bullets = attribute_bullets(body)
        out.append({
            'concept': s['header'],
            'intro': intro,
            'bullets': bullets,
            'is_subsection': s['is_subsection'],
        })
    return out


def parse_dci_col(blocks):
    """DCI uses dynamic headers (PS1.A: Structure and Properties of Matter, etc.)."""
    sections = []
    cur = None
    for b in blocks:
        bnorm = re.sub(r'\s+', ' ', b).strip()
        m = DCI_HEADER.match(bnorm)
        if m:
            if cur:
                sections.append(cur)
            cur = {'code': m.group(1), 'name': m.group(2).strip(), 'body': []}
        else:
            # subsection labels inside DCI (Connections to Nature of Science, etc.) end the prior DCI section
            sub_match = None
            for h in SUBSECTION_HEADERS:
                if bnorm == h or bnorm.startswith(h + ' '):
                    sub_match = h
                    break
            if sub_match:
                if cur:
                    sections.append(cur)
                cur = {'code': '', 'name': sub_match, 'body': []}
                tail = bnorm[len(sub_match):].strip()
                if tail:
                    cur['body'].append(tail)
            else:
                if cur is None:
                    cur = {'code': '', 'name': '', 'body': []}
                cur['body'].append(b)
    if cur:
        sections.append(cur)
    out = []
    for s in sections:
        intro, bullets = attribute_bullets(s['body'])
        out.append({'code': s['code'], 'name': s['name'], 'intro': intro, 'bullets': bullets})
    return out


def extract_connections_below_table(page, bbox):
    """Connections section sits below the foundation table on the last page of a topic."""
    # crop below bbox, full width
    if bbox[3] >= page.height - 20:
        return []
    cropped = page.crop((0, bbox[3], page.width, page.height - 30))
    txt = cropped.extract_text() or ''
    return parse_connections_text(txt)


def parse_connections_text(txt):
    """Parse the connections section: 'Connections to other DCIs in...', 'Articulation of DCIs across grade levels:',
    'Connections to NJSLS – English Language Arts', 'Connections to NJSLS – Mathematics'.
    """
    if not txt.strip():
        return []
    lines = [l.strip() for l in txt.split('\n')]
    # Drop footer like "January 2022" and "Page X of 200"
    lines = [l for l in lines if not re.match(r'^(New Jersey Department.*|Page \d+ of \d+|January \d{4})', l)]

    sections = []
    cur = None
    for ln in lines:
        if re.match(r'^(Connections to|Articulation of)', ln):
            if cur:
                sections.append(cur)
            cur = {'header': ln.rstrip(':'), 'items_raw': []}
        elif ln.startswith(('•', '●')):
            if cur is None:
                cur = {'header': 'Connections', 'items_raw': []}
            cur['items_raw'].append(ln.lstrip('•●').strip())
        else:
            if cur and cur['items_raw']:
                cur['items_raw'][-1] = cur['items_raw'][-1] + ' ' + ln
            elif cur:
                cur['header'] = (cur['header'] + ' ' + ln).strip()
    if cur:
        sections.append(cur)

    out = []
    for s in sections:
        items = []
        for raw in s['items_raw']:
            codes = [normalize_pe_code(m.group(1)) for m in PE_CODE_TAG.finditer(raw)]
            clean = PE_CODE_TAG.sub('', raw).strip().rstrip(',').strip()
            items.append({'text': clean, 'pe_codes': codes})
        out.append({'header': s['header'], 'items': items})
    return out


def parse_pe_text_block(text, topic):
    """Parse the topic header + PE statements + clarification/AB pairs from page text (above the table)."""
    if not text:
        return
    lines = [l for l in text.split('\n') if l.strip()]
    current_pe = None
    pending_text = []
    for ln in lines:
        ln = ln.strip()
        # PE bullet starts
        m = PE_BULLET.match(ln)
        if m:
            if current_pe and pending_text:
                # flush prior PE text accumulation as clarification/AB if applicable
                _flush_clar_ab(topic, current_pe, pending_text)
                pending_text = []
            current_pe = normalize_pe_code(m.group(1))
            statement = re.sub(r'^[•●]\s*(?:MS|HS|3-5|6-8|9-12|[1-5])-(?:PS|LS|ESS|ETS)\d+-\d+\s+', '', ln)
            if current_pe not in topic['pes']:
                topic['pes'][current_pe] = {
                    'code': current_pe, 'statement': statement,
                    'clarification': '', 'assessment_boundary': '',
                }
            else:
                # multi-line statements get appended
                topic['pes'][current_pe]['statement'] += ' ' + statement
        elif current_pe:
            pending_text.append(ln)
    if current_pe and pending_text:
        _flush_clar_ab(topic, current_pe, pending_text)


def _flush_clar_ab(topic, pe_code, lines):
    text = ' '.join(lines)
    # The lines might also continue a PE statement before brackets start. Extract statement-tail first.
    bracket_start = text.find('[')
    if bracket_start == -1:
        # all continuation of PE statement
        topic['pes'][pe_code]['statement'] += ' ' + text
        topic['pes'][pe_code]['statement'] = topic['pes'][pe_code]['statement'].strip()
        return
    tail = text[:bracket_start].strip()
    if tail:
        topic['pes'][pe_code]['statement'] += ' ' + tail
        topic['pes'][pe_code]['statement'] = topic['pes'][pe_code]['statement'].strip()
    brackets = text[bracket_start:]
    clar = re.search(r'\[Clarification Statement:\s*(.+?)\]\s*(?=\[|$)', brackets, re.S)
    ab = re.search(r'\[Assessment Boundary:\s*(.+?)\]\s*(?=\[|$)', brackets, re.S)
    if clar:
        topic['pes'][pe_code]['clarification'] = clar.group(1).strip()
    if ab:
        topic['pes'][pe_code]['assessment_boundary'] = ab.group(1).strip()


def extract():
    topics = {}  # topic_code -> dict
    current_topic_code = None
    current_grade = None
    pending_foundation_cols = {'SEP': [], 'DCI': [], 'CCC': []}  # accumulates across pages

    def flush_foundation(topic_code):
        if topic_code is None:
            return
        for label in ('SEP', 'DCI', 'CCC'):
            blocks = lines_to_blocks(pending_foundation_cols[label])
            # remove the column header block if present (the first block matching the column title)
            colhead = {'SEP': 'Science and Engineering Practices',
                       'DCI': 'Disciplinary Core Ideas',
                       'CCC': 'Crosscutting Concepts'}[label]
            blocks = [b for b in blocks if b.strip() != colhead]
            if label == 'SEP':
                topics[topic_code]['foundation']['seps'].extend(parse_sep_col(blocks))
            elif label == 'DCI':
                topics[topic_code]['foundation']['dcis'].extend(parse_dci_col(blocks))
            else:
                topics[topic_code]['foundation']['cccs'].extend(parse_ccc_col(blocks))
        for label in pending_foundation_cols:
            pending_foundation_cols[label] = []

    with pdfplumber.open(PDF) as pdf:
        for pn, page in enumerate(pdf.pages):
            txt = page.extract_text() or ''
            lines = txt.split('\n')
            # detect grade header at top of page
            first_line = lines[0].strip() if lines else ''
            if first_line in GRADE_HEADERS:
                current_grade = GRADE_HEADERS[first_line]
                # remove first line so it doesn't pollute later parsing
                lines = lines[1:]

            # detect topic header(s) on this page from the text above the table
            tables = page.find_tables()
            table_bbox = tables[0].bbox if tables else None

            # Above-table text: split text into "above table" and "below table" by y comparing with table bbox
            words = page.extract_words(keep_blank_chars=False)
            above_words = [w for w in words if not table_bbox or w['top'] < table_bbox[1]]
            below_words = [w for w in words if table_bbox and w['top'] >= table_bbox[3]]

            above_lines = _reconstruct_lines(above_words)
            for ln in above_lines:
                lns = ln.strip()
                if lns in GRADE_HEADERS:
                    current_grade = GRADE_HEADERS[lns]
                    continue
                m = TOPIC_RE.match(lns)
                if m:
                    # New topic starts — flush any pending foundation accumulation for the previous topic
                    flush_foundation(current_topic_code)
                    prefix, domain, num, name = m.groups()
                    topic_code = f"{prefix}-{domain}{num}"
                    current_topic_code = topic_code
                    clean_name = re.sub(r'\s*Students who demonstrate.*$', '', name).strip()
                    if topic_code not in topics:
                        topics[topic_code] = {
                            'grade': prefix if prefix in ('MS','HS','3-5','6-8','9-12') else prefix,
                            'code': topic_code, 'name': clean_name, 'pes': {},
                            'foundation': {'seps': [], 'dcis': [], 'cccs': []},
                            'connections_raw': [],
                        }

            # parse PE statements in the above-table region
            if current_topic_code:
                above_text = '\n'.join(above_lines)
                parse_pe_text_block(above_text, topics[current_topic_code])

            # accumulate foundation columns from the table region
            if table_bbox and current_topic_code:
                col_lines = extract_column_lines(page, table_bbox)
                for label, lns in col_lines.items():
                    pending_foundation_cols[label].extend(lns)
                    pending_foundation_cols[label].append('')  # blank-line separator between pages

            # parse connections section below the table
            if table_bbox and current_topic_code:
                conns = extract_connections_below_table(page, table_bbox)
                if conns:
                    # connections signal that this topic is ending on this page → flush foundation
                    flush_foundation(current_topic_code)
                    topics[current_topic_code]['connections_raw'].extend(conns)

    # final flush in case last topic had pending content
    flush_foundation(current_topic_code)
    return topics


def _reconstruct_lines(words, y_tol=3):
    """Group words into text lines, merging words within y_tol of each other onto the same line."""
    if not words:
        return []
    sorted_words = sorted(words, key=lambda w: (w['top'], w['x0']))
    buckets = []  # list of {y_anchor, words}
    for w in sorted_words:
        placed = False
        for b in buckets:
            if abs(w['top'] - b['y']) <= y_tol:
                b['words'].append(w)
                placed = True
                break
        if not placed:
            buckets.append({'y': w['top'], 'words': [w]})
    buckets.sort(key=lambda b: b['y'])
    lines = []
    for b in buckets:
        line = ' '.join(w['text'] for w in sorted(b['words'], key=lambda w: w['x0']))
        lines.append(line)
    return lines


def attribute_to_pes(topics):
    """Slice each topic's foundation bullets down to per-PE views, same as the K-4 extractor."""
    pe_records = []
    for tcode, t in topics.items():
        for pcode, pe in t['pes'].items():
            seps_for_pe = []
            for sep in t['foundation']['seps']:
                bullets = [b for b in sep['bullets'] if pcode in b['pe_codes']]
                if bullets:
                    seps_for_pe.append({
                        'practice': sep['practice'], 'intro': sep['intro'],
                        'bullets': [b['text'] for b in bullets],
                    })
            dcis_for_pe = []
            for dci in t['foundation']['dcis']:
                bullets = [b for b in dci['bullets'] if pcode in b['pe_codes']]
                if bullets:
                    dcis_for_pe.append({
                        'code': dci['code'], 'name': dci['name'],
                        'bullets': [b['text'] for b in bullets],
                    })
            cccs_for_pe = []
            for ccc in t['foundation']['cccs']:
                bullets = [b for b in ccc['bullets'] if pcode in b['pe_codes']]
                if bullets:
                    cccs_for_pe.append({
                        'concept': ccc['concept'], 'intro': ccc.get('intro', ''),
                        'bullets': [b['text'] for b in bullets],
                    })
            connections = []
            for conn in t['connections_raw']:
                items = [i for i in conn['items'] if pcode in i['pe_codes']]
                if items:
                    connections.append({
                        'header': conn['header'],
                        'items': [i['text'] for i in items],
                    })
            pe_records.append({
                'topic_code': tcode, 'topic_name': t['name'], 'grade': t['grade'],
                'code': pe['code'], 'statement': pe['statement'].strip(),
                'clarification': pe['clarification'], 'assessment_boundary': pe['assessment_boundary'],
                'seps': seps_for_pe, 'dcis': dcis_for_pe, 'cccs': cccs_for_pe,
                'connections': connections,
            })
    return pe_records


def main():
    topics = extract()
    pe_records = attribute_to_pes(topics)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, 'w') as f:
        json.dump({'topics': topics, 'pe_records': pe_records}, f, indent=2, ensure_ascii=False)
    print(f"topics: {len(topics)}")
    print(f"PE records: {len(pe_records)}")
    by_grade = {}
    for r in pe_records:
        by_grade.setdefault(r['grade'], []).append(r['code'])
    for g in sorted(by_grade):
        print(f"  grade {g}: {len(by_grade[g])} PEs")
    if pe_records:
        print("\n=== SAMPLE PE (first one) ===")
        print(json.dumps(pe_records[0], indent=2, ensure_ascii=False)[:3500])


if __name__ == '__main__':
    main()
