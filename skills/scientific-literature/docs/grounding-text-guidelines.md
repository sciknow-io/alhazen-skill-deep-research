# Grounding Text Guidelines — what to generate as the groundable label

When capturing an entity during per-paper sensemaking, record **two** things:

1. `name` — the **verbatim mention** as it appears in the paper (for provenance/display).
2. `scilit-grounding-label` — the **canonical full expression** submitted to the ontology lookup.

Ontology search matches on canonical **labels and synonyms**, not on lab shorthand. Abbreviations and
compound phrases fail the QC gate (fuzzy/ambiguous/unresolved) and land in `needs-review`. Generating a
clean `scilit-grounding-label` is what lifts grounding recall (validated on the Hallmarks vocabulary:
~2/40 with verbatim names → 6/9 with full expressions).

## Rules for the grounding label

1. **Expand every abbreviation / acronym to its full canonical name.**
   - `ROS` → `reactive oxygen species` · `HSC` → `hematopoietic stem cell` · `Tregs` → `regulatory T cell`
2. **One atomic entity per label.** Split conjunctions and combinations.
   - `DHEA and metformin` → two entities: `dehydroepiandrosterone`; `metformin`
3. **Strip qualifiers, context, treatments, dosages, and timing** — keep the core entity; move the rest to
   the verbatim `name` or the surrounding claim/observation text.
   - `intratumoral regulatory T cells (Tregs)` → `regulatory T cell`
   - `GH-induced hyperinsulinemia` → `hyperinsulinemia`
   - `12-hour fasting interval` → `fasting`
   - `AAV9-Tert / telomerase (TERT)` → `telomerase`
4. **Use the singular, scientific noun form** (ontology label convention), not plurals or lab usage.
   - `mitochondria` → `mitochondrion` · `naive CD4/CD8 T cell pool` → `naive T cell` (or split CD4/CD8)
5. **Use the standard nomenclature for the entity kind:**
   - chemical/metabolite → IUPAC or common chemical name (CHEBI label form)
   - cell type → canonical cell-type name (CL label form)
   - process → the process noun phrase (GO label form: `autophagy`, `cellular senescence`, `chromatin organization`)
   - phenotype → the clinical/phenotype term (HP label form)
   - anatomy/tissue → the anatomical term (UBERON label form)
6. **Drop parentheticals and editorial gloss** that aren't part of the name.
   - `8-oxoguanine (oxidative DNA lesion)` → `8-oxoguanine`
7. **Genes/proteins:** use the full protein/gene name, not just the symbol — but note OLS/PR coverage is
   thin and often returns species-specific entries; molecular actors frequently still land `needs-review`
   pending a dedicated resolver (UniProt/HGNC). Capture the full name anyway (`SIRT3` → `sirtuin 3`,
   `SOD2` → `superoxide dismutase 2`) so the dedicated resolver can use it later.
8. **Prefer the higher-level canonical concept (conservative lump/split).** Ground to the most specific term
   that is *unambiguous and exact*; if only a hyper-specific compound exists, generalize to the canonical
   parent and let the verbatim `name` + the claim text carry the specific detail. Do NOT invent fine terms.
9. **If no clean canonical form exists, leave it ungrounded.** `ungrounded` is first-class and visible; a
   wrong grounding is worse than none.

## Quick reference

| Verbatim mention (`name`) | Grounding label (`scilit-grounding-label`) | Kind |
|---|---|---|
| ROS | reactive oxygen species | chemical |
| HSC / HSC function | hematopoietic stem cell | cell_type |
| mitochondria | mitochondrion | (cell component) |
| GH-induced hyperinsulinemia | hyperinsulinemia | phenotype |
| intratumoral Tregs | regulatory T cell | cell_type |
| AAV9-Tert / telomerase (TERT) | telomerase | protein |
| DHEA and metformin | dehydroepiandrosterone · metformin (2 entities) | chemical |

The agent generates `scilit-grounding-label` during capture; grounding (`ground-entity`, `survey-entities`)
uses it in preference to the verbatim `name`.
