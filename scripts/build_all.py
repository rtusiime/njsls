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

# Science: discipline → topics → pes
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

# CSDT: standards (8.1 / 8.2) → grade_bands → disciplinary_concepts → core_idea_blocks → pes
# Flatten only the default-visible grade bands so all.json matches the site's Forge Prep scope.
visible_bands = set(csdt.get("default_visible_grade_bands", ["5", "8"]))
for std in csdt["standards"]:
    for gb_key, gb in std["grade_bands"].items():
        if gb_key not in visible_bands:
            continue
        for dc in gb["disciplinary_concepts"]:
            for cib in dc["core_idea_blocks"]:
                core_idea_joined = " | ".join(cib["core_ideas"])
                for pe in cib["pes"]:
                    flat.append({
                        "subject": "csdt",
                        "code": pe["code"],
                        "grade": gb_key,
                        "standard": f"{std['code']} - {std['name']}",
                        "disciplinary_concept": f"{dc['abbrev']} - {dc['name']}",
                        "core_idea": core_idea_joined,
                        "statement": pe["statement"],
                    })

# Strip None values
flat = [{k: v for k, v in d.items() if v is not None} for d in flat]

all_data = {
    "schema_version": "1.0",
    "site": "https://rtusiime.github.io/njsls/",
    "source": "New Jersey Department of Education - NJSLS (2023 ELA + Math, 2020 Science / SS / CSDT)",
    "standard_count": len(flat),
    "subjects": {
        "ela":             {"title": "English Language Arts",                  "grade_range": "5-8",                      "adopted": "2023"},
        "math":            {"title": "Mathematics",                            "grade_range": "5-8",                      "adopted": "2023"},
        "science":         {"title": "Science",                                "grade_range": "5-8 (Grade 5 + MS 6-8)",   "adopted": "2020 (NGSS-aligned)"},
        "social_studies":  {"title": "Social Studies",                         "grade_range": "3-8 (bands 3-5 and 6-8)",  "adopted": "2020"},
        "csdt":            {"title": "Computer Science & Design Thinking",     "grade_range": "5-8 (end-of-grade 5 + 8)", "adopted": "2020"},
    },
    "standards": flat,
}

(DATA / "all.json").write_text(json.dumps(all_data, indent=2, ensure_ascii=False) + "\n")

from collections import Counter
counts = Counter(d["subject"] for d in flat)
print(f"Wrote data/all.json — {len(flat)} standards total")
for k, v in counts.items():
    print(f"  {k}: {v}")
