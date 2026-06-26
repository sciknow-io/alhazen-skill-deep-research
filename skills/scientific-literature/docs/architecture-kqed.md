# KQED — A Scientific Sensemaking Architecture for the Alhazen Notebook

**Status:** design (living document)
**Scope:** the `scientific-literature` skill and the core Alhazen schema it builds on
**Provenance:** synthesized from a design dialogue grounding four bodies of work — Teufel's argumentative zoning, Boguslav et al.'s ignorance-base, the KEfED experimental-design formalism (Burns et al.), and the ignorome/knowledge-graph enrichment line (Callahan, Hunter et al.) — onto the KQED process model.

---

## 1. Value proposition

> Given a target, mechanism, or interpretive framework (e.g. the *hallmarks of aging*) and a goal, produce a concise, navigable map of **(1)** what a body of work *claims* and under which framework, **(2)** the *type and depth of evidence* beneath each claim, traced to the experiments that produced it, and **(3)** the *graded gaps* — the known unknowns that mark where the next experiment should go, each carrying an actionable knowledge goal.

A plain LLM summary delivers only (1). Adding (2) gives *trust* — every claim traced to its experimental warrant. Adding (3) gives the *differentiator*: not just what is known, but where the frontier is and what experiment would move it. This is a decision-support artifact, not a digest.

The platform must be **extensible** (new domains and experiment types plug in), **correctable** (interpretations revise cheaply without disturbing the data beneath), and able to **serve focused, relevant, complex content to LLMs** solving specific problems.

---

## 2. The KQED process model

KQED replaces the older "Cycle of Scientific Investigation" (CoSI) as the process backbone. It is a 2×2 over a **`theory | evidence`** divide, cycling clockwise:

```
            theory            │            evidence
   ┌──────────────────────┐   │   ┌──────────────────────┐
   │  KNOWLEDGE     [ KG ] │◄──┼───│  DATA      [ M bar* ]│
   └───────────┬──────────┘  is explained by ───────────┘
               │ analyze      │              ▲ execute
               ▼              │              │
   ┌──────────────────────┐   │   ┌──────────────────────┐
   │  QUESTIONS      [ ? ] │───┼──►│ EXPERIMENT [ P→A→M ] │
   └──────────────────────┘  design ──────────────────────┘
```

**Four states (the nouns):**

| State | Side | Meaning | Glyph |
|---|---|---|---|
| **K — Knowledge** | theory | synthesized, established understanding; the domain model | knowledge graph |
| **Q — Questions** | theory | open questions, hypotheses, known unknowns | `?` |
| **E — Experiment** | evidence | the experimental *design* (a KEfED protocol) | `P→A→M` |
| **D — Data** | evidence | the raw measurements produced by an experiment | bar chart + `✱` |

**Four arcs (the verbs):**

| Arc | Label | Operation |
|---|---|---|
| K→Q | **analyze** | mine knowledge for the adjacent possible → questions/gaps |
| Q→E | **design** *(crosses the divide)* | turn a question into a testable experimental design |
| E→D | **execute** | obtain measurements in their protocol context |
| D→K | **is explained by** *(crosses the divide)* | abductively fit data back to theory |

**Two structural facts the diagram asserts:**

1. **The `theory | evidence` line is the load-bearing axis.** The left side (K, Q) is revisable and model-laden; the right side (E, D) is stable and observational. This single line *is* both the KEfED observation↔interpretation boundary and the crisp↔soft representational boundary (§5).
2. **Only two arcs cross the line, and they are the hard ones:** `design` (theory commits to a test) and `is explained by` (evidence updates theory). The within-side arcs (`analyze`, `execute`) are comparatively mechanical. **Platform value concentrates on the two crossing arcs.**

KQED is the **process / skill layer**. It is deliberately separated from the **representational substrate** — the three orthogonal systems of §3, which *live on* the states.

---

## 3. Three orthogonal representational systems

Every assertion in the notebook has **independent coordinates on three axes**. Keeping them orthogonal is the core design discipline; collapsing them is how this kind of model rots.

> **Design principle — notebook-defined schemas; standards are optional.**
> The platform is **agnostic over mechanistic modeling**. An Alhazen notebook **defines its own schema, specialized for its particular use case** — it is not required to adopt any external standard. Existing ontologies and formalisms (named throughout this document) are **optional reference vocabularies, prior art to borrow from, and interop targets** — never a mandated backbone. This applies most strongly to System 3 (mechanistic), but the same rule holds wherever a standard is cited: use it if it fits the use case, replace it freely if it does not. The only load-bearing commitments are the *patterns* (the KQED process, the observation↔interpretation split, the crisp/soft contract), not any particular controlled vocabulary.
>
> **Staged adoption — anchor → extend → specialize.** The intended path is staged, not all-or-nothing: **(1) anchor** on a reference point that mostly fits (a vocabulary, ontology, or formalism); **(2) extend** it with notebook-specific types/attributes/relations where the use case exceeds it; **(3) specialize** into a schema the notebook owns. Each stage stays interoperable with its anchor — extensions are additive and a mapping back to the reference is retained — so a notebook can re-export to the standard or swap anchors later. Standards are the *scaffold you start from and grow past*, not a ceiling. The references in §13 are entry points for stage (1), nothing more.

> Example — *"KO of gene X accelerates senescence"* is simultaneously:
> - **Rhetorically** an `OWN`/AIM claim;
> - **Epistemically** a *sufficiency*-warrant interpretation derived from a loss-of-function KEfED model with parameters {gene, perturbation, readout};
> - **Mechanistically** a causal edge `X —accelerates→ senescence`.

| System | Answers | Lives on (KQED) | Grounding frameworks |
|---|---|---|---|
| **1 · Rhetorical** | What is *said* (and flagged unknown)? | **K** (claims) + **Q** (gaps/hypotheses) | Teufel (AZ/CFC/hinges) + Boguslav (ignorance) |
| **2 · Epistemic** | What is *shown*, and what does it *license*? | **E** (KEfED) + **D** (observations) | KEfED + EFO + OBI; ECO/SEPIO/Biolink vocabularies |
| **3 · Mechanistic** | What is *modeled* (domain theory)? | **K** (the knowledge graph) | **notebook-defined domain schema** (anchored on prior art only as far as it fits — §3.3) |

### 3.1 System 1 — Rhetorical (sensemaking over discourse)

A sensemaking layer over published material (and any other signal we can find). It types *what scientists are doing argumentatively* and *what they flag as unknown*.

**Teufel — argumentative structure** (*The Structure of Scientific Articles*, 2010). Three reliably human-annotatable schemes projected from one model (KCDM):

- **AZ (Argumentative Zoning)** — 7 sentence-level zones: `AIM, OWN, BACKGROUND, CONTRAST, BASIS, OTHER, TEXTUAL`.
- **CFC (Citation Function)** — 12 citation functions grouped by stance: `Weak`; contrastive `CoCo- / CoCoGM / CoCoR0 / CoCoXY`; positive `PSup / PBas / PUse / PModi / PSim / PMot`; `Neut`.
- **Hinges (H-1..H-18)** — the relations between knowledge claims (new KC ↔ existing KC), which CFC groups. **Hinges are the claim↔claim relation the current model lacks.**

**Boguslav — statements of ignorance** (*Creating an Ignorance-Base*, 2023). A statement of missing/incomplete knowledge that *implies a knowledge goal*. Annotated as `scope` (sentence) → `lexical cue(s)` → `ignorance category`. The 13 categories double as a research life-cycle and as the **adjacent possible** — each entails an actionable next step (see §8.2). This populates the **Q** node.

**The seam between Teufel and Boguslav** (System 1's internal structure): they are different axes — Teufel hinges are *relational/inter-claim*; Boguslav categories are *monadic/meta-epistemic*. Their overlap is concentrated entirely on the **negative** hinges:

- Positive hinges (`PUse/PBas/PSup/PSim/PMot`) assert *knowledge* → no ignorance overlap; they *consume/resolve* gaps.
- Negative hinges (`Weak`, `CoCo-`) and the gap-ish moves (`R-6` no-solution, `R-11` limitations, `R-12` future-work) *expose* ignorance → they co-locate with Boguslav statements.

Consequence: **a gap node has two provenance sources** — an *explicit* Boguslav cue, or one *inferred* from a negative hinge. A gap found both ways is high-confidence; a gap implied by contrast but never stated outright is a discovery. The `analyze` (K→Q) arc runs both detectors.

### 3.2 System 2 — Epistemic (KEfED)

The constructive backbone for *what the data actually supports*. Where ECO only *labels* a warrant, **KEfED constructs it from the experimental design** (Russ, Ramakrishnan, Hovy, Bota & Burns, *BMC Bioinformatics* 2011).

Two ideas do the work:

1. **Observation vs. interpretation as distinct assertion types.** *Observational* assertions are formulated without background knowledge (only enough to fix terminology); *interpretational* assertions invoke the domain model. The defining property: **if the background knowledge changes, the interpretation changes, while the observation stays fixed.** This is the platform's correctability invariant (§9).

2. **Workflow-indexed measurement context.** A KEfED model is the protocol as a graph of `Object`s and `Activity`s (with `Branch`/`Fork` control flow) carrying `Variable`s = `Parameter` | `Constant` | `Measurement`. **Each measurement is contextualized by the parameters on its path back through the protocol** — that path *is* the warrant. The warrant→claim-level mapping (§7) is therefore *derived from the KEfED graph*, not hand-assigned.

**EFO (Experimental Factor Ontology)** annotates the `Parameter`/`Constant` variables (cell line, compound, dose, time, assay, perturbation). **OBI** annotates the `Activity`/`Object` process elements. **OBO** ontologies ground the entities.

**Data landscapes per subdiscipline.** A subdiscipline's data landscape = the **EFO-factor-spanned parameter space of its canonical KEfED template**. Measurements populate it; **unsampled regions of that space are structural ignorance** (the geometric, ignorome-style counterpart to Boguslav's textual ignorance). "Which factors matter" = which parameters, when varied, move the measurement or interpretation.

**Optional typing vocabularies** (stage-(1) anchors a notebook may adopt for the evidence axis, then extend — typing, not structure):
- **ECO** / GO evidence codes — evidence-type labels (e.g. `IDA, IMP, IPI, IGI, IEP`).
- **Biolink `knowledge_level`** — `observation → statistical_association → knowledge_assertion → logical_entailment → prediction`; plus `agent_type`.
- **SEPIO** — the recursive `Assertion ← Evidence Line ← Evidence Item(s)` axis, and *assertion-supports-assertion*, for multi-experiment aggregation into higher-level claims.

(KEfED's observation/interpretation split and workflow-indexed context are the load-bearing *pattern*; the vocabularies above are anchors, swappable per use case.)

### 3.3 System 3 — Mechanistic (domain logic)

How the domain is actually represented: drug discovery, fundamental biology, signal-transduction pathways, genetics. This is the **K** node's knowledge graph — domain entities (`alh-domain-thing`) connected by **typed relations the notebook defines for its use case**.

**This layer is deliberately notebook-defined and standard-agnostic.** There is no mandated mechanistic formalism. A notebook authors the entity types, relation types, and value sets that fit *its* mechanistic questions — a signal-transduction notebook, a genetics notebook, and a drug-discovery notebook will each carry a different System-3 schema, and that is the point. The platform commits only to the *pattern*: domain entities + typed relations that interpretational assertions assemble into.

Prior art serves only as **stage-(1) anchors** to start from and extend (per the staged-adoption principle), never as a required backbone:

- *Causal-statement formalisms* (e.g. INDRA's typed mechanistic statements with belief aggregation and executable export; GO-CAM / BEL causal triples) — useful **reference points** if a notebook needs causal mechanism + multi-evidence belief + simulation, and a good interop target — but a notebook is free to define a coarser or richer relation set.
- *Large biomedical KGs* (e.g. PheKnowLator-shaped gene–GO–pathway–disease–drug–phenotype graphs) — a reference for graph *shape* and a substrate for enrichment, adopted only as far as a use case wants it.

The interpretational assertions produced by the `is explained by` arc *assemble into* whatever schema the notebook defines; the graph's missing or contradictory edges are exactly the gaps that re-enter **Q**. Because System 3 is the most use-case-specific layer, it is also the one most expected to start from a reference anchor and grow its own specialized types.

---

## 4. The unifying operation: enrichment

A single statistical primitive serves all three systems: **"which concepts are over-represented in {a rhetorical class / an evidence class / an ignorance category} versus a background?"**

- Teufel-enrichment — which concepts cluster in `CONTRAST` zones.
- **Ignorance enrichment** (Boguslav) — which concepts are over-represented in ignorance statements; surfaces topics "ripe for exploration" and, run over an experimental gene list, **points to an implied field holding the answers** (cross-disciplinary hypothesis formation).
- KG-embedding enrichment (the ignorome papers) — nearest mechanisms in embedding space.

Build the enrichment primitive once; apply it per layer.

---

## 5. The crisp / soft contract (two-tier neuro-symbolic representation)

The `theory | evidence` line is also the boundary between **database-precision** and **embedded-complexity**. The platform is deliberately two-tier with one bridge:

- **Crisp tier (TypeDB):** typed nodes/edges with defined value sets — KEfED variables, EFO/OBI/OBO terms, claim/evidence/gap/interpretation nodes, mechanistic edges, knowledge-level/warrant. Queryable, reasoned-over, correctable. *(K is most crisp; Q is half-crisp.)*
- **Soft tier (cache + embeddings/Qdrant):** the artifacts whose semantics resist typing — fragments, protocol prose, data tables, figures, code. *(D is most soft; E bridges.)*
- **The bridge (already in the schema):** every crisp node points to its soft source via `alh-aboutness` + `cache-path`; every soft fragment can be *promoted* into crisp structure by annotation. The `alh-sensemaking-note` (fragment-anchored, AZ/ignorance-typed) is exactly this bridge object.

**The crisp graph is the *selector*, not just the store.** To solve a specific problem: query the KG for the relevant claims/observations/gaps (precise, typed, reasoned), then *hydrate* them with their embedded fragments and feed that minimal bundle to the LLM. Graph-driven retrieval beats vector-only RAG on precision. The LLM operates at the boundary in both directions — reading soft content to produce/correct crisp structure (the `design`/`explain` arcs), and consuming crisp structure to fetch the right soft content.

---

## 6. The four arcs as agent operations (skills)

Each arc is a distinct operation with a clear I/O and a powering framework. This is the platform's module decomposition.

| Arc | Operation | Input → Output | Powered by |
|---|---|---|---|
| **K→Q `analyze`** | surface the adjacent possible | knowledge graph + corpus → ranked questions/gaps `{category, knowledge-goal}` | Boguslav ignorance + negative-hinge gaps; ignorance enrichment |
| **Q→E `design`** *(crossing)* | turn a question into a testable design | gap + target claim-level → KEfED protocol + EFO factors to vary | the **warrant table** (§7) read in reverse |
| **E→D `execute`** | obtain measurements in context | KEfED model → observational assertions | KEfED workflow indexing; for literature: *extract* P/A/M from the paper |
| **D→K `is explained by`** *(crossing)* | abductively fit data to theory | observations → updated claims / mechanistic model + flagged anomalies | KEfED interpretation + the notebook's own domain model (assembly à la INDRA/GO-CAM optional) |

Two consequences:

- **`is explained by` is abductive** (inference to the best explanation) — the framing already used by the `literature-trends` skill. KEfED's invariant bites here: the same D, under a revised K, yields a different explanation. **Re-running D→K is the correctness mechanism.**
- **The loop never closes cleanly, and that is the product.** An explanation that *fails* (an anomaly the model can't account for) emits a new Question. Gaps are the **residue of the `explain` arc**, not a static layer.

---

## 7. The warrant table (experiment → claim level)

The substance of the `design` and `explain` arcs: *which experiments license which mechanistic claims, at what level*. The level of claim you can make is **bounded by the experiment type** — and it is derivable from the KEfED parameter/measurement structure.

| Experiment / data | Mechanistic claim licensed | Knowledge level |
|---|---|---|
| DEG / GWAS / co-expression / correlation | **association only** — *not* causal | observation / association |
| Physical assay (co-IP, Y2H, ChIP) | **interaction / complex** — binding, no direction | assertion (structural) |
| Loss-of-function (KO, KD, CRISPR) + phenotype | **necessity** (causal) | assertion (causal) |
| Gain-of-function (overexpression) + phenotype | **sufficiency** (causal) | assertion (causal) |
| Dose-response / time-course / rescue | **quantitative, directional** mechanism | assertion → prediction |
| Structural / biochemical reconstitution | **direct molecular mechanism** | strongest |

**The Layer B / Layer C junction:** a *DEG is an association-level claim, never a mechanism* — which is precisely the ignorome's definition of a gap (experimental signal lacking a mechanistic warrant). **A gap is a claim stuck at a lower warrant level than a mechanism requires; the entailed knowledge goal is "run the experiment type that upgrades it,"** and the warrant table names that experiment. This is the engine behind `design`.

---

## 8. Reference taxonomies

### 8.1 Teufel — AZ zones and CFC functions

- **AZ (7):** `AIM` (research goal), `OWN` (new work — = KCA `New-KC`), `BACKGROUND` (accepted — `No-KC`), `CONTRAST` (criticised/contrasted competitor), `BASIS` (built upon), `OTHER` (other's work — `Ex-KC`), `TEXTUAL` (sign-post sentences).
- **CFC (12):** `Weak`; `CoCo-` (superiority of own KC), `CoCoGM` (contrast in goals/methods), `CoCoR0` (contrast in results), `CoCoXY` (contrast between two existing KCs); `PSup` (support), `PBas` (basis), `PUse` (use), `PModi` (modify), `PSim` (similar), `PMot` (motivation); `Neut`.

### 8.2 Boguslav — 13 ignorance categories (with entailed knowledge goal)

Each category maps a class of lexical cue to an actionable next step. (Corpus frequencies from the 91-article ignorance-base; three broad umbrellas group these in the source.)

| Ignorance category | Knowledge goal (actionable step) | Example cues |
|---|---|---|
| answered research question | find / verify the answer in the article | aim, goal, sought, to determine |
| **unknown / novel** | explore the unknown to gain insight | could not find, elusive, not…established, uncertain |
| explicit research inquiry | answer the question / find methods to | ?, what, why, wondered |
| **proposed / incompletely understood** *(dominant)* | gather more evidence; complete the partial picture; address shortcomings | believe, evidence…limited, hypothesis, no studies, preliminary, support, trend |
| indefinite relationship among variables | confirm the link; determine the full relationship | affect, associated, correlate, influence, interact, link, tend |
| largely understood | test whether the most-likely explanation holds | almost all, assumed, evident, it is clear, most likely |
| anomalous / curious finding | explore the surprise; test repeatability | appeared to be, interestingly, noteworthy, surprisingly |
| alternative options / controversy | resolve disagreement; determine the correct option | cannot rule out, has been challenged, whether, whilst |
| difficult research task | build methods/techniques to study the complicated system | not feasible, remains…challenge, variability |
| problem or complication | assess gravity; decide if it blocks the next experiment | issue, error, insufficient, lack of reproducibility, publication bias |
| future work | determine the next course of action | additional research…needed, further study, recommend, warrants |
| future prediction | run the experiment to test the prediction | allow, expect, if so, will |
| important consideration | take the urgent action / disseminate now | call for action, crucial, emphasis, necessary, relevant |

Note: the `proposed / incompletely understood` category dominates the corpus — most scientific ignorance is *graded/contested understanding needing more evidence*, not total unknown. That is exactly where evidence depth and the hallmark premises live.

### 8.3 KEfED — model elements

`Object` (material/information entity), `Activity` (acts on objects, may transform them), `Branch`/`Fork` (control flow), `Variable ∈ {Parameter, Constant, Measurement}`. A measurement's context = the parameters on its workflow path to the protocol start. One KEfED model is a **template for many experiments**. Elements are annotated with OBI (process/entity), EFO (factors), and domain OBO terms.

---

## 9. Data model — mapping onto the Alhazen schema

The three systems and four states map onto core Alhazen types. Items marked **(new)** are not yet implemented.

### 9.1 Already in place (core curation note subtypes)

```
alh-note
├── alh-sensemaking-note    ← System 1 atomic unit: fragment-anchored, carries
│                              {AZ-zone, ignorance-category, knowledge-goal};
│                              grounded to entities via alh-aboutness; the crisp/soft bridge
├── alh-analysis-note
│   ├── scilit-claim         ← a knowledge claim (K node)
│   ├── scilit-evidence      ← evidence (to be enriched, §9.2)
│   ├── scilit-citation-impact
│   └── alh-analysis-pipeline-note → scilit-faceting-note
└── alh-reporting-note       ← the synthesized framework-map artifact
```

`scilit-investigation` is the container; a generalized core `alh-investigation` note type (so investigations are listable cross-skill) and the tech-recon migration onto it are tracked separately (skillful-alhazen issue #63).

### 9.2 New types by KQED state

| State | New types | Notes |
|---|---|---|
| **K** | `domain-relation` **(notebook-defined)** — typed relation(s) between `alh-domain-thing`s, named/shaped per use case; `domain-model-version` | the notebook authors these; an interpretation *invokes* a model version |
| **Q** | `gap` **(new)** — owns `ignorance-category`, `knowledge-goal`, `cues[]`, `provenance ∈ {explicit-cue, inferred-from-hinge, both}`; `hypothesis` | populated by the `analyze` arc |
| **E** | `kefed-model` **(new)** — `kefed-activity`, `kefed-object`, `kefed-variable{parameter|constant|measurement}`, branch/fork; EFO/OBI annotations | one model = template for many experiments |
| **D** | `observation` **(new)** — measurement value + parameter-context; `knowledge-level = observation` | the immutable anchor |

### 9.3 New relations

- `scilit-hinge` **(new)** — claim↔claim, owns `hinge-type` (Weak/CoCo*/P*); System 1 relational layer.
- `claim --addresses/raises--> gap` **(new)** — gap edge; target of negative hinges.
- `interpretation --depends-on--> domain-model-version` **(new)** — the correctability hook (re-run on model change).
- `observation --indexed-by--> kefed-parameter` — the workflow context link.
- evidence/observation enrichment **(new attributes on `scilit-evidence`):** `experiment-type` (OBI), `evidence-type` (ECO), `warrant ∈ {association, interaction, necessity, sufficiency, direct-mechanism, quantitative}`, `knowledge-level` (Biolink), `bio-scale ∈ {molecular, pathway, cellular, tissue, organism}`, `direction ∈ {supports, refutes, inconclusive}`.
- `evidence-line` **(new, SEPIO)** — aggregates N evidence/observations → one synthesized claim with combined belief; *the home for multi-experiment synthesis and predictive-model claims.*

**Open modeling fork:** is `interpretation` a *new* type, or just `scilit-claim` with a `depends-on → domain-model-version` edge? The latter is cheaper but conflates two of the three systems on one node.

---

## 10. Platform guarantees

- **Correctable.** Observations (D) are immutable anchors; interpretations, mechanistic models, KEfED templates, and gap assignments are versioned and revisable. Correction = re-run the `is explained by` arc against a new `domain-model-version`; the data beneath is untouched. (KEfED invariant.)
- **Extensible.** KEfED models are domain-agnostic templates; a new experimental subdiscipline = a new template + its EFO factor axes. The three systems extend independently (orthogonality).
- **LLM-serving.** The crisp graph selects a focused, relevant bundle of soft content per problem and per arc; the LLM produces/corrects crisp structure from soft content and vice versa. Reliability of automatic annotation must be checked against the human-validated agreement ceilings the source schemes report (Teufel and Boguslav both validated with trained annotators) before automatic labels are trusted for synthesis.

---

## 11. Testbed — the hallmarks of aging

The *hallmarks of aging* framework (López-Otín et al., 2023) is the canonical interpretive framework: 12 high-level claims, each a curated node in **K**. Its structure is a gift — **each hallmark's three defining premises are three different warrant levels**:

1. *age-associated manifestation* → **association** (observation);
2. *experimental accentuation accelerates aging* → **sufficiency** (gain-of-function);
3. *therapeutic attenuation decelerates aging* → **necessity / intervention** (loss-of-function).

So the framework already encodes the warrant table (§7). A "complete" hallmark = all three levels evidenced; a hallmark gap = a level missing — directly renderable as an **evidence-vs-gap surface** (an `alh-reporting-note`) showing both *textual* gaps (Boguslav cues) and *structural* gaps (unsampled KEfED parameter regions).

An existing deep-dive investigation over the hallmarks corpus is the starting point.

### First increment

1. Author 2–3 **KEfED templates** for canonical aging experiment types (loss-of-function + lifespan; gain-of-function + senescence marker; association/DEG), EFO-annotated.
2. Wire `observation → interpretation` for the hallmarks deep-dive, with **warrant derived from the template**.
3. Run the **`analyze` arc** (ignorance + negative-hinge gaps) over the corpus.
4. Render the per-hallmark **evidence-vs-gap surface**, structural + textual gaps side by side.

This exercises both crossing arcs (`design`, `explain`) and the enrichment primitive on the smallest end-to-end slice.

---

## 12. Open decisions

1. **KQED states as first-class entities** (`kqed-knowledge/-question/-experiment/-data` containers) vs. KQED as a pure process/skill layer with state carried implicitly by existing note/claim/KEfED types. (First is more legible; second avoids a parallel hierarchy.)
2. **`interpretation`** as a new type vs. `scilit-claim` + `depends-on` edge (§9.3).
3. **Scope of the first build:** the full four-arc platform, or the **`design` + `explain` crossing pair** first with `analyze`/`execute` as stubs.
4. **Where `analyze` reads from:** corpus-only (textual ignorance) vs. corpus + assembled KG (structural ignorance) from day one.

---

## 13. References

These are **stage-(1) anchors** (per the staged-adoption principle in §3), not mandated standards. Teufel, Boguslav, and KEfED supply the load-bearing *patterns*; the rest are reference points to start from and extend or replace per use case.

- Teufel, S. (2010). *The Structure of Scientific Articles: Applications to Citation Indexing and Summarization.* CSLI / Cambridge University Press. — AZ, CFC, KCA, KCDM.
- Boguslav, M.R., Salem, N.M., White, E.K., Sullivan, K.J., Bada, M., Hernandez, T.L., Leach, S.M., Hunter, L.E. (2023). *Creating an Ignorance-Base: Exploring Known Unknowns in the Scientific Literature.* J. Biomed. Inform. — 13 ignorance categories, knowledge goals, ignorance enrichment.
- Callahan, T.J., Stefanski, A.L., Kim, J-D., Baumgartner, W.A. Jr., Wyrwa, J.M., Hunter, L.E. *Knowledge-Driven Mechanistic Enrichment of the Preeclampsia Ignorome.* — the ignorome as a computable set operation + KG enrichment.
- Russ, T.A., Ramakrishnan, C., Hovy, E.H., Bota, M., Burns, G.A.P.C. (2011). *Knowledge engineering tools for reasoning with scientific observations and interpretations: a neural connectivity use case.* BMC Bioinformatics 12:351. — **KEfED**, BioScholar, the observation/interpretation distinction, workflow-indexed measurement context.
- Evidence & Conclusion Ontology — evidenceontology.org; GO evidence codes.
- SEPIO (Scientific Evidence and Provenance Information Ontology) — Monarch Initiative.
- Biolink Model — `knowledge_level`, `agent_type`, association/evidence.
- INDRA — Gyori, Bachman, Subramanian, Muhlich, Galescu, Sorger (2017, MSB 13:954); Bachman, Gyori, Sorger (2023, MSB e11325). Mechanistic statement assembly, belief scoring, executable models.
- OBI (Ontology for Biomedical Investigations); EFO (Experimental Factor Ontology); OBO Foundry; GO-CAM; BEL.
- López-Otín, C., Blasco, M.A., Partridge, L., Serrano, M., Kroemer, G. (2023). *Hallmarks of aging: an expanding universe.* Cell. — the testbed framework.
```
