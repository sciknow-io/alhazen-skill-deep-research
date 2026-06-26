#!/usr/bin/env python3
"""
Seed the SIRT3 KQED prototype record into the live notebook.

Builds, under a new deep-dive investigation "Hallmarks of aging (KQED)" (focal =
the SIRT3 paper): 4 provenance-bearing vocabularies, 16 fragments, 5 KEfED models
+ variables, 8 observations, 6 claims, 6 gaps, 7 hinges, a System-3 mechanism, and
the alh-derivation grounding reference matrix. Deterministic ids -> idempotent.

Run: uv run python prototypes/seed_sirt3_kqed.py
Data: docs/example-kqed-sirt3.md + docs/example-fragments-sirt3.md
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kqed as K
from kqed import escape_string, get_timestamp

PAPER = "scilit-paper-a5c569d48e76"
ARTIFACT = "artifact-4a7d77f868de"
INV = "scinv-kqed-sirt3"


def ensure_investigation(d):
    if K._exists(d, INV):
        return INV
    ts = get_timestamp()
    K.w(d, f'insert $i isa scilit-investigation, has id "{INV}", '
          f'has name "Hallmarks of aging (KQED)", '
          f'has content "## KQED-method deep dive\\nProvenance-bearing three-system (rhetorical/epistemic-KEfED/mechanistic) record. First exemplar paper: SIRT3 reverses aging-associated degeneration.", '
          f'has scilit-investigation-status "analysis", has scilit-investigation-type "deep-dive", has created-at {ts};')
    K.w(d, f'match $i isa scilit-investigation, has id "{INV}"; $p isa scilit-paper, has id "{PAPER}"; '
          f'insert (note: $i, subject: $p) isa alh-aboutness;')
    return INV


# ---- fragments (id -> (type, verbatim anchor)) ----
FRAGS = {
 "F1": ("sentence", "Whether sirtuins can reverse aging-associated degeneration is unknown"),
 "F2": ("sentence", "SIRT3 is suppressed with aging, and SIRT3 upregulation in aged HSCs improves their regenerative capacity"),
 "F3": ("sentence", "it is unclear whether sirtuins can reverse, as opposed to simply slow"),
 "F4": ("sentence", "Is stem cell aging a chronic result of cumulative oxidative damage or an acute effect"),
 "F5": ("sentence", "SIRT3 mRNA levels were about 3,000-fold higher in HSCs and MPPs"),
 "F6": ("sentence", "no difference in the number of immunophenotypically defined enriched HSPCs or highly enriched HSCs"),
 "F7": ("sentence", "The size of both HSPC and HSC compartments was 50% smaller in aged"),
 "F8": ("sentence", "SIRT3 overexpression resulted in a 5-fold increase in functional reconstitution"),
 "F9": ("sentence", "NAC treatment rescued reconstitution"),
 "F10": ("sentence", "the enzymatic activity was 50% lower in SIRT3 KO HSPCs"),
 "F11": ("sentence", "SOD2 K53/89R improved the survival of HSCs by 67%, whereas WT SOD2 had no effect"),
 "F12": ("sentence", "SIRT3 mRNA levels were 70% lower in HSPCs of old mice"),
 "F13": ("sentence", "Future studies will determine the effect of SIRT3 on lifespan"),
 "F14": ("methods-step", "BM cells from WT or SIRT3 KO CD45.2 littermates was mixed with"),
 "F15": ("methods-step", "SIRT3, SOD2, and SOD2 K53/89R were cloned into pFUGW lentiviral construct"),
 "F16": ("sentence", "we do not rule out the possibility that chronic oxidative damage"),
}


def seed():
    d = K.get_driver()
    try:
        ensure_investigation(d)

        # ---- 0. VOCABULARIES (provenance-bearing libraries) ----
        v_war = K.add_vocab(d, "KEfED warrant levels", "alhazen/KQED architecture", vid="vocab-kefed-warrant")
        warrants = {}
        for nm in ["association", "interaction", "necessity", "sufficiency",
                   "causal-mediator", "epistasis", "direct-mechanism", "quantitative"]:
            warrants[nm] = K.add_vocab_term(d, v_war, nm, provenance="KQED warrant table (Toulmin warrant)",
                                            tid=f"warr-{nm}")

        v_exp = K.add_vocab(d, "KEfED experiment types", "OBI/BAO/EFO + curated",
                            iri="http://purl.obolibrary.org/obo/obi.owl", vid="vocab-kefed-exptype")
        # term -> (label, iri-or-None, provenance(s), licensed-warrant)
        EXPTYPES = {
          "expression-profiling": ("expression-profiling assay (qPCR/western)",
                "http://purl.obolibrary.org/obo/OBI_0000366",
                ["OBI:0000366 (molecular feature identification assay)", "EFO transcription profiling"], "association"),
          "loss-of-function": ("loss-of-function genetic perturbation (knockout)",
                "http://purl.obolibrary.org/obo/OBI_0000443",
                ["OBI gene knockout / analyte assay", "curated: LoF licenses necessity"], "necessity"),
          "gain-of-function": ("gain-of-function perturbation (lentiviral overexpression)",
                None, ["curated: GoF licenses sufficiency", "OBI transfection/transduction"], "sufficiency"),
          "pharmacological-mediator-test": ("pharmacological mediator (antioxidant) rescue",
                None, ["curated: intervention isolates the causal mediator (NAC)"], "causal-mediator"),
          "epistasis-bypass": ("epistasis / deacetyl-mimic bypass",
                None, ["curated: constitutively-active downstream node bypasses the upstream gene"], "epistasis"),
        }
        exp = {}
        for key, (label, iri, prov, war) in EXPTYPES.items():
            exp[key] = K.add_vocab_term(d, v_exp, label, iri=iri, provenance=prov,
                                        licenses=warrants[war], tid=f"exp-{key}")

        v_ign = K.add_vocab(d, "Boguslav ignorance taxonomy", "Boguslav et al. 2023", vid="vocab-ignorance")
        IGN = {
          "unknown-novel": "explore the unknown to gain insight",
          "alternative-controversy": "resolve disagreement; determine the correct option",
          "explicit-research-inquiry": "answer the explicit question",
          "incompletely-understood": "gather more evidence; complete the partial picture",
          "future-work": "determine the next course of action",
          "future-prediction": "run the experiment to test the prediction",
        }
        ign = {}
        for key, goal in IGN.items():
            ign[key] = K.add_vocab_term(d, v_ign, key, provenance="Boguslav et al. 2023, J Biomed Inform",
                                        tid=f"ign-{key}")

        v_cfc = K.add_vocab(d, "Teufel citation functions (CFC)", "Teufel 2010", vid="vocab-cfc")
        cfc = {}
        for nm in ["Weak", "CoCo-", "CoCoGM", "PUse", "PBas", "PSup", "PMot"]:
            cfc[nm] = K.add_vocab_term(d, v_cfc, nm, provenance="Teufel 2010, The Structure of Scientific Articles",
                                       tid=f"cfc-{nm.replace('-','minus')}")

        # ---- 2. FRAGMENTS ----
        fid = {}
        for key, (ft, text) in FRAGS.items():
            fid[key] = K.add_fragment(d, ARTIFACT, ft, text, fid=f"kqed-frag-{key}")

        # ---- 3a. KEfED models (template -> experiment-type), grounded to methods fragments ----
        T1 = K.add_kefed_model(d, "Expression profiling (SIRT3/SOD2 by qPCR/western)", exp["expression-profiling"],
              "Sort BM subpopulations by surface markers; quantify transcript/protein by real-time PCR / western blot.",
              variables=[("parameter", "cell-population", "HSC|MPP|HSPC|MP|CLP|diff", "EFO:cell type"),
                         ("parameter", "age", "young|old", "EFO:age"),
                         ("measurement", "expression-level", "mRNA/protein", "")], mid="kqed-kefed-T1")
        T2 = K.add_kefed_model(d, "Loss-of-function + HSC phenotype (WT vs SIRT3-KO)", exp["loss-of-function"],
              "Compare WT vs SIRT3-KO; competitive transplantation into lethally irradiated recipients / colony-forming assay; readouts by flow cytometry.",
              variables=[("parameter", "genotype", "WT|KO", "EFO:genotype"),
                         ("parameter", "age", "young|old", "EFO:age"),
                         ("parameter", "stress", "homeostatic|transplant|serial|paraquat", "EFO:stress"),
                         ("constant", "competitor-ratio", "1:1 CD45.1", ""),
                         ("measurement", "reconstitution-or-HSC-readout", "%/count", "")], mid="kqed-kefed-T2")
        K.ground_note(d, T2, [fid["F14"]])
        T3 = K.add_kefed_model(d, "Gain-of-function rescue (lentiviral SIRT3 in aged HSC)", exp["gain-of-function"],
              "Lentiviral SIRT3 (vs control) into lineage-depleted aged cells; ROS, colony-forming and competitive transplantation readouts.",
              variables=[("parameter", "SIRT3-level", "control|overexpressed", "EFO:genetic modification"),
                         ("parameter", "age", "young|old", "EFO:age"),
                         ("measurement", "rescue-readout", "ROS/colony/reconstitution", "")], mid="kqed-kefed-T3")
        K.ground_note(d, T3, [fid["F15"]])
        T4 = K.add_kefed_model(d, "Antioxidant mediator test (NAC rescue)", exp["pharmacological-mediator-test"],
              "Competitive transplant of aged WT/KO cells; recipients +/- daily NAC; reconstitution readout.",
              variables=[("parameter", "treatment", "none|NAC", "EFO:compound"),
                         ("parameter", "genotype", "WT|KO", "EFO:genotype"),
                         ("measurement", "reconstitution", "%", "")], mid="kqed-kefed-T4")
        T5 = K.add_kefed_model(d, "Epistasis: deacetyl-mimic SOD2-K53/89R", exp["epistasis-bypass"],
              "Express control / WT-SOD2 / SOD2-K53/89R in aged-KO cells; +paraquat; survival and colony readouts.",
              variables=[("parameter", "construct", "ctrl|WT-SOD2|SOD2-K53/89R", "EFO:genetic modification"),
                         ("constant", "stressor", "paraquat", "EFO:compound"),
                         ("measurement", "survival-colony", "%", "")], mid="kqed-kefed-T5")
        K.ground_note(d, T5, [fid["F15"]])

        # ---- 3b. Observations (obs -> kefed-model; grounded to result fragment) ----
        OBS = [
          ("O1AC", T1, "SIRT3 ~3000x enriched in HSCs/MPPs vs differentiated blood cells", "association", "molecular", "F5"),
          ("O1DK", T2, "No HSC pool / reconstitution / colony difference in young WT vs KO", "assertion", "tissue", "F6"),
          ("O2AG", T2, "Aged KO: HSC pool -50%, reconstitution -30%, colonies -20%", "assertion", "tissue", "F7"),
          ("O3E",  T4, "NAC rescues reconstitution of aged SIRT3-KO HSCs", "assertion", "tissue", "F9"),
          ("O3G",  T2, "SOD2 enzymatic activity 50% lower in SIRT3-KO HSPCs (mRNA unchanged)", "assertion", "molecular", "F10"),
          ("O3IJ", T1, "SIRT3 mRNA 70% lower in HSPCs of old vs young mice", "association", "molecular", "F12"),
          ("O4DF", T3, "SIRT3 overexpression: 5-fold increase in functional reconstitution of aged HSCs", "assertion", "tissue", "F8"),
          ("O4G",  T5, "SOD2-K53/89R improves aged-KO HSC survival +67%; WT-SOD2 no effect", "assertion", "molecular", "F11"),
        ]
        obs = {}
        for oid, model, stmt, kl, scale, frag in OBS:
            obs[oid] = K.add_observation(d, INV, model, stmt, kl, scale, about=PAPER, oid=f"kqed-obs-{oid}")
            K.ground_note(d, obs[oid], [fid[frag]])

        # ---- 4a. Claims (grounded to fragments per reference matrix) ----
        def claim(cid, ctype, stmt, frags):
            if not K._exists(d, cid):
                ts = get_timestamp()
                K.w(d, f'match $inv isa scilit-investigation, has id "{INV}"; '
                      f'insert $c isa scilit-claim, has id "{cid}", has name "{escape_string(stmt[:60])}", '
                      f'has scilit-claim-type "{ctype}", has scilit-claim-statement "{escape_string(stmt)}", has created-at {ts}; '
                      f'(parent-note: $inv, child-note: $c) isa alh-note-threading;')
                K.w(d, f'match $c isa scilit-claim, has id "{cid}"; $p isa scilit-paper, has id "{PAPER}"; '
                      f'insert (note: $c, subject: $p) isa alh-aboutness;')
            K.ground_note(d, cid, [fid[f] for f in frags])
            return cid
        C1 = claim("kqed-claim-C1", "primary", "SIRT3 upregulation reverses aging-associated functional degeneration of HSCs", ["F1", "F2", "F8"])
        C2 = claim("kqed-claim-C2", "primary", "SIRT3 is necessary for HSC maintenance under stress/old age but dispensable in young", ["F6", "F7"])
        C3 = claim("kqed-claim-C3", "secondary", "SIRT3 is suppressed with age, contributing to elevated ROS in aged HSCs", ["F2", "F12"])
        C4 = claim("kqed-claim-C4", "secondary", "SIRT3 acts cell-autonomously (not via the niche)", [])
        C5 = claim("kqed-claim-C5", "secondary", "Mechanism: SIRT3 deacetylates/activates SOD2 to reduce ROS (SOD2-K53/89R bypasses SIRT3)", ["F10", "F11"])
        C6 = claim("kqed-claim-C6", "primary", "Physiological stem-cell aging is an acute, reversible ROS effect (not solely chronic damage)", ["F4", "F9", "F16"])

        # ---- 4b. Gaps (Boguslav category via classify; grounded) ----
        def gap(gid, cat, goal, prov, stmt, frag):
            K.add_gap(d, INV, ign[cat], goal, prov, stmt, gid=gid)
            if frag:
                K.ground_note(d, gid, [fid[frag]])
            return gid
        G1 = gap("kqed-gap-G1", "unknown-novel", "test reversal directly", "explicit-cue", "Whether sirtuins can reverse aging degeneration is unknown", "F1")
        G2 = gap("kqed-gap-G2", "alternative-controversy", "distinguish reverse vs slow", "explicit-cue", "Unclear whether sirtuins reverse vs simply slow", "F3")
        G3 = gap("kqed-gap-G3", "explicit-research-inquiry", "resolve chronic-vs-acute; test reversibility", "explicit-cue", "Is stem-cell aging chronic-cumulative or acute-reversible?", "F4")
        G4 = gap("kqed-gap-G4", "incompletely-understood", "quantify chronic vs acute contribution", "explicit-cue", "Chronic oxidative damage contribution not ruled out", "F16")
        G5 = gap("kqed-gap-G5", "future-prediction", "test other stem-cell compartments", "explicit-cue", "SIRT3 may regulate stem cells in other tissues (speculation)", None)
        G6 = gap("kqed-gap-G6", "future-work", "run an organismal lifespan study", "explicit-cue", "Effect of SIRT3 on organismal lifespan unknown", "F13")

        # ---- 4c. addresses edges (claim/obs -> gap) ----
        for note, g in [(C1, G1), (C1, G2), (C6, G3), (C6, G4), (C1, G6)]:
            K.add_addresses(d, note, g)

        # ---- 4d. hinges (claim -> existing KC stub paper; CFC term) ----
        stubs = {nm: K.find_or_make_stub_paper(d, nm)
                 for nm in ["Guarente 2007 (sirtuins extend lifespan)",
                                         "Kanfi 2012 (SIRT6 OE extends lifespan)",
                                         "Qiu 2010 (SIRT3-SOD2 deacetylation)",
                                         "Ito 2006 (ROS limits HSC lifespan)",
                                         "Banerjee 2012 (sirtuin lifespan controversy)",
                                         "Balaban 2005 (passive mitochondrial damage view)",
                                         "Kiel 2005 (SLAM HSC markers)"]}
        HINGES = [(C1, "Guarente 2007 (sirtuins extend lifespan)", "PMot"),
                  (C1, "Kanfi 2012 (SIRT6 OE extends lifespan)", "CoCo-"),
                  (C5, "Qiu 2010 (SIRT3-SOD2 deacetylation)", "PUse"),
                  (C2, "Ito 2006 (ROS limits HSC lifespan)", "PUse"),
                  (C1, "Banerjee 2012 (sirtuin lifespan controversy)", "Weak"),
                  (C6, "Balaban 2005 (passive mitochondrial damage view)", "CoCoGM"),
                  (C2, "Kiel 2005 (SLAM HSC markers)", "PUse")]
        for cl, tgt, fn in HINGES:
            K.add_hinge(d, cl, stubs[tgt], cfc[fn])

        # ---- 5. System-3 mechanism ----
        be = {nm: K.add_bioentity(d, nm, bid=f"kqed-bio-{i}")
              for i, nm in enumerate(["aging", "SIRT3", "SOD2", "ROS", "mitochondria", "HSC function", "tissue regeneration"])}
        MECH = [("aging", "suppresses", "SIRT3"), ("SIRT3", "activates", "SOD2"),
                ("SIRT3", "maintains", "mitochondria"), ("SOD2", "inhibits", "ROS"),
                ("SIRT3", "inhibits", "ROS"), ("ROS", "inhibits", "HSC function"),
                ("HSC function", "activates", "tissue regeneration"), ("SIRT3", "activates", "HSC function")]
        # idempotency for mech links: only add if none exist yet for this investigation seed
        existing = K.r(d, 'match (mech-source: $s, mech-target: $t) isa scilit-mechanistic-link; fetch {"x": $s.id};')
        if not existing:
            for s, mt, t in MECH:
                K.add_mech_link(d, be[s], mt, be[t], confidence=0.85)

        print("SEED COMPLETE")
        print(f"  investigation: {INV}")
        print(f"  fragments located: " +
              str(len(K.r(d, 'match $f isa alh-fragment, has id $i; $i like "kqed-frag-.*"; '
                             '$f has offset $o; $o >= 0; fetch {"i":$i};'))) + "/16")
    finally:
        d.close()


if __name__ == "__main__":
    seed()
