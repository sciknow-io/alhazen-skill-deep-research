# Worked KQED Study — *SIRT3 Reverses Aging-Associated Degeneration*

**Paper:** Brown K, Xie S, Qiu X, Mohrin M, Shin J, Liu Y, Zhang D, Scadden DT, Chen D. *Cell Reports* 3:319–327 (2013). DOI `10.1016/j.celrep.2013.01.005`. Open access.
**Notebook id:** `scilit-paper-a5c569d48e76` · **Context:** Hallmarks-of-aging deep-dive (`scinv-3e0aa419866c`).
**Purpose of this doc:** a complete pass of the KQED architecture (`docs/architecture-kqed.md`) over one primary paper, populating all three representational systems and showing how the four arcs play out. Doubles as the concrete schema-instance prototype.

---

## 0. Why this paper is the ideal test case

It is, by itself, **one complete KQED cycle**: it opens by *analyzing* established knowledge into explicit questions (K→Q), *designs* experiments against them (Q→E), *executes* assays (E→D), and *explains* the data back into a mechanistic model (D→K) — and it ends by emitting the next question (the residual gap). It also exercises **all six warrant levels** and three of the four bio-scales, so the warrant table is fully demonstrated, with one scale (organismal) left explicitly open.

```
   K  established: sirtuins→lifespan; ROS↑ with age drives HSC aging; SIRT3→SOD2→ROS
   │  analyze
   ▼
   Q  "Can a sirtuin REVERSE (not just slow) aging degeneration?"
   │  "Is stem-cell aging a chronic cumulative effect or an ACUTE ROS effect — reversible?"
   │  design
   ▼
   E  LoF (KO) · GoF (lentiviral SIRT3) · antioxidant rescue (NAC) · epistasis (SOD2-K53/89R)
   │  execute
   ▼
   D  reconstitution %, HSC#, colony#, ROS (MFI), survival %, cycling, SOD2 activity ...
   │  is explained by
   ▼
   K' aging ⊣ SIRT3 → SOD2 ⊣ ROS ⊣ HSC-function → tissue regeneration; REVERSIBLE
   │  residual gap → new Q:
   ▼
   Q' "effect of SIRT3 on organismal lifespan" (explicitly future work)
```

---

## 1. System 1 — Rhetorical (claims, hinges, gaps)

### 1.1 Knowledge claims (interpretational assertions — all `New-KC`)

| id | type | claim | AZ |
|---|---|---|---|
| C1 | **primary** | SIRT3 **upregulation reverses** aging-associated functional degeneration of HSCs (rejuvenation). | AIM/OWN |
| C2 | primary | SIRT3 is **necessary** for HSC maintenance **under stress / old age**, but **dispensable in young** homeostatic conditions. | OWN |
| C3 | secondary | SIRT3 is **suppressed with age** (~70% mRNA ↓), contributing to elevated ROS in aged HSCs. | OWN |
| C4 | secondary | SIRT3 acts **cell-autonomously** (not via the niche). | OWN |
| C5 | secondary | Mechanism: SIRT3 → **SOD2 (deacetylation/activation)** → reduced ROS (the deacetyl-mimic SOD2-K53/89R bypasses SIRT3). | OWN |
| C6 | primary | Physiological stem-cell aging is (at least partly) an **acute, reversible ROS effect**, not solely chronic cumulative damage. | OWN |

### 1.2 Hinges (claim ↔ existing-KC relations — System-1 relational layer)

| hinge | type | target existing KC |
|---|---|---|
| sirtuins extend lifespan; SIRT6 OE ↑ lifespan | **PBas / PMot** (motivation) | Guarente 2007; Kanfi 2012 |
| SIRT3→SOD2 deacetylation mechanism | **PUse / PBas** (used as basis) | Qiu 2010; Tao 2010 |
| ROS↑ with age drives HSC aging via p38 | **PUse** | Ito 2006; Tothova 2007 |
| SLAM-marker HSC definition, serial-transplant ROS | **PUse** | Kiel 2005; Miyamoto 2007 |
| sirtuin lifespan role "controversial" in worms/flies | **Weak / CoCo-** (contrast) | Banerjee 2012; Burnett 2011 |
| reframes "passive mitochondrial damage accumulation" as **plastic/reversible** | **CoCoGM** (contrast in view) | Balaban 2005 |
| "sirtuins *slow* aging" → this shows a sirtuin can *reverse* it | **CoCo-** (superiority/extension) | Kanfi 2012 |

### 1.3 Gaps / statements of ignorance (Boguslav categories + entailed knowledge-goal)

| gap | ignorance category | knowledge-goal | provenance |
|---|---|---|---|
| "Whether sirtuins can **reverse** aging-associated degeneration is **unknown**." | unknown/novel | test reversal directly | explicit cue + AIM |
| "unclear whether sirtuins can **reverse, as opposed to simply slow**" | alternative/controversy | distinguish reverse vs slow | explicit cue |
| "How do ROS levels increase with age…? Is stem-cell aging **chronic** … or an **acute** effect…? Are [they] **reversible**?" | explicit research inquiry + alternative | resolve chronic-vs-acute; test reversibility | explicit `?` |
| "we **do not rule out** … chronic oxidative damage … contributes" | incompletely understood | quantify chronic vs acute contribution | hedge cue (limitation) |
| "We **speculate** that SIRT3 may regulate stem cells in **other tissues**." | future prediction / proposed | test other stem-cell compartments | speculation cue |
| **"Future studies will determine the effect of SIRT3 on lifespan."** | **future work** | run an organismal lifespan study | explicit future-work cue |

The last gap is the load-bearing one (see §4): the paper closes the cellular/tissue warrants but the **organismal-scale** warrant is left open.

---

## 2. System 2 — Epistemic (KEfED): experiments → observations → warrants

The paper instantiates **five KEfED templates**. Each template is a protocol workflow whose `Parameter`s (independent variables + context) index the `Measurement`s; the **warrant is derived from which parameter is manipulated and the measurement's context**.

### 2.1 The templates

| T | name | manipulated parameter (IV) | key context params | measurement(s) | derived warrant | ECO anchor |
|---|---|---|---|---|---|---|
| **T1** | expression profiling | — (observational) | cell-population, age | mRNA / protein level | **association** | IEP |
| **T2** | loss-of-function + phenotype | genotype {WT, **KO**} | age{young,old}, stress{homeo, transplant, serial-n, paraquat} | HSC#, reconstitution%, colony#, ROS, survival%, cycling, dead% | **necessity** | IMP |
| **T3** | gain-of-function rescue | SIRT3-level {control, **OE**} (lentiviral) | age{young,old} | ROS, colony#, reconstitution%, p19/BAX | **sufficiency** | (overexpression) |
| **T4** | pharmacological mediator test | treatment {none, **NAC**} | genotype{WT,KO}, age=old | reconstitution% | **causal-mediator (necessity of ROS)** | — |
| **T5** | epistasis / deacetyl-mimic | construct {ctrl, WT-SOD2, **SOD2-K53/89R**} | +paraquat, aged-KO background | survival%, colony# | **mechanism / epistasis** (places SOD2-deacetyl downstream of SIRT3) | IGI |

### 2.2 The experiment instances (E→D), with derived warrant & bio-scale

| fig | template | parameter-context | observation (D) | interpretation (K) | warrant | bio-scale |
|---|---|---|---|---|---|---|
| 1A–C | T1 | population × | SIRT3 ~3000× higher in HSC/MPP vs differentiated | SIRT3 enriched in HSCs | association | molecular |
| 1D–K | T2 | **young**, homeostatic | **no** difference (HSC#, reconstitution, lineages, colonies) | SIRT3 **dispensable young** | necessity (–) | cellular/tissue |
| 2A–G | T2 | **old**, homeostatic | KO: HSC pool −50%, reconstitution −30%, colonies −20% | SIRT3 **required at old age** | necessity (+) | tissue |
| 2H–K | T2 | young, **serial transplant (3°)** | KO: self-renewal/reconstitution −50% at 3° (null at 2°) | SIRT3 required **under serial stress** | necessity (+) | tissue |
| S1C–F | T2 | aged WT donor → **KO recipient** (niche) | comparable | SIRT3 **not** required in niche → **autonomous** | necessity (–), control | tissue |
| S1G | T3 | aged-KO + SIRT3-OE | colony **+25%** | SIRT3 rescues KO defect | sufficiency | tissue |
| 3A–D | T2 | old, transplant/paraquat | KO: ROS↑, survival −37%, dead×2, cycling +40% | SIRT3 reduces oxidative stress, promotes survival/quiescence | necessity → mechanism | molecular/cellular |
| **3E** | **T4** | aged-KO **+ NAC** | reconstitution **rescued** | **oxidative stress is the causal mediator** | causal-mediator | tissue |
| 3F–H | T2 | old | SOD2 activity −50% (mRNA =), dysfunctional mito +40% | SIRT3 acts via **SOD2 activity**, maintains mito integrity | mechanism | molecular |
| 3I–L | T1 | young vs **old** | SIRT3 mRNA −70%, SOD2 activity −30% with age | SIRT3 **suppressed with age** | association | molecular |
| 4A–B | T3 | aged + SIRT3-OE | ROS↓; p19/BAX↓ | SIRT3-OE reduces ROS & apoptotic markers | sufficiency / mechanism | molecular/cellular |
| 4C | T3 | aged + SIRT3-OE | colony **+40%** | functional rescue (in vitro) | sufficiency | tissue |
| **4D–F** | **T3** | aged + SIRT3-OE | reconstitution **5-fold↑** | **SIRT3-OE rejuvenates aged HSCs in vivo** (= **C1**) | **sufficiency** | tissue |
| S3C–D | T3 | **young** + SIRT3-OE | **no** effect | rescue is **specific to aged** | sufficiency (–), specificity | cellular |
| 4G–H | T5 | aged-KO + SOD2-K53/89R | survival +67%, colony +75% (WT-SOD2: none) | deacetyl-SOD2 **bypasses SIRT3** | epistasis | molecular/tissue |

**The KEfED payoff, concretely:** the *same* measurement — `reconstitution %` — appears at **null** (young, 1I) and **−30%** (old, 2E) and **+5-fold** (aged+OE, 4E). The observation values are stable; it is the **parameter context (age) + the manipulated variable (genotype/SIRT3-level)** that flips the interpretation and *sets the warrant*. Warrant is read off the design, not assigned by hand — exactly the architecture's claim.

---

## 3. System 3 — Mechanistic (the domain model the paper assembles)

Notebook-defined causal relations over domain entities (`alh-domain-thing`s). `→` = promotes/activates, `⊣` = inhibits/reduces.

```
aging ⊣ SIRT3                         (3I–L: age suppresses SIRT3)
SIRT3 → SOD2(activity)               (3F–G, 4G: deacetylation; K53/89R mimic)
SIRT3 → mitochondrial homeostasis    (3H: fewer dysfunctional mitochondria)
SOD2 ⊣ ROS                            (antioxidant)
SIRT3 ⊣ ROS                           (3A, 4A: net effect)
ROS → HSC dysfunction                 (3B–D: ↑cycling, ↑apoptosis[p19,BAX], ↓survival)
HSC dysfunction ⊣ tissue regeneration (2,4: reconstitution / colony capacity)
— reversal —
SIRT3(OE) → HSC function (aged only)  (4D–F: sufficiency)
SOD2-K53/89R → HSC function           (4G–H: downstream of SIRT3)
```

**Net model (Fig 4I):** `aging ⊣ SIRT3 → SOD2 ⊣ ROS ⊣ HSC-function → tissue-maintenance`, and the loop is **reversible** by restoring SIRT3 (or deacetyl-SOD2).

**Hallmark placement (System-3 ↔ K framework):** this paper supplies evidence at the intersection of **H6 deregulated nutrient-sensing** (sirtuin axis), **H7 mitochondrial dysfunction**, and **H9 stem-cell exhaustion** — a single mechanistic chain spanning three hallmarks.

---

## 4. The evidence-vs-gap surface (warrant × bio-scale)

The deliverable artifact (`alh-reporting-note`): does the paper complete the warrant table, and at what scale?

| warrant ↓ \ bio-scale → | molecular | cellular | tissue | **organism** |
|---|---|---|---|---|
| **association** (age-associated) | ✓ SIRT3↓, SOD2-act↓ (3I–L) | — | — | — |
| **necessity** (LoF) | ✓ SOD2-act, mito (3F–H) | ✓ survival/cycle (3B–D) | ✓ HSC pool/reconstitution old (Fig 2) | **✗ GAP** |
| **sufficiency** (GoF) | ✓ ROS↓ (4A) | ✓ (S3) | ✓ 5-fold reconstitution (4D–F) | **✗ GAP** |
| **causal-mediator** | ✓ NAC rescue (3E) | | ✓ | — |
| **epistasis** | ✓ SOD2-K53/89R (4G–H) | | ✓ | — |

**Reading:** the paper **fully completes** the three hallmark-premise warrants (association + necessity + sufficiency) at the **molecular→cellular→tissue** scales — a "complete hallmark" at the cellular level. The **single structural gap is the organismal (lifespan) row**, which the authors flag explicitly as future work. That gap *is* the next experiment, and its design is licensed by the warrant table: an **organism-scale LoF/GoF lifespan study** (e.g., HSC-specific SIRT3 modulation → survival curve).

---

## 5. As schema instances (the prototype shape)

What this study would write into the notebook (new types in **bold**, per `architecture-kqed.md §9`):

- **`scilit-hinge`** ×7 (claim↔existing-KC, §1.2)
- `scilit-claim` ×6 (§1.1) — each `aboutness`→ focal paper fragment
- **`gap`** ×6 (§1.3) — `ignorance-category` + `knowledge-goal`; the lifespan gap `provenance = explicit-cue`
- **`kefed-model`** ×5 (T1–T5) — workflow graphs; `kefed-variable` params EFO-annotated (genotype, age, stress, construct, treatment), measurements (reconstitution, ROS, colony…)
- **`observation`** ×~15 (§2.2 rows) — measurement value + parameter-context, `knowledge-level = observation`, `indexed-by → kefed-parameter`
- `scilit-evidence` enriched: `warrant`, `bio-scale`, `direction`, `experiment-type` (derived)
- **`domain-relation`** ×~9 (§3 causal edges) — notebook-defined; assembled by the `is explained by` arc; `interpretation --depends-on--> domain-model-version`
- 1 **`alh-reporting-note`** = the §4 evidence-vs-gap surface

**Open decisions this paper resolves in favor of a choice:**
- *interpretation node:* the SIRT3 claims are genuinely both System-1 claims and System-2 interpretations → favors `scilit-claim` **+ `depends-on → domain-model-version`** (one node, edge to model) over a separate type.
- *observation grain:* one measurement-in-context per figure panel works cleanly (each panel = one parameter-context cell).
- *kefed-model grain:* one template reused across many panels (T2 spans Figs 1,2,3) — confirms **template ≠ instance**; the panels are instances (observations) against a shared template.
- *warrant derivation:* mechanically derivable from {manipulated parameter, measurement context} — no hand-labeling needed.
```
