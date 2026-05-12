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
| `index.html` | Hub: subject cards with per-subject accent colors and Ready status. No data dependency. |
| `ela.html` | English Language Arts, Grades 5–8. Filtered browser. Fetches `data/ela.json` at load. |
| `math.html` | Mathematics, Grades 5–8. Filtered browser with KaTeX rendering. Fetches `data/math.json`. |
| `science.html` | Science, Grades 5–8 (Grade 5 + MS 6–8). Filtered browser. Fetches `data/science.json`. |
| `data/ela.json` | Subject-specific hierarchical schema (domains → anchors → grades → entries). |
| `data/math.json` | Subject-specific hierarchical schema (grade → domains → clusters → standards). |
| `data/science.json` | Subject-specific hierarchical schema (discipline → topics → PEs), per-topic `grade_band`. |
| `data/all.json` | **Flat denormalized 314-record array of every standard** — `{subject, code, grade, domain, statement, …}`. LLM/API consumption layer. |
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
          subs: [string],                       // optional sub-bullets
          subgroup                              // optional category tag (e.g., "phonics")
        }]
      }
    }]
  }
}
```
Filters in UI: Domain pills + Grade pills.

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

### `data/all.json` — flat consumption layer
Each standard is an entry in `standards: [...]` with denormalised fields: `{subject, code, grade, statement, …}` plus subject-specific extras (domain/anchor for ELA, domain/cluster for Math, discipline/topic for Science). 314 entries total as of Session 5.

This is the format to feed an LLM / Claude project / external script. Don't put hierarchical schemas in front of consumers when they want to scan all 314 standards.

### Other subjects, when added
Pick a schema that matches the source document's natural organization. Add a new `data/<subject>.json`. Update `scripts/build_all.py` to include it in `all.json`. The HTML view layer can have totally different shapes per subject — the only contract is each subject page fetches its own JSON.

## Visual design system

Same fonts and warm-paper palette across all pages — distinct subject accent.

| Subject | Accent hex | CSS var name |
|---|---|---|
| ELA | `#8B3A1F` terracotta | `--accent` |
| Math | `#1F5A6E` deep teal | `--accent` |
| Science | `#3F6B47` forest green | `--accent` |
| Social Studies *(future)* | TBD | `--accent` |

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
| ELA (already in this repo) | originally extracted from a 2023 NJSLS-ELA reference |
| Math | `/Users/ktusiime/Desktop/DLA/Forge/curriculum/2023_NJSLS_Mathematics.docx` |
| Science 6–8 | `/Users/ktusiime/Desktop/DLA/Forge/curriculum/NJSLS-Science_6-8.pdf` |
| Science K–5 | `/Users/ktusiime/Desktop/DLA/Forge/curriculum/NJSLS-Science_K-5.pdf` |
| Social Studies | `/Users/ktusiime/Desktop/DLA/Forge/curriculum/2020NJSLS-SS_by_Standard.pdf` (also `..._by_GradeBand.pdf`) |
| Computer Science | `2020 NJSLS-CSDT.pdf` |
| Health / PE | `2020_NJSLS-CHPE.pdf` |
| World Languages | `2020NJSLS-WL.pdf` |
| Visual & Performing Arts | `2020 NJSLS-VPA.pdf` |
| Career Readiness | `2020NJSLS-CLKS.pdf` |

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

## Cohort Calendar integration (Phase 3 reference)

Sister repo `github.com/john-forge/CohortCalendar` (deployed at `https://john-forge.github.io/CohortCalendar/`) holds 357 blocks, 173 with `std` tagged in NJSLS code format (140 `std_defensible: true`).

**Live state source** for coverage-view fetches: Supabase REST endpoint with the public anon key (baked into CC's `publish.py`, already public).

```
GET https://vaqdoeckaobmsalikmpx.supabase.co/rest/v1/documents?id=eq.main&select=data
Headers:
  apikey: sb_publishable_UlWZDjS5Yx07Cl-reOlLAg_qOsp7DLn
  Authorization: Bearer sb_publishable_UlWZDjS5Yx07Cl-reOlLAg_qOsp7DLn

Returns: [ { "data": { "blocks": [...], "grades": [...], ... } } ]
```

CORS is configured to allow `https://rtusiime.github.io` origin — verified Session 6. Phase 3 coverage view can fetch directly from njsls's browser. No proxy/Worker needed.

To find blocks teaching a standard:
```js
const blocks = data.blocks.filter(b => b.std && b.std.includes(STANDARD_CODE));
```

Each block has `id, ttl, desc, w (week), d (day), s (slot), dur, tp (type), grades, std[], std_defensible`.

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
