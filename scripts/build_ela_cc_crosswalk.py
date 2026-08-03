#!/usr/bin/env python3
"""Regenerate the Common Core (2016) `cc_codes` on every grades 5-8 ELA entry in
data/ela.json, from the official NJDOE 2016->2023 crosswalk docx.

Idempotent: re-run after editing ela.json to refresh cc_codes/cc_source, then run
scripts/build_all.py to propagate to all.json.

Coverage (129/130; L.WF.5.2 is new-in-2023 with no CC equivalent):
  official — a direct row in the crosswalk tables (Language, Reading-Literature, Writing, RI.AA).
  derived  — the crosswalk normalizes companion standards: Reading-Informational folds into the
             RL rows (RI.CI.8.2 -> RI.8.2, parallel to RL.CI.8.2 -> RL.8.2), and Writing's
             grade 6-8 rows follow the grade-5 subcat->CC-anchor pattern.
  wording  — Speaking/Listening is absent from the crosswalk entirely; the 2023 SL sub-category
             codes preserve the CC anchor number (SL.PE.6.1 -> SL.6.1, ...), confirmed by matching
             the NJSLS statements against Common Core SL text.
"""
import zipfile, re, json
from pathlib import Path
from xml.etree import ElementTree as ET
from collections import Counter

ROOT = Path(__file__).parent.parent
DOCX = ROOT / "data/sources/NJSLS_ELA_Crosswalk_2016_to_2023.docx"
ELA = ROOT / "data/ela.json"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
SL_ANCHOR = {"PE": "1", "II": "2", "ES": "3", "PI": "4", "UM": "5", "AS": "6"}  # confirmed vs CC SL.x.n


def lead_code(s):
    m = re.match(r"^\s*([A-Z]{1,3}(?:\.[A-Za-z0-9]+){1,4})", s)
    return m.group(1).rstrip(".") if m else ""


def parse_crosswalk():
    """{2023_code: 2016_code} for every table row that maps one standard code to another."""
    doc = ET.fromstring(zipfile.ZipFile(DOCX).read("word/document.xml"))
    base = {}
    for tbl in doc.iter(W + "tbl"):
        for r in tbl.iter(W + "tr"):
            cells = ["".join(t.text or "" for t in c.iter(W + "t")).strip() for c in r.iter(W + "tc")]
            if len(cells) >= 4:
                a, b = lead_code(cells[2]), lead_code(cells[3])
                if a and b and re.match(r"^(RL|RI|RF|W|SL|L)\.", a) and re.match(r"^(RL|RI|RF|W|SL|L)\.", b):
                    base[a] = b
    return base


def build_map(codes):
    base = parse_crosswalk()
    parse = lambda c: re.match(r"^([A-Z]{1,3})\.([A-Z]{2,3})\.(\d+)\.(\d+)$", c)
    # subcat -> CC anchor number, learned from the table rows
    anchors = {}
    for a, b in base.items():
        m, mb = parse(a), re.match(r".*\.(\d+)$", b)
        if m and mb:
            anchors.setdefault((m.group(1), m.group(2)), Counter())[mb.group(1)] += 1
    uniform = {k: v.most_common(1)[0][0] for k, v in anchors.items() if len(v) == 1}
    out = {}
    for c in codes:
        m = parse(c)
        if c in base:
            out[c] = {"cc": [base[c]], "src": "official"}
        elif m and m.group(1) == "SL" and m.group(2) in SL_ANCHOR:
            out[c] = {"cc": [f"SL.{m.group(3)}.{m.group(4)}"], "src": "wording"}
        elif m:
            dom, sub, g, _ = m.groups()
            key = (dom, sub) if (dom, sub) in uniform else (("RL", sub) if dom == "RI" else None)
            if key in uniform:
                out[c] = {"cc": [f"{dom}.{g}.{uniform[key]}"], "src": "derived"}
    return out


def main():
    ela = json.loads(ELA.read_text())
    entries = []

    def walk(o):
        if isinstance(o, dict):
            if "code" in o and "main" in o:
                entries.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(ela)
    cc = build_map({e["code"] for e in entries})
    n = 0
    for e in entries:
        if e["code"] in cc:
            e["cc_codes"] = cc[e["code"]]["cc"]
            e["cc_source"] = cc[e["code"]]["src"]
            n += 1
        else:
            e.pop("cc_codes", None)
            e.pop("cc_source", None)
    ELA.write_text(json.dumps(ela, indent=2, ensure_ascii=False) + "\n")
    by_src = Counter(cc[e["code"]]["src"] for e in entries if e["code"] in cc)
    print(f"cc_codes on {n} entries — {dict(by_src)}; uncoded: "
          f"{sorted(e['code'] for e in entries if e['code'] not in cc)}")


if __name__ == "__main__":
    main()
