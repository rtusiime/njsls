# njsls — repo orientation

Static site presenting the New Jersey Student Learning Standards as a teacher-readable filtered browser, one subject per page. Hub at `index.html` links to each subject and hosts the **semantic discovery search** (BYO Anthropic API key). Deploys to GitHub Pages at `https://rtusiime.github.io/njsls/`. Audience: Forge Prep curriculum team.

## Semantic search (Phase 2, as of Session 6)

The hub has a paste-anything search box that finds NJSLS matches for vague learning goals, standard codes, full lesson plans, or single topics.

- **Model:** `claude-sonnet-4-6` with prompt caching on the corpus (5-min TTL).
- **Key handling:** BYO — stored in `localStorage` under `njsls_anthropic_api_key`. First-time search prompts via modal; "Change API key" link visible under the search box.
- **CORS:** browser → `api.anthropic.com/v1/messages` direct using the `anthropic-dangerous-direct-browser-access: true` header. No backend.
- **Grounding:** the full `data/all.json` corpus (~50K tokens) is injected into the system prompt; Claude returns `{ "matches": [{ code, rationale }] }` JSON. We validate codes against the local corpus before rendering — hallucinated codes are dropped.
- **Cost:** ~$0.21 first query of a session (cache write), ~$0.04 per query thereafter (cache hit), per user's own Anthropic bill.
- **Output rendering:** subject-colored result cards with the verbatim statement, optional subs, rationale chip, and a "Open <subject> page →" link. KaTeX renders any LaTeX in Math standards.

To restyle or tune search: it lives inline at the bottom `<script>` block of `index.html`. Prompt text is in `SYSTEM_INSTRUCTIONS`.

## File map

| File / Path | Role |
|---|---|
| `index.html` | Hub: 4 subject cards + semantic search box. Loads `data/all.json` when search runs. |
| `ela.html` | English Language Arts, Grades 5–8. Filtered browser. Fetches `data/ela.json` at load. |
| `math.html` | Mathematics, Grades 5–8. Filtered browser with KaTeX rendering. Fetches `data/math.json`. |
| `science.html` | Science, Grades 5–8 (Grade 5 + MS 6–8). Filtered browser. Fetches `data/science.json`. |
| `social-studies.html` | Social Studies, Grades 3–8 (bands 3–5 and 6–8). Filtered browser. Fetches `data/social-studies.json`. |
| `data/ela.json` | Hierarchical: domains → anchors → grades → entries. |
| `data/math.json` | Hierarchical: grade → domains → clusters → standards. |
| `data/science.json` | Hierarchical: discipline → topics → PEs; per-topic `grade_band`. |
| `data/social-studies.json` | Hierarchical: band → standards (6.1 / 6.2 / 6.3) → eras OR groups → core_idea_blocks → PEs. |
| `data/sources/*.md` | Cleaned source markdown for subjects whose source we processed ourselves (currently SS). |
| `data/all.json` | **Flat denormalized 523-record array of every standard.** LLM/API consumption layer. |
| `assets/cc-backlinks.js` + `.css` | Shared module: fetches CC live state and attaches "Taught in" sections under each standard entry on subject pages. |
| `scripts/build_all.py` | Rebuilds `data/all.json` after any subject JSON edit. |
| `SESSIONS.md` | Reverse-chronological transcript log per work session. Append at top before each session's final commit. |
| `CLAUDE.md` | This file. Auto-loaded into Claude Code context. |

**Architecture as of Session 5:** HTML pages are presentation; data lives in `/data/*.json`; pages `fetch()` at load time. The de-facto API is `https://rtusiime.github.io/njsls/data/all.json` (and per-subject equivalents). No backend.

**To edit data:** edit the relevant `data/*.json` directly, then run `python3 scripts/build_all.py` to regenerate `data/all.json`. Commit both files together so the flat index stays in sync with the per-subject sources.

**To preview locally:** `python3 -m http.server` from the repo root (NOT `file://` — fetch() won't load JSON over the file protocol).

## Per-subject schemas

The schemas are intentionally **different shapes per subject** because NJDOE organizes each subject differently. Don't force a unified shape — adapters per subject is the point.

### ELA — `data/ela.json`
```
{
  "<domain>": {                                 // language, reading, writing, speaking_listening
    name, note,
    anchors: [{
      code, name, statement,
      grades: {
        "<grade>": [{                           // "5" | "6" | "7" | "8"
          prefix,                               // L | RL | RI | W | SL
          code,                                 // e.g., "L.RF.5.3"
          main,                                 // statement text
          subs: [{ code, text }],               // optional lettered sub-bullets; code = <parent>.A/.B/… (e.g. L.SS.6.1.A), individually searchable
          subgroup                              // optional category tag (e.g., "phonics")
        }]
      }
    }]
  }
}
```
Filters in UI: Domain pills + Grade pills. Lettered sub-bullets are individually coded (`L.SS.6.1.A`) and searchable by that code; an exact sub-code query highlights the matching bullet. Codes are assigned by list position from the source docx (verified: all 34 sub-bearing entries match the docx exactly).

### Math — `data/math.json`
```
{
  "<grade>": {                                  // "5" | "6" | "7" | "8"
    grade, note,
    domains: [{
      code,                                     // "5.OA", "6.RP", etc.
      name,
      clusters: [{
        letter,                                 // "A", "B", "C"
        heading,
        standards: [{
          code,                                 // "5.OA.A.2"
          main,                                 // verbatim text with inline LaTeX in \(...\)
          subs: [string]                        // optional lettered sub-items
        }]
      }]
    }]
  }
}
```
Filters in UI: Grade pills + live search input. Math has inline LaTeX expressions (e.g., `\frac{1}{10}`); rendered client-side via KaTeX auto-render. Search is normalised so plain-text queries like `1/2` find `\frac{1}{2}` — see `stripLatex()` in `math.html`.

### Science — `data/science.json`
```
{
  "<discipline>": {                             // physical, life, earth_space, engineering
    name, note,
    topics: [{
      code,                                     // "5-PS1", "MS-PS1", "3-5-ETS1", etc.
      name,
      grade_band: "5" | "MS",                   // per-grade for elementary, MS for 6-8
      pes: [{
        code,                                   // "5-PS1-1", "MS-PS1-1", etc.
        statement,
        clarification,                          // optional
        assessment_boundary                     // optional
      }]
    }]
  }
}
```
Filters in UI: Discipline pills + Grade-band pills + Topic-code pills + live search.

### Social Studies — `data/social-studies.json`
```
{
  "grade_bands": ["3-5", "6-8"],
  "standards_meta": { "6.1": "U.S. History: America in the World", "6.2": "World History / Global Studies", "6.3": "Active Citizenship in the 21st Century" },
  "bands": {
    "<3-5 | 6-8>": {
      "standards": [{
        code,                                   // "6.1", "6.2", "6.3"
        name,
        end_grade: 5 | 8,
        organization: "by_concept" | "by_era",
        // Either eras (for 6-8 6.1 / 6.2) OR groups (for 3-5 or 6.3):
        eras: [{
          era_num, era_label, era_summary,
          core_idea_blocks: [{ core_idea, pes: [{ code, statement }] }]
        }],
        groups: [{
          discipline,                           // "Civics, Government, and Human Rights"
          sub_concept,                          // "Civics and Political Institutions"
          core_idea_blocks: [{ core_idea, pes: [{ code, statement }] }]
        }]
      }]
    }
  }
}
```
Filters in UI: Grade-band pills + Standard pills (6.1 / 6.2 / 6.3) + live search.

Code shape varies by standard/band:
- 3-5 and 6.3: `6.<1|3>.<5|8>.<DiscConcept>.<num>` — e.g., `6.1.5.CivicsPI.1`
- 6-8 6.1/6.2: `6.<1|2>.8.<DiscConcept>.<era>.<letter>` — e.g., `6.1.8.CivicsPI.3.a`

### `data/all.json` — flat consumption layer
Each standard is an entry in `standards: [...]` with denormalised fields: `{subject, code, grade, statement, …}` plus subject-specific extras (domain/anchor for ELA, domain/cluster for Math, discipline/topic for Science, standard/era-or-discipline/core_idea for SS). 903 entries (`schema_version` 1.1).

**Science PEs also carry NGSS three-dimensionality as queryable structure** (not latent prose fused into statement/clarification): scalar *lens keys* `sep_practices` / `dci_codes` / `ccc_concepts` for filtering by dimension (e.g. every PE using the Cause-and-Effect lens), plus full `seps` / `dcis` / `cccs` structures with identifiers + bullets. The repeated grade-band progression `intro` paragraphs are kept in `science.json` for the page render but dropped from `all.json` as boilerplate. A top-level `science_dimensions` block enumerates the available lenses (8 SEP practices, 15 CCC concepts, 35 DCI codes). Propagation logic lives in `science_dimensions()` in `scripts/build_all.py`.

This is the format to feed an LLM / Claude project / external script. Don't put hierarchical schemas in front of consumers when they want to scan all the standards.

### Other subjects, when added
Pick a schema that matches the source document's natural organization. Add a new `data/<subject>.json`. Update `scripts/build_all.py` to include it in `all.json`. The HTML view layer can have totally different shapes per subject — the only contract is each subject page fetches its own JSON.

## Visual design system

Same fonts and warm-paper palette across all pages — distinct subject accent.

| Subject | Accent hex | CSS var name |
|---|---|---|
| ELA | `#8B3A1F` terracotta | `--accent` |
| Math | `#1F5A6E` deep teal | `--accent` |
| Science | `#3F6B47` forest green | `--accent` |
| Social Studies | `#7E4E6E` mauve | `--accent` |

Fonts: `Fraunces` (display, italic for accent words) + `Manrope` (body). Background: `#FAF6EE` warm paper. Soft radial-gradient blooms in the subject accent color.

**Shared visual elements** (currently duplicated across files):
- masthead with back-link → eyebrow → title → subtitle → source-line
- sticky filter bar with pill rows
- anchor/topic cards (white surface, 3–4px left accent bar, soft shadow)
- footer with attribution to NJDOE

## Source documents

All NJSLS PDFs and docx files live one level up at `../curriculum/`. When adding a subject, the source is verbatim authoritative.

| Subject | Source path |
|---|---|
| ELA (already in this repo) | Source docx now in-repo: `data/sources/2023_NJSLS_ELA.docx` (2023 NJSLS-ELA). Parse via stdlib `zipfile` + `xml.etree` on `word/document.xml` — deterministic; lettered subs are Word auto-numbering (`numPr`/`ilvl`), so letters derive from list position. |
| Math | `/Users/ktusiime/Desktop/DLA/Forge/curriculum/2023_NJSLS_Mathematics.docx` |
| Science 6–8 | `/Users/ktusiime/Desktop/DLA/Forge/curriculum/NJSLS-Science_6-8.pdf` |
| Science K–5 | `/Users/ktusiime/Desktop/DLA/Forge/curriculum/NJSLS-Science_K-5.pdf` |
| Social Studies | `/Users/ktusiime/Desktop/DLA/Forge/curriculum/2020NJSLS-SS_by_Standard.pdf` (also `..._by_GradeBand.pdf`) |
| Computer Science | `2020 NJSLS-CSDT.pdf` |
| Health / PE | `2020_NJSLS-CHPE.pdf` |
| World Languages | `2020NJSLS-WL.pdf` |
| Visual & Performing Arts | `2020 NJSLS-VPA.pdf` |
| Career Readiness (CLKS) | Local `2020NJSLS-CLKS.pdf` no longer in `../curriculum/`. Live source — NJDOE: [9.1 Financial Literacy](https://www.nj.gov/education/standards/clicks/Docs/2020NJSLS-9.1FinancialLiteracy.pdf), [9.2 Career Awareness](https://www.nj.gov/education/standards/clicks/Docs/2020NJSLS-9.2CareerAwareness.pdf), [9.4 Life Literacies & Key Skills](https://www.nj.gov/education/standards/clicks/Docs/2020NJSLS-9.4LifeLiteraciesandKeySkills.pdf) (also [combined](https://www.nj.gov/education/standards/clicks/Docs/2020NJSLS-CLKS.pdf)) |

For PDF extraction: `pdftotext -layout` from poppler (already installed via brew). For docx: `unzip -p file.docx word/document.xml` and parse the XML, or use Python's `python-docx` if installed.

## Common operations

### Adding a new subject

1. Choose the source doc from `../curriculum/`.
2. Decide the schema shape — let the source's natural organization drive it. Document the shape in this file under "Per-subject schemas."
3. Extract verbatim into JSON. **Spot-check** the extraction: count clusters/standards against the source and verify at least three records against the source text. Delegate the mechanical extraction to a subagent when the source is long.
4. Build a new `<subject>.html` modeled on `ela.html` or `science.html` — whichever schema is closer.
5. Add a card to `index.html` under `<div class="subject-grid">`. Pick an accent color that's visually distinct from existing subjects. Update the `:root` color vars in `index.html`.
6. Run an end-to-end check: open the page locally, exercise every filter, confirm the standards count matches the source.
7. Append a Session entry to `SESSIONS.md` covering the work.
8. Commit + push. Pages rebuilds automatically.

### Deployment

- Hosted at `https://rtusiime.github.io/njsls/` (GitHub Pages, free tier, public repo `rtusiime/njsls`).
- Build is automatic on push to `main`. Typical rebuild: 30–90 seconds.
- Check status: `gh api /repos/rtusiime/njsls/pages/builds/latest --jq '.status'`. Wait pattern: `until [ "$(gh api ... --jq .status)" = "built" ]; do sleep 5; done`.
- Verify live: `curl -sI https://rtusiime.github.io/njsls/<page>.html`.

### Updating subject status on hub

Subjects start "In progress" and flip to "Ready" once their data is populated. In `index.html`, change the card's class from `coming-soon` to `ready`, swap the status pill text, and update the CTA.

## When to refactor (and when not to)

**Don't extract shared CSS or render JS yet.** Three subjects with copy-pasted ~250 lines of CSS each is cheap. The natural refactor trigger is **adding subject #4 or #5** — at that point, edit-once cost dominates copy-paste cost. Until then, self-contained files are simpler to reason about.

**Do** extract data files (`data/<subject>.json` loaded via fetch) if a single HTML grows past ~2500 lines. Current cap: ELA at 1988.

## Cohort Calendar integration (Phase 3 — shipped Session 7)

Sister repo `github.com/john-forge/CohortCalendar` (deployed at `https://john-forge.github.io/CohortCalendar/`) holds 357 blocks, 173 with `std` tagged.

**Live state source:** Supabase REST endpoint with the public anon key (baked into CC's `publish.py`, already public).

```
GET https://vaqdoeckaobmsalikmpx.supabase.co/rest/v1/documents?id=eq.main&select=data
Headers:
  apikey: sb_publishable_UlWZDjS5Yx07Cl-reOlLAg_qOsp7DLn
  Authorization: Bearer sb_publishable_UlWZDjS5Yx07Cl-reOlLAg_qOsp7DLn

Returns: [ { "data": { "blocks": [...], "grades": [...], ... } } ]
```

CORS allows `https://rtusiime.github.io` origin. No proxy/Worker needed.

Each block has `id, ttl, desc, w (week 0-indexed), d (day 0=Mon..4=Fri), s (slot), dur, tp (block type), grades[] (G5..G8), std[], std_defensible, tag, anc, locked`.

### Backlinks shared module — `assets/cc-backlinks.js` + `.css`

Loaded by every subject page. On first DOMContentLoaded **and** any time the page's own render() runs, the module:

1. Fetches CC state from Supabase (once per page load).
2. Builds `Map<standardCode, blocks[]>`, sorted chronologically (week → day → slot).
3. Walks the DOM for `.entry[data-code]`, `.std-entry[data-code]`, `.pe-entry[data-code]`.
4. Appends a `.cc-backlinks` section under each matched entry: header (count) + chip-row of blocks. Collapsed past 4 blocks with "Show N more."
5. Chip click → opens CC at `#blk_<id>` hash (CC doesn't yet handle the hash; for now it just goes to CC homepage — a small CC change away from a real deep link).

Subject pages call `window.attachCCBacklinks()` at the end of their fetch().then() handler — the module gracefully handles being called before CC state is ready (waits).

### Known data-alignment gap (as of Session 7)

CC uses two code formats interleaved:
- **Modern NJSLS-2023 codes** (`5.NBT.B.7`, `MS-LS1-7`, `7.RP.A.2`) — match our corpus exactly. 20 of CC's 39 unique tagged codes are in this category.
- **Older CCSS-anchor abbreviations** (`SL.1`, `W.4`, `RI.2`, also Math `5.MD.A.1` vs our `5.M.A.1`) — don't match. 19 of CC's 39.

Backlinks render for the 20 matching codes; the 19 unmatched ones are silent — those standards appear without a "Taught in" section. **This is a real product gap.** Three remediation paths:
- **(a) Translation table** at the join layer (mechanical for Math, requires curation for ELA anchors → grade-specific NJSLS codes).
- **(b) Update CC tags** to current NJSLS — cross-repo migration.
- **(c) Leave as-is, accept the gap** — the 20 matching codes are the heavily-taught ones; coverage of high-leverage standards is mostly working.

User input needed before picking (a) or (b).

## What's intentionally *not* in this repo

- The three-dimensional NGSS foundation box for Science (SEPs, DCIs, CCCs). The source PDF lays it out in multi-column tables that `pdftotext -layout` mangles. If added later, switch to a column-aware extractor like Python `pdfplumber` with bbox-aware grouping, or pull the foundation from the NGSS website rather than the PDF.
- A README. Not needed — this file plus SESSIONS.md cover everything.
- Build tooling, linters, package.json. Single-file static HTML; don't add a build step.

## Conventions worth knowing

- **"Forge Prep" everywhere** in user-facing copy. Never *DLA* or *Douglass Leadership Academy*, even though the directory path contains "DLA". This was a correction from the user — see `feedback_forge_prep_naming.md` in memory.
- **SESSIONS.md is the dev journal.** Append a new entry at the **top** of the file before every final commit when working in this repo. Format is documented in the memory file `project_njsls_sessions_log.md`.
- **Subject pages get a `← All standards` back-link** in the masthead (small uppercase chip-link, muted gray, hovers to the subject accent).
- **Hub status pages** (`math.html` and `science.html` *before* they were populated) used a "status callout" pattern — domain previews + source-doc citation. Use that pattern for any new subject scaffolded before data is ready.

## Pointers

- Reverse-chronological dev history: `SESSIONS.md`
- User profile and project-wide memory: `/Users/ktusiime/.claude/projects/-Users-ktusiime-Desktop-DLA-Forge-Code/memory/MEMORY.md`
- Parent project context (the broader Forge/Code workspace, includes CohortCalendar): one level up.
