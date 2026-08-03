"""Extract K-4 NJSLS Science (PEs + foundation box) from the docx.

Source: /Users/ktusiime/Desktop/DLA/Forge/curriculum/NJSLS-Science_K-12.docx
Output: data/sources/science_k4_extracted.json

The docx claims "K-12" in the filename but only contains K-4. The 5-8 PDF
is handled by a separate extractor.
"""
import json, re, zipfile, sys
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
W = NS['w']

DOCX = '/Users/ktusiime/Desktop/DLA/Forge/curriculum/NJSLS-Science_K-12.docx'
OUT = Path(__file__).parent.parent / 'data' / 'sources' / 'science_k4_extracted.json'

# K-4 topic codes look like: K-PS2, 1-LS3, 2-ESS2, 3-PS3, 4-ESS1, K-2-ETS1, 3-5-ETS1
# Topic header — name may run on into the next sentence ("Students who demonstrate..."), so name capture is non-greedy and we trim later.
TOPIC_RE = re.compile(r'^((?:K-2|3-5|K|[1-5]))-(PS|LS|ESS|ETS)(\d+):\s*(.+?)(?:\s+Students who demonstrate.*)?$')
PE_RE = re.compile(r'^[•●]\s*((?:K-2|3-5|K|[1-5])-(?:PS|LS|ESS|ETS)\d+-\d+)\s+(.*)$')
PE_CODE_TAG = re.compile(r'\(\s*((?:K-2|3-5|K|[1-5])-?(?:PS|LS|ESS|ETS)\d+-?\s*\d+)\s*\)')
DCI_HEADER = re.compile(r'^([A-Z]{2,3}\d+\.[A-Z])\s*:\s*(.+)$')

GRADE_HEADERS = {'Kindergarten':'K', 'Grade 1':'1', 'Grade 2':'2', 'Grade 3':'3', 'Grade 4':'4', 'Grade 5':'5'}

# Fixed NGSS practice / crosscutting names — gives us deterministic header detection.
SEP_NAMES = [
    'Asking Questions and Defining Problems',
    'Developing and Using Models',
    'Planning and Carrying Out Investigations',
    'Planning and Carrying out Investigations',  # casing variant in source
    'Analyzing and Interpreting Data',
    'Using Mathematics and Computational Thinking',
    'Constructing Explanations and Designing Solutions',
    'Engaging in Argument from Evidence',
    'Obtaining, Evaluating, and Communicating Information',
]
CCC_NAMES = [
    'Patterns',
    'Cause and Effect',
    'Scale, Proportion, and Quantity',
    'Systems and System Models',
    'Energy and Matter',
    'Structure and Function',
    'Stability and Change',
]
# Subsection labels that appear inside SEP/DCI/CCC cells — treat as section breaks
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

def normalize_practice(p):
    p = p.strip()
    return 'Planning and Carrying Out Investigations' if p == 'Planning and Carrying out Investigations' else p


def text_of(elem):
    return ''.join(t.text or '' for t in elem.iter(f'{{{W}}}t'))


def normalize_pe_code(c):
    """Some bullets have stray spaces in PE-code parens like 'K PS2-1' or 'K-PS2- 1'."""
    return c.replace(' ', '-').replace('--', '-')


def cell_paragraphs(cell):
    """Return list of stripped paragraph text in a table cell, dropping blanks."""
    out = []
    for p in cell.iter(f'{{{W}}}p'):
        t = text_of(p).strip()
        if t:
            out.append(t)
    return out


def split_bullets_by_pe(paragraphs, bullet_chars=('▪', '•', '●', '○')):
    """Given a list of paragraph strings, group consecutive lines into 'bullets'.
    A bullet starts with one of the bullet chars; continuation lines (no bullet) get appended.
    Returns list of {text, pe_codes} where pe_codes are extracted from trailing (CODE) tags.
    """
    bullets = []
    cur = None
    for para in paragraphs:
        if any(para.startswith(b) for b in bullet_chars):
            if cur is not None:
                bullets.append(cur)
            cur = para.lstrip(''.join(bullet_chars)).strip()
        else:
            if cur is not None:
                cur = cur + ' ' + para.strip()
    if cur is not None:
        bullets.append(cur)

    enriched = []
    for b in bullets:
        codes = [normalize_pe_code(m.group(1)) for m in PE_CODE_TAG.finditer(b)]
        # strip the trailing PE code tags from the text
        clean = PE_CODE_TAG.sub('', b).strip().rstrip(',').strip()
        enriched.append({'text': clean, 'pe_codes': codes})
    return enriched


def _split_by_known_headers(paras, header_set, alt_header_set=()):
    """Walk a list of paragraph strings; each time we encounter a paragraph whose CONCATENATION
    with subsequent paragraphs forms a known header, start a new section. Returns list of
    {header: str, body_paras: [...]}. Headers in alt_header_set start sections too but
    are flagged with is_subsection=True.
    """
    # Detect headers by matching prefix-of-concatenation against header_set/alt_header_set.
    sections = []
    cur = {'header': '', 'body_paras': [], 'is_subsection': False}
    bullet_chars = ('▪', '•', '●', '○')

    i = 0
    while i < len(paras):
        p = paras[i]
        if any(p.startswith(b) for b in bullet_chars):
            cur['body_paras'].append(p)
            i += 1
            continue

        # Try to match a header that may span 1-3 paragraphs (titles wrap)
        matched = None
        is_sub = False
        for k in (3, 2, 1):
            if i + k > len(paras):
                continue
            joined = ' '.join(paras[i:i+k]).strip()
            joined_norm = re.sub(r'\s+', ' ', joined)
            for h in header_set:
                if joined_norm.startswith(h):
                    matched = (h, k)
                    break
            if matched:
                break
            for h in alt_header_set:
                if joined_norm.startswith(h):
                    matched = (h, k); is_sub = True
                    break
            if matched:
                break

        if matched:
            h, k = matched
            if cur['header'] or cur['body_paras']:
                sections.append(cur)
            cur = {'header': h, 'body_paras': [], 'is_subsection': is_sub}
            # Tail of joined past header (e.g., header text + same-paragraph extra) goes to body
            joined = ' '.join(paras[i:i+k]).strip()
            tail = joined[len(h):].strip()
            if tail:
                cur['body_paras'].append(tail)
            i += k
        else:
            # non-bullet paragraph that didn't match a known header → intro/continuation text
            cur['body_paras'].append(p)
            i += 1

    if cur['header'] or cur['body_paras']:
        sections.append(cur)
    return sections


def parse_sep_cell(cell):
    """SEP cell: blocks keyed by one of the 8 NGSS practice names.
    Each block: practice name (header), optional grade-band intro (descriptive paragraph), bullets.
    Subsections like 'Connections to Nature of Science' end the practice block.
    """
    paras = cell_paragraphs(cell)
    if not paras:
        return []
    sections = _split_by_known_headers(paras, SEP_NAMES, SUBSECTION_HEADERS)

    out = []
    for s in sections:
        if not s['header'] and not s['body_paras']:
            continue
        bullet_chars = ('▪', '•', '●', '○')
        intro_paras = [p for p in s['body_paras'] if not any(p.startswith(b) for b in bullet_chars)]
        bullet_paras = [p for p in s['body_paras'] if any(p.startswith(b) for b in bullet_chars)]
        out.append({
            'practice': normalize_practice(s['header']) if s['header'] in SEP_NAMES else s['header'],
            'intro': ' '.join(intro_paras).strip(),
            'bullets': split_bullets_by_pe(bullet_paras),
            'is_subsection': s['is_subsection'],
        })
    return out


def parse_dci_cell(cell):
    """DCI cell: 'PS2.A: Forces and Motion' header, then bullets under it. Repeat for each DCI.
    May end with 'Connections to Engineering, Technology, and Applications of Science' or NoS subsections.
    """
    paras = cell_paragraphs(cell)
    sections = []
    cur = None
    bullet_chars = ('▪', '•', '●', '○')
    for p in paras:
        m = DCI_HEADER.match(p)
        if m:
            if cur:
                sections.append(cur)
            cur = {'code': m.group(1), 'name': m.group(2).strip(), 'bullets_paras': []}
        elif any(p.startswith(b) for b in bullet_chars):
            if cur is None:
                # bullet without a header — orphan, attach to a synthetic section
                cur = {'code': '', 'name': '', 'bullets_paras': []}
            cur['bullets_paras'].append(p)
        else:
            # could be a subsection like "Connections to Engineering..."
            if cur:
                sections.append(cur)
            cur = {'code': '', 'name': p, 'bullets_paras': []}
    if cur:
        sections.append(cur)

    out = []
    for s in sections:
        bullets = split_bullets_by_pe(s['bullets_paras'])
        out.append({
            'code': s['code'],
            'name': s['name'],
            'bullets': bullets,
        })
    return out


def parse_ccc_cell(cell):
    """CCC cell: blocks keyed by one of the 7 NGSS crosscutting concept names. Same approach as SEPs."""
    paras = cell_paragraphs(cell)
    if not paras:
        return []
    sections = _split_by_known_headers(paras, CCC_NAMES, SUBSECTION_HEADERS)
    out = []
    for s in sections:
        if not s['header'] and not s['body_paras']:
            continue
        bullet_chars = ('▪', '•', '●', '○')
        intro_paras = [p for p in s['body_paras'] if not any(p.startswith(b) for b in bullet_chars)]
        bullet_paras = [p for p in s['body_paras'] if any(p.startswith(b) for b in bullet_chars)]
        out.append({
            'concept': s['header'],
            'intro': ' '.join(intro_paras).strip(),
            'bullets': split_bullets_by_pe(bullet_paras),
            'is_subsection': s['is_subsection'],
        })
    return out


def parse_table(tbl):
    """Parse one foundation table. Returns dict with seps/dcis/cccs lists (raw, with per-bullet PE codes)."""
    rows = list(tbl.iter(f'{{{W}}}tr'))
    if not rows:
        return None
    # Header row should be SEP/DCI/CCC
    header_cells = [text_of(c).strip() for c in rows[0].iter(f'{{{W}}}tc')]
    if len(header_cells) < 3 or 'Science and Engineering Practices' not in header_cells[0]:
        return None
    seps, dcis, cccs = [], [], []
    for row in rows[1:]:
        cells = list(row.iter(f'{{{W}}}tc'))
        if len(cells) < 3:
            continue
        seps.extend(parse_sep_cell(cells[0]))
        dcis.extend(parse_dci_cell(cells[1]))
        cccs.extend(parse_ccc_cell(cells[2]))
    return {'seps': seps, 'dcis': dcis, 'cccs': cccs}


def extract():
    z = zipfile.ZipFile(DOCX)
    root = ET.fromstring(z.read('word/document.xml'))
    body = root.find('w:body', NS)
    seq = list(body)

    # State machine: walk body in order
    grade = None
    topics = {}  # key: topic_code -> {grade, code, name, pes: {pe_code: {...}}, foundation_tables: [...], connections: {...}}
    current_topic_code = None
    current_pe_code = None  # last PE we saw a clarification/AB pair for

    i = 0
    while i < len(seq):
        el = seq[i]
        tag = el.tag.split('}')[1]
        txt = text_of(el).strip()

        if tag == 'p':
            # Grade header?
            if txt in GRADE_HEADERS:
                grade = GRADE_HEADERS[txt]
            # Topic header?
            m = TOPIC_RE.match(txt)
            if m:
                prefix, domain, num, name = m.groups()
                topic_code = f"{prefix}-{domain}{num}"
                current_topic_code = topic_code
                # Topic name often runs into "Students who demonstrate understanding can:" — trim that.
                clean_name = re.sub(r'\s*Students who demonstrate.*$', '', name).strip()
                # Use the prefix from the topic code itself as the grade band — prefix is authoritative
                # for span topics (K-2, 3-5) and matches the grade header for single-grade topics.
                topic_grade = prefix
                if topic_code not in topics:
                    topics[topic_code] = {
                        'grade': topic_grade,
                        'code': topic_code,
                        'name': clean_name,
                        'pes': {},
                        'foundation': {'seps': [], 'dcis': [], 'cccs': []},
                        'connections_raw': [],
                    }
            # PE statement?
            elif current_topic_code:
                pem = PE_RE.match(txt)
                if pem:
                    code = normalize_pe_code(pem.group(1))
                    statement = pem.group(2).strip()
                    topics[current_topic_code]['pes'][code] = {
                        'code': code,
                        'statement': statement,
                        'clarification': '',
                        'assessment_boundary': '',
                    }
                    current_pe_code = code
                # Clarification + AB combined paragraph
                elif '[Clarification Statement:' in txt or '[Assessment Boundary:' in txt:
                    if current_pe_code and current_pe_code in topics[current_topic_code]['pes']:
                        clar = re.search(r'\[Clarification Statement:\s*(.+?)\](?=\s*(\[Assessment Boundary|$))', txt, re.S)
                        ab = re.search(r'\[Assessment Boundary:\s*(.+?)\]\s*$', txt, re.S)
                        if clar:
                            topics[current_topic_code]['pes'][current_pe_code]['clarification'] = clar.group(1).strip()
                        if ab:
                            topics[current_topic_code]['pes'][current_pe_code]['assessment_boundary'] = ab.group(1).strip()
                # Connection paragraphs
                elif txt.startswith(('Connections to', 'Articulation of')):
                    topics[current_topic_code]['connections_raw'].append({'header': txt, 'items': []})
                elif txt.startswith(('•', '●')) and topics[current_topic_code]['connections_raw']:
                    item_text = txt.lstrip('•●').strip()
                    # may end with (PE-code) tags
                    pe_codes = [normalize_pe_code(m.group(1)) for m in PE_CODE_TAG.finditer(item_text)]
                    clean = PE_CODE_TAG.sub('', item_text).strip().rstrip(',').strip()
                    topics[current_topic_code]['connections_raw'][-1]['items'].append({
                        'text': clean, 'pe_codes': pe_codes
                    })

        elif tag == 'tbl' and current_topic_code:
            parsed = parse_table(el)
            if parsed:
                topics[current_topic_code]['foundation']['seps'].extend(parsed['seps'])
                topics[current_topic_code]['foundation']['dcis'].extend(parsed['dcis'])
                topics[current_topic_code]['foundation']['cccs'].extend(parsed['cccs'])

        i += 1

    return topics


def attribute_to_pes(topics):
    """For each PE in each topic, slice the topic's foundation bullets down to just the ones tagged for that PE."""
    pe_records = []
    for tcode, t in topics.items():
        pes = t['pes']
        if not pes:
            continue
        for pcode, pe in pes.items():
            seps_for_pe = []
            for sep in t['foundation']['seps']:
                bullets = [b for b in sep['bullets'] if pcode in b['pe_codes']]
                if bullets:
                    seps_for_pe.append({
                        'practice': sep['practice'],
                        'intro': sep['intro'],
                        'bullets': [b['text'] for b in bullets],
                    })
            dcis_for_pe = []
            for dci in t['foundation']['dcis']:
                bullets = [b for b in dci['bullets'] if pcode in b['pe_codes']]
                if bullets:
                    dcis_for_pe.append({
                        'code': dci['code'],
                        'name': dci['name'],
                        'bullets': [b['text'] for b in bullets],
                    })
            cccs_for_pe = []
            for ccc in t['foundation']['cccs']:
                bullets = [b for b in ccc['bullets'] if pcode in b['pe_codes']]
                if bullets:
                    cccs_for_pe.append({
                        'concept': ccc['concept'],
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
                'topic_code': tcode,
                'topic_name': t['name'],
                'grade': t['grade'],
                'code': pe['code'],
                'statement': pe['statement'],
                'clarification': pe['clarification'],
                'assessment_boundary': pe['assessment_boundary'],
                'seps': seps_for_pe,
                'dcis': dcis_for_pe,
                'cccs': cccs_for_pe,
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
    print(f"wrote {OUT}")

    # quick sanity dump
    by_grade = {}
    for r in pe_records:
        by_grade.setdefault(r['grade'], []).append(r['code'])
    for g in sorted(by_grade):
        print(f"  grade {g}: {len(by_grade[g])} PEs")

    # Show first PE in full
    if pe_records:
        print("\n=== SAMPLE PE ===")
        print(json.dumps(pe_records[0], indent=2, ensure_ascii=False)[:3000])


if __name__ == '__main__':
    main()
