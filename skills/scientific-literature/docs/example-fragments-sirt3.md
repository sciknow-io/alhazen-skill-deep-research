# Worked Example — Fragment Extraction & Referencing (SIRT3 paper)

**Companion to** `example-kqed-sirt3.md`. Same paper (`10.1016/j.celrep.2013.01.005`, `scilit-paper-a5c569d48e76`).
**Question this answers:** how does every derivative note in the KQED study (claims, observations, gaps, KEfED protocols, domain-relations) stay anchored to the **verbatim text** that justifies it — so the whole body of work is traceable, correctable, and re-hydratable for an LLM?

---

## 1. The principle — fragments are *shared evidentiary atoms*

A **fragment** is a span of the paper's canonical full text, stored once. Derivative notes do **not** copy text; they **reference** fragments. This gives two properties that matter:

- **Many notes → one fragment.** A single result sentence supports an observation *and* a claim *and* a domain-relation. (F8 below supports four notes.)
- **One note → many fragments.** A synthesized claim is grounded in several spans across abstract/results/discussion. (C1 below cites three fragments.)

The fragment is the **crisp↔soft bridge**: crisp because it's a typed node with an exact locator; soft because it points at verbatim prose an LLM can re-read.

---

## 2. The model — three reference axes (no new core types needed)

```
scilit-pdf-fulltext  (the whole artifact; cache-path → the extracted text file)
        │  alh-fragmentation (whole → part)        ← locator / provenance to the source
        ▼
scilit-fragment  (sub alh-fragment)
        owns: content (verbatim quote), offset, length   ← resolves back into the full text
        owns: a locator (section / figure / "SUMMARY")
        subtypes: scilit-sentence · scilit-figure(legend) · scilit-section · scilit-methods-step

derivative-note ──alh-derivation(derivative → derived-from-source)──▶ scilit-fragment
                  "this note is GROUNDED IN this text"   ← the support/evidence edge

derivative-note ──alh-aboutness(note → subject)──▶ domain-thing | paper
                  "this note is ABOUT SIRT3 / about the focal paper"   ← orthogonal, semantic
```

**The key clarification:** *grounding* and *aboutness* are different edges on different axes. Claim C1 is **about** SIRT3 (`alh-aboutness → SIRT3`) **and** **derived from** fragment F8 (`alh-derivation → F8`). One says *what it concerns*; the other says *what text backs it*. Both already exist in core (`alh-note` and `alh-fragment` are ICEs that play `alh-derivation`; `alh-fragment` plays `alh-fragmentation:part`), so the fragment layer needs **no new entity types** — only `scilit-fragment` subtypes and population.

---

## 3. The extracted fragments (real spans, real offsets)

Offsets are into the canonical single-space full text (`len = 39,709` chars) derived from the `scilit-pdf-fulltext` cache. Each is a `scilit-fragment` whose `content` is the verbatim quote.

| id | type | locator | offset | verbatim (anchor) |
|---|---|---|---|---|
| F1 | sentence | SUMMARY | 953 | "Whether sirtuins can reverse aging-associated degeneration is unknown." |
| F2 | sentence | SUMMARY | 1612 | "SIRT3 is suppressed with aging, and SIRT3 upregulation in aged HSCs improves their regenerative capacity." |
| F3 | sentence | INTRO | 2705 | "it is unclear whether sirtuins can reverse, as opposed to simply slow, aging-associated degeneration" |
| F4 | sentence | INTRO | 4074 | "Is stem cell aging a chronic result of cumulative oxidative damage or an acute effect of increased ROS levels?" |
| F5 | sentence | RESULTS (Fig 1A–C) | 6965 | "SIRT3 mRNA levels were about 3,000-fold higher in HSCs and MPPs than in differentiated blood cells." |
| F6 | sentence | RESULTS (Fig 1D–F) | 7652 | "no difference in the number of … enriched HSPCs or highly enriched HSCs was observed between WT and SIRT3 KO mice." |
| F7 | sentence | RESULTS (Fig 2A–C) | 9387 | "The size of both HSPC and HSC compartments was 50% smaller in aged … SIRT3 KO mice compared to their WT littermates." |
| F8 | sentence | RESULTS (Fig 4D–F) | 22000 | "SIRT3 overexpression resulted in a 5-fold increase in functional reconstitution …" |
| F9 | sentence | RESULTS (Fig 3E) | 17404 | "NAC treatment rescued reconstitution defects of aged SIRT3 KO HSCs … demonstrating that oxidative stress indeed compromises HSC function …" |
| F10 | sentence | RESULTS (Fig 3G) | 19857 | "the enzymatic activity was 50% lower in SIRT3 KO HSPCs compared to WT controls." |
| F11 | sentence | RESULTS (Fig 4G) | 23126 | "SOD2 K53/89R improved the survival of HSCs by 67%, whereas WT SOD2 had no effect." |
| F12 | sentence | RESULTS (Fig 3I–J) | 20615 | "SIRT3 mRNA levels were 70% lower in HSPCs of old mice compared to those in young mice." |
| F13 | sentence | DISCUSSION | 26866 | "Future studies will determine the effect of SIRT3 on lifespan." |
| F14 | methods-step | EXP. PROC. (Transplantation) | 30546 | "… BM cells from WT or SIRT3 KO CD45.2 littermates was mixed with … CD45.1 … competitor cells and injected into lethally irradiated (950 Gy) … recipients." |
| F15 | methods-step | EXP. PROC. (Lentiviral) | 32584 | "SIRT3, SOD2, and SOD2 K53/89R were cloned into pFUGW lentiviral construct …" |
| F16 | sentence | DISCUSSION | 24964 | "we do not rule out the possibility that chronic oxidative damage to cellular components contributes …" |

---

## 4. The reference matrix — which notes cite which fragments

(Notes are from `example-kqed-sirt3.md`. ● = `alh-derivation` edge note → fragment.)

| note | F1 | F2 | F3 | F4 | F5 | F6 | F7 | F8 | F9 | F10 | F11 | F12 | F13 | F14 | F15 | F16 |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| **C1** reversal (primary) | ● | ● | | | | | | ● | | | | | | | | |
| **C2** necessary/dispensable | | | | | | ● | ● | | | | | | | | | |
| **C3** suppressed with age | | ● | | | | | | | | | | ● | | | | |
| **C5** SIRT3→SOD2 mech | | | | | | | | | | ● | ● | | | | | |
| **C6** acute/reversible ROS | | | | ● | | | | | ● | | | | | | | ● |
| **G1** reverse unknown | ● | | | | | | | | | | | | | | | |
| **G2** reverse vs slow | | | ● | | | | | | | | | | | | | |
| **G3** chronic-vs-acute Qs | | | | ● | | | | | | | | | | | | |
| **G4** chronic not excluded | | | | | | | | | | | | | | | | ● |
| **G6** lifespan (future work) | | | | | | | | | | | | | ● | | | |
| **O** SIRT3 enriched (1A–C) | | | | | ● | | | | | | | | | | | |
| **O** young-null (1D–K) | | | | | | ● | | | | | | | | ● | | |
| **O** old-deficit (2A–G) | | | | | | | ● | | | | | | | ● | | |
| **O** NAC rescue (3E) | | | | | | | | | ● | | | | | ● | | |
| **O** SOD2 activity (3G) | | | | | | | | | | ● | | | | | | |
| **O** SIRT3↓ age (3I–J) | | | | | | | | | | | | ● | | | | |
| **O** 5-fold rescue (4D–F) | | | | | | | | ● | | | | | | | ● | |
| **O** epistasis (4G) | | | | | | | | | | | ● | | | | ● | |
| **kefed T2** (LoF transplant) | | | | | | | | | | | | | | ● | | |
| **kefed T3/T5** (GoF/epistasis) | | | | | | | | | | | | | | | ● | |
| **rel** SIRT3→SOD2 | | | | | | | | | | ● | ● | | | | | |
| **rel** aging⊣SIRT3 | | | | | | | | | | | | ● | | | | |
| **rel** SIRT3-OE→HSC-fn | | | | | | | | ● | | | | | | | | |
| **rel** ROS⊣HSC-fn | | | | | | | | | ● | | | | | | | |

### Two reuse cases that prove the point

- **F8 → 4 notes.** The single sentence *"SIRT3 overexpression resulted in a 5-fold increase in functional reconstitution"* grounds the **observation** (4D–F), the primary **claim C1**, the **sufficiency interpretation**, and the **domain-relation** `SIRT3-OE → HSC-function`. One span, four crisp nodes — no duplicated prose, and editing the fragment (or re-reading it) propagates to all four.
- **C1 ← 3 fragments.** The reversal claim is grounded in F1 (the stated unknown it answers), F2 (the abstract's result statement), and F8 (the in-vivo result). Its justification is a *set* of spans, each independently checkable.

Note the **methods fragments (F14, F15)** ground the **KEfED templates** — the protocol text *is* where parameters/measurements are read from (T2's `{genotype, age, stress}`, the competitor ratio constant, the 950 Gy irradiation; T3/T5's lentiviral constructs). So the same fragment layer feeds System-2 structure, not just System-1 claims.

---

## 5. How fragments get extracted (two complementary modes)

1. **Structural pre-fragmentation (deterministic).** Split the `scilit-pdf-fulltext` into `scilit-section` → `scilit-paragraph` → `scilit-sentence`, and parse figure legends → `scilit-figure`, methods steps → `scilit-methods-step`. Each gets offset/length + locator up front. This populates the fragment store independent of any note.
2. **On-demand span promotion (when a note is authored).** When the `is explained by` / `analyze` arc produces a note, it cites the supporting span (verbatim or char-range). The span is resolved against the structural fragments; an exact/overlapping match reuses that fragment, a novel span is **promoted** to a new `scilit-fragment`. This is how the crisp node acquires its `alh-derivation` edge.

In practice the LLM does (2) at note-creation time, and (1) provides the stable index it snaps to.

---

## 6. Why this is the payoff of the crisp/soft contract

- **Traceability / audit.** Every node in the KQED graph resolves to ≥1 verbatim span at a precise offset — click-through from a claim to the sentence that states it.
- **Correctability.** Re-running the `is explained by` arc (e.g., the model version changes) re-reads the *same* immutable fragments; only the interpretation edge changes. Fragments never move.
- **Focused LLM context.** To work a problem, query the crisp graph for the relevant notes, then **hydrate** exactly their referenced fragments (F-set) — a minimal, on-point bundle instead of the whole PDF. The reference matrix *is* the retrieval plan.
- **No duplication.** N notes share M fragments; the body of work is a graph over a single text, not N copies of quoted prose.

---

## 7. Schema instances this example writes

- `scilit-fragment` ×16 (F1–F16) — `content` + `offset` + `length` + locator; subtypes sentence/figure/methods-step.
- `alh-fragmentation` ×16 — each fragment → the `scilit-pdf-fulltext` whole.
- `alh-derivation` ×~40 — the ● edges in §4 (note → fragment).
- (unchanged) `alh-aboutness` — each note → its domain subject (SIRT3, HSC, …), the orthogonal axis.

**Design confirmations from doing it for real:**
- The **sentence** is the natural default fragment grain; figure-legend and methods-step are the other two that earn their keep (methods-steps feed KEfED).
- `alh-derivation` (not `alh-aboutness`) is the right edge for *textual grounding* — keeps "what backs it" separate from "what it's about."
- Reuse is heavy (F8, F12, F2 each back ≥2 notes), so storing text **once** in the fragment and referencing it is clearly correct over per-note quotes.
```
