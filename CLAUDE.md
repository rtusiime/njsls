# njsls — repo orientation

Static site presenting the New Jersey Student Learning Standards as a teacher-readable filtered browser, one subject per page. Hub at `index.html` links to each subject. Deploys to GitHub Pages at `https://rtusiime.github.io/njsls/`. Audience: Forge Prep curriculum team.

## File map

| File | Role | Has data? |
|---|---|---|
| `index.html` | Hub: three subject cards with per-subject accent colors and Ready / In-progress status. | no |
| `ela.html` | English Language Arts, Grades 5–8. Full filtered browser. | yes — inline `const STANDARDS` |
| `math.html` | Mathematics, Grades 5–8. *(status page until populated)* | (eventually inline `const MATH`) |
| `science.html` | Science, Grades 6–8 (MS). Full filtered browser. | yes — inline `const SCIENCE` |
| `SESSIONS.md` | Reverse-chronological transcript log per work session. Append at top before each session's final commit. | n/a |
| `CLAUDE.md` | This file. Auto-loaded into Claude Code context. | n/a |

Every HTML file is **fully self-contained**: inline CSS, inline `<script>`, inline data. Drop any file on any static server and it works. No build step.

## Per-subject schemas

The schemas are intentionally **different shapes per subject** because NJDOE organizes each subject differently. Don't force a unified shape — adapters per subject is the point.

### ELA (`ela.html`)
```
STANDARDS = {
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

### Science (`science.html`)
```
SCIENCE = {
  "<discipline>": {                             // physical, life, earth_space, engineering
    name, note,
    topics: [{
      code,                                     // "MS-PS1", "MS-LS3", etc.
      name,
      pes: [{
        code,                                   // "MS-PS1-1", etc.
        statement,
        clarification,                          // optional
        assessment_boundary                     // optional
      }]
    }]
  }
}
```
Filters in UI: Discipline pills + Topic-code pills + live search input.

### Math (`math.html`) — *schema to be locked when populated*
Likely: `domain → cluster → grade → standard with subs`. Will document here once committed.

### Other subjects, when added
Pick a schema that matches the source document's natural organization. The site can carry totally different shapes — the only contract is the JS render function inside each file, which produces the same visual card pattern.

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
