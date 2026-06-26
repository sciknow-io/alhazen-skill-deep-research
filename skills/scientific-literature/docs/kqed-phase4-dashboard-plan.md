# Phase 4 — Read-Only Dashboard: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use
> checkbox (`- [ ]`) syntax. **Depends on Phases 1–3** (grounding, sensemaking, analysis read verbs).

**Goal:** A ground-up, **read-only** dashboard: a hub of Investigations + Collections, where each investigation
renders via a **template chosen by its type** — KQED narrative (template A: question → analysis → S1/S2/S3 →
paper/concept/fragment) or a survey **tabular reader** (template B, e.g. CAIS) — plus Concept and Paper views.

**Architecture:** Build ONLY in the skill's `dashboard/` source (`components/`, `lib.ts`, `pages/`, `routes/`);
`make build-dashboard` copies to `dashboard/src/...`. Every view follows the canonical
`paper/[id]` page→route→component template. `lib.ts` shells to read-only CLI verbs via `runScilit`. The
mechanism graph reuses the plain-SVG pattern from `components/embedding-map.tsx` (no graph library).

**Tech Stack:** Next.js App Router (server pages + client components), TypeScript, ReactMarkdown+remarkGfm,
plain SVG. Backend = the Phase 1–3 read verbs.

## Global Constraints

- **NEVER edit `dashboard/src/...`** (generated). Edit `skills/biomed/scientific-literature/dashboard/*` then
  `make build-dashboard` (from `/Users/gullyburns/skillful-alhazen`).
- **Read-only invariant:** every API route calls ONLY `show-*`/`list-*` verbs through `runScilit`/`runNotebook`;
  no route writes to the KG or calls OLS.
- Reuse `lib.ts:runScilit(args)` (sets `TYPEDB_DATABASE`, gateway fallback) and `components/atoms.tsx`
  (`Shell`, `Panel`, `HeaderStrip`, `MarkdownContent`, `BackNav`), `components/tokens.ts`, the
  `components/embedding-map.tsx` SVG scaling pattern.
- Screenshots during testing → `~/.alhazen/cache/screenshots/` only.
- Canonical template (follow verbatim for each new view): `pages/.../paper/[id]/page.tsx` (server, async
  `params`) + `routes/paper/[id]/route.ts` (`GET` → lib fn, try/catch 500) + `components/paper-detail.tsx`
  (`'use client'`, fetch `/api/scientific-literature/...`, `Shell`+`Panel`).

---

### Task 1: lib.ts — read functions, types, template registry

**Files:** Modify `dashboard/lib.ts`.

**Interfaces:** Produces `listInvestigations()`, `getInvestigation(id)` (→ `show-investigation`),
`getInvestigationTable(id)` (→ `show-investigation-table`), `listCollections()`, `getConcept(curie)`,
`getPaperSensemaking(id)`; and `templateFor(type): "kqed"|"survey"` registry.

- [ ] **Step 1: Add read wrappers** (mirror existing `listCorpora`/`getPaper`)
```typescript
export async function listInvestigations(): Promise<{ investigations: Investigation[]; count: number }> {
  return runScilit(['list-investigations']) as Promise<{ investigations: Investigation[]; count: number }>;
}
export async function getInvestigation(id: string): Promise<InvestigationView> {
  return runScilit(['show-investigation', '--id', id]) as Promise<InvestigationView>;
}
export async function getInvestigationTable(id: string): Promise<InvestigationTable> {
  return runScilit(['show-investigation-table', '--id', id]) as Promise<InvestigationTable>;
}
export async function getConcept(curie: string): Promise<ConceptView> {
  return runScilit(['show-concept', '--curie', curie]) as Promise<ConceptView>;
}
export async function getPaperSensemaking(id: string): Promise<PaperSensemaking> {
  return runScilit(['show-paper-sensemaking', '--id', id]) as Promise<PaperSensemaking>;
}
export const TEMPLATE_BY_TYPE: Record<string, 'kqed' | 'survey'> = {
  kqed: 'kqed', 'deep-dive': 'kqed', survey: 'survey', meeting: 'survey',
};
export function templateFor(type?: string): 'kqed' | 'survey' {
  return (type && TEMPLATE_BY_TYPE[type]) || 'survey';   // default = tabular reader
}
```
(Add the TS interfaces `Investigation`, `InvestigationView`, `InvestigationTable`, `ConceptView`,
`PaperSensemaking` matching the read-verb JSON.)

- [ ] **Step 2: Add a `show-concept` read verb** to `scientific_literature.py` (the one read verb not built in
  P1–P3): given `--curie`, return the `scilit-ontology-term` (label/def/source/iri) + bioentities/claims/
  observations classified to it. Read-only.
- [ ] **Step 3: Commit** — `git commit -am "feat(scilit-dash): lib read wrappers + template registry + show-concept"`

---

### Task 2: API routes (thin read-only GET wrappers)

**Files:** Create under `dashboard/routes/`: `investigations/route.ts`, `investigation/[id]/route.ts`,
`investigation/[id]/table/route.ts`, `concept/[curie]/route.ts`, `paper/[id]/sensemaking/route.ts`,
`collections/route.ts`.

**Interfaces:** Each is the canonical `GET` handler → its lib fn, try/catch → `NextResponse.json`.

- [ ] **Step 1: Create each route** from the template, e.g. `investigation/[id]/route.ts`:
```typescript
import { NextResponse } from 'next/server';
import { getInvestigation } from '@/lib/scientific-literature';
export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  try { const { id } = await params; return NextResponse.json(await getInvestigation(id)); }
  catch (e) { return NextResponse.json({ error: String(e) }, { status: 500 }); }
}
```
(Repeat for the others; `[curie]` routes decode the param.)
- [ ] **Step 2: Commit.**

---

### Task 3: Home hub — Investigations + Collections

**Files:** Create `dashboard/pages/scientific-literature/page.tsx` + `components/hub.tsx`.

**Interfaces:** Renders two panels: investigation cards (question + type badge → `/investigation/[id]`) and
collection cards (→ `/corpus/[id]`).

- [ ] **Step 1: `page.tsx`** → `<Hub />`. **Step 2: `components/hub.tsx`** (`'use client'`) fetches
  `/api/scientific-literature/investigations` and `/api/scientific-literature/corpora`, renders two `Panel`s of
  cards; investigation card shows `question` (or name) + a type badge; clicking routes to `/investigation/${id}`.
- [ ] **Step 3: `make build-dashboard`, load `/scientific-literature`**, confirm both panels populate; screenshot.
- [ ] **Step 4: Commit.**

---

### Task 4: Investigation dispatch + Template A (KQED narrative)

**Files:** Create `dashboard/pages/scientific-literature/investigation/[id]/page.tsx`,
`components/investigation-kqed.tsx`, `components/mechanism-graph.tsx`.

**Interfaces:** The page fetches the investigation, reads its `type`, and renders template A or B via
`templateFor(type)`. Template A renders question → analysis (synthesis notes w/ stance badges + evidence chips)
→ S1/S2/S3 sections, with the mechanism graph as SVG.

- [ ] **Step 1: `page.tsx`** (server) loads `getInvestigation(id)` once, passes `type` + data to a client
  dispatcher that renders `<InvestigationKqed/>` or `<InvestigationTable/>` per `templateFor(type)`.
- [ ] **Step 2: `components/investigation-kqed.tsx`** — `HeaderStrip` with the **question**; a "Analysis" `Panel`
  rendering each synthesis note via `MarkdownContent` with a **stance badge** (`consensus|contested|emerging`)
  and **evidence chips** (links to `/paper/[id]` and `/concept/[curie]`); then `Panel`s for **S1 Discourse**
  (claims/hinges/CFC + cross-facet table), **S2 Epistemology** (observations by knowledge-level×bio-scale + gaps),
  **S3 Mechanism** (`<MechanismGraph/>`).
- [ ] **Step 3: `components/mechanism-graph.tsx`** — adapt `embedding-map.tsx`: nodes = grounded bioentities
  (label = CURIE/name), edges = `scilit-mechanistic-link` (`<line>` + arrowhead, color by `scilit-mech-type`);
  reuse the `toX/toY` scaling + hover `<title>`; clicking a node routes to `/concept/[curie]`. Simple force-free
  layout (circular or grid by degree) — no external lib.
- [ ] **Step 4: `make build-dashboard`**, load a `kqed`/`deep-dive` investigation (the SIRT3 deep-dive); confirm
  question + analysis + SVG mechanism render; chips navigate to paper/concept; screenshot.
- [ ] **Step 5: Commit.**

---

### Task 5: Template B — Survey/meeting tabular reader

**Files:** Create `components/investigation-table.tsx` (+ the `[id]/table` route already in Task 2).

**Interfaces:** Renders the document × notes grid from `getInvestigationTable(id)`.

- [ ] **Step 1: `components/investigation-table.tsx`** (`'use client'`) — a sortable/filterable HTML table:
  rows = documents (`scilit-paper` + `scilit-session`), columns = key attributes + their notes
  (`scilit-experience-note`/sensemaking). Rows link to `/paper/[id]` (or a session detail). A text filter box
  filters client-side (display-only — no server round-trip that triggers work). No analysis/graph.
- [ ] **Step 2: `make build-dashboard`, load the CAIS investigation** (`survey` type) at `/investigation/[id]`;
  confirm it renders the table (NOT the KQED stack); screenshot.
- [ ] **Step 3: Commit.**

---

### Task 6: Concept + Paper (KQED-first) views

**Files:** Create `pages/.../concept/[curie]/page.tsx` + `components/concept-detail.tsx`; rebuild
`pages/.../paper/[id]/page.tsx` + `components/paper-detail.tsx` to the KQED-first layout.

**Interfaces:** Concept = ontology-term hub; Paper = Layer-1 sensemaking + grounded concepts + fragments.

- [ ] **Step 1: `concept-detail.tsx`** — from `getConcept(curie)`: label, definition, `scilit-ontology-source`,
  a **CURIE → OLS link** (`https://www.ebi.ac.uk/ols4/ontologies/{src}/...` or `https://bioregistry.io/{curie}`),
  synonyms, and lists of bioentities/claims/observations grounded to it (links out).
- [ ] **Step 2: Rebuild `paper-detail.tsx`** to show the paper's Layer-1 sensemaking from
  `getPaperSensemaking(id)` (observations, claims, mechanism) + grounded concept chips + full-text fragments;
  keep the existing notes/PDF-artifact rendering.
- [ ] **Step 3: `make build-dashboard`**, load `/concept/<curie>` (OLS link works) and `/paper/<id>`; screenshot.
- [ ] **Step 4: Commit.**

---

### Task 7: Wiring, read-only invariant, end-to-end verification

**Files:** Modify `skills-registry.yaml` (dashboard block), `dashboard/public/skills-config.json` (already
registered — refresh name/description to the KQED dashboard).

- [ ] **Step 1: Refresh registry/config** name → "Scientific Literature (KQED)", description → the sensemaking
  framing; `make build-dashboard`.
- [ ] **Step 2: Read-only invariant check** — grep the skill's `dashboard/routes/` for any verb that is not
  `show-*`/`list-*`:
```bash
grep -rEo "runScilit\(\['[a-z-]+" dashboard/routes | sort -u
```
Expected: only `show-*`/`list-*` verbs. Any `ground-*`/`analyze-*`/`sensemake-*`/`set-*` in a route is a defect.
- [ ] **Step 3: End-to-end (per master plan verification):** hub loads (investigations + collections); the SIRT3
  `kqed` investigation → question + analysis (stance badges) + SVG mechanism, chips → paper/concept → fragment;
  the CAIS `survey` investigation → tabular reader; `/concept/<curie>` OLS link resolves; no file written to the
  repo root; screenshots in `~/.alhazen/cache/screenshots/`.
- [ ] **Step 4: Commit** — `git commit -am "feat(scilit-dash): KQED read-only dashboard (hub + templates A/B + concept/paper)"`

---

## Self-Review notes
- Every view reuses the canonical page→route→component template and `atoms.tsx`/`tokens.ts`; only the
  mechanism graph adds code (adapted from `embedding-map.tsx`, no new dependency).
- The template registry (`templateFor`) is the single dispatch point; unknown types default to the tabular
  reader, so adding a future view kind is a new component + one registry entry.
- Read-only invariant is explicitly grepped (Task 7 Step 2) — the architectural contract is testable.
- All four read verbs consumed here (`list-investigations`, `show-investigation`, `show-investigation-table`,
  `show-concept`, `show-paper-sensemaking`) are defined in P1–P3 or P4 Task 1 Step 2.
