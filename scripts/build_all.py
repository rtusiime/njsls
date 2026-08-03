#!/usr/bin/env python3
"""Rebuild data/all.json (the flat denormalised standards index) from the per-subject JSONs.

Run this after editing data/ela.json, data/math.json, or data/science.json.
The flat all.json is the LLM/API consumption layer — see CLAUDE.md.
"""
import json
from pathlib import Path

DATA = Path(__file__).parent.parent / "data"

ela = json.loads((DATA / "ela.json").read_text())
math_ = json.loads((DATA / "math.json").read_text())
science = json.loads((DATA / "science.json").read_text())
ss = json.loads((DATA / "social-studies.json").read_text())
csdt = json.loads((DATA / "csdt.json").read_text())
clks = json.loads((DATA / "clks.json").read_text())
chpe = json.loads((DATA / "chpe.json").read_text())


def flatten_njdoe_framework(subject_key, data):
    """Flatten the NJDOE-framework shape (standards → grade_bands → disciplinary_concepts
    → core_idea_blocks → pes) into flat records. Restricts to default_visible_grade_bands
    so all.json stays Forge-scoped. Shared by CSDT, CLKS, CHPE."""
    records = []
    visible = set(data.get("default_visible_grade_bands", ["5", "8"]))
    for std in data["standards"]:
        for gb_key, gb in std["grade_bands"].items():
            if gb_key not in visible:
                continue
            for dc in gb["disciplinary_concepts"]:
                for cib in dc["core_idea_blocks"]:
                    core_idea_joined = " | ".join(cib["core_ideas"])
                    for pe in cib["pes"]:
                        records.append({
                            "subject": subject_key,
                            "code": pe["code"],
                            "grade": gb_key,
                            "standard": f"{std['code']} - {std['name']}",
                            "disciplinary_concept": f"{dc['abbrev']} - {dc['name']}",
                            "core_idea": core_idea_joined,
                            "statement": pe["statement"],
                        })
    return records

flat = []

# ELA: domain → anchors → grades → entries
for _domain_key, domain in ela.items():
    for anchor in domain["anchors"]:
        for grade, entries in anchor["grades"].items():
            for e in entries:
                flat.append({
                    "subject": "ela",
                    "code": e["code"],
                    "grade": grade,
                    "domain": domain["name"],
                    "anchor": f"{anchor['code']} - {anchor['name']}",
                    "statement": e["main"],
                    "subs": e.get("subs") or None,
                    "prefix": e.get("prefix"),
                    "cc_codes": e.get("cc_codes") or None,      # Common Core (2016) equivalent(s)
                    "cc_source": e.get("cc_source"),            # official | derived | wording
                })

# Math: grade → domains → clusters → standards
for grade, gdata in math_.items():
    for dom in gdata["domains"]:
        for clus in dom["clusters"]:
            for s in clus["standards"]:
                flat.append({
                    "subject": "math",
                    "code": s["code"],
                    "grade": grade,
                    "domain": f"{dom['code']} - {dom['name']}",
                    "cluster": f"{clus['letter']}. {clus['heading']}",
                    "statement": s["main"],
                    "subs": s.get("subs") or None,
                })

# Science: discipline → topics → pes.
# NGSS three-dimensionality (SEP / DCI / CCC) is structured in science.json but used to be
# fused into statement+clarification prose here, so the flat layer couldn't be queried by
# dimension. Propagate it: compact scalar "lens" keys (sep_practices / dci_codes /
# ccc_concepts) make filtering trivial ("everything using the Cause-and-Effect lens"), and
# the full structures carry the bullets + identifiers for grounding. The repeated grade-band
# progression `intro` paragraphs are dropped — presentation boilerplate that stays on the
# page (science.json → science.html), not in this scan-everything layer.
def science_dimensions(pe):
    seps, dcis, cccs = pe.get("seps") or [], pe.get("dcis") or [], pe.get("cccs") or []
    dims = {}
    sep_practices = [s["practice"] for s in seps if s.get("practice")]
    dci_codes     = [d["code"]     for d in dcis if d.get("code")]
    ccc_concepts  = [c["concept"]  for c in cccs if c.get("concept")]
    if sep_practices: dims["sep_practices"] = sep_practices
    if dci_codes:     dims["dci_codes"]     = dci_codes
    if ccc_concepts:  dims["ccc_concepts"]  = ccc_concepts
    if seps: dims["seps"] = [{k: v for k, v in s.items() if k != "intro"} for s in seps]
    if dcis: dims["dcis"] = dcis
    if cccs: dims["cccs"] = [{k: v for k, v in c.items() if k != "intro"} for c in cccs]
    return dims

for _disc_key, disc in science.items():
    for topic in disc["topics"]:
        for pe in topic["pes"]:
            flat.append({
                "subject": "science",
                "code": pe["code"],
                "grade": topic.get("grade_band", "MS"),
                "discipline": disc["name"],
                "topic": f"{topic['code']} - {topic['name']}",
                "statement": pe["statement"],
                "clarification": pe.get("clarification"),
                "assessment_boundary": pe.get("assessment_boundary"),
                **science_dimensions(pe),
            })

# Social Studies: band → standards (6.1 / 6.2 / 6.3) → eras OR groups → core_idea_blocks → pes
for band_key, band in ss["bands"].items():
    for std in band["standards"]:
        container_key = "eras" if std["organization"] == "by_era" else "groups"
        for container in std[container_key]:
            for cib in container["core_idea_blocks"]:
                for pe in cib["pes"]:
                    rec = {
                        "subject": "social_studies",
                        "code": pe["code"],
                        "grade": band_key,
                        "standard": f"{std['code']} - {std['name']}",
                        "core_idea": cib["core_idea"],
                        "statement": pe["statement"],
                    }
                    if std["organization"] == "by_era":
                        rec["era"] = container["era_label"]
                        if container.get("era_summary"):
                            rec["era_summary"] = container["era_summary"]
                    else:
                        rec["discipline"] = container["discipline"]
                        rec["sub_concept"] = container["sub_concept"]
                    flat.append(rec)

# CSDT, CLKS, CHPE — same NJDOE framework shape. Visible-bands filter keeps all.json Forge-scoped.
flat.extend(flatten_njdoe_framework("csdt", csdt))
flat.extend(flatten_njdoe_framework("clks", clks))
flat.extend(flatten_njdoe_framework("chpe", chpe))

# Strip None values
flat = [{k: v for k, v in d.items() if v is not None} for d in flat]

# Controlled vocabularies for the science NGSS dimensions — the set of "lenses" a consumer
# can filter records by (each value appears in the sep_practices / dci_codes / ccc_concepts
# keys on individual science records).
_sci = [d for d in flat if d["subject"] == "science"]
science_dimension_index = {
    "note": "NGSS three-dimensionality tagged on science PEs. Filter records by these lenses via their sep_practices / dci_codes / ccc_concepts keys.",
    "sep_practices": sorted({p for d in _sci for p in d.get("sep_practices", [])}),
    "ccc_concepts":  sorted({c for d in _sci for c in d.get("ccc_concepts", [])}),
    "dci_codes":     sorted({c for d in _sci for c in d.get("dci_codes", [])}),
}

all_data = {
    "schema_version": "1.1",
    "site": "https://rtusiime.github.io/njsls/",
    "source": "New Jersey Department of Education - NJSLS (2023 ELA + Math, 2020 Science / SS / CSDT / CLKS / CHPE)",
    "standard_count": len(flat),
    "subjects": {
        "ela":             {"title": "English Language Arts",                            "grade_range": "5-8",                      "adopted": "2023"},
        "math":            {"title": "Mathematics",                                      "grade_range": "5-8",                      "adopted": "2023"},
        "science":         {"title": "Science",                                          "grade_range": "5-8 (Grade 5 + MS 6-8)",   "adopted": "2020 (NGSS-aligned)"},
        "social_studies":  {"title": "Social Studies",                                   "grade_range": "3-8 (bands 3-5 and 6-8)",  "adopted": "2020"},
        "csdt":            {"title": "Computer Science & Design Thinking",               "grade_range": "5-8 (end-of-grade 5 + 8)", "adopted": "2020"},
        "clks":            {"title": "Career Readiness, Life Literacies & Key Skills",   "grade_range": "5-8 (end-of-grade 5 + 8)", "adopted": "2020"},
        "chpe":            {"title": "Comprehensive Health & Physical Education",        "grade_range": "5-8 (end-of-grade 5 + 8)", "adopted": "2020"},
    },
    "science_dimensions": science_dimension_index,
    "standards": flat,
}

(DATA / "all.json").write_text(json.dumps(all_data, indent=2, ensure_ascii=False) + "\n")

from collections import Counter
counts = Counter(d["subject"] for d in flat)
print(f"Wrote data/all.json — {len(flat)} standards total")
for k, v in counts.items():
    print(f"  {k}: {v}")
