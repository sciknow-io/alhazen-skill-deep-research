#!/usr/bin/env python3
"""
Worked example: map a REVIEW's citing-claim to the ORIGIN claim in the cited
primary paper, using the KQED hinge machinery.

Source review : Lopez-Otin et al., "Hallmarks of aging: an expanding universe",
                Cell 2023  (scilit-paper-21632e9ffb04), investigation scinv-3e0aa419866c.
Citing claim  : reference 123 sentence about SIRT3 / aged HSCs (Teufel CFC = PUse).
Cited paper   : Brown et al., SIRT3 Reverses Aging-Associated Degeneration,
                Cell Reports 2013 (scilit-paper-a5c569d48e76).
Origin claim  : kqed-claim-C1 (already sensemade under scinv-kqed-sirt3).

Builds, idempotently:
  review-claim --grounded-in--> review citation-sentence fragment
  review-claim --hinge[PUse]--> SIRT3 paper        (paper-level citation edge)
  review-claim --hinge[PUse]--> kqed-claim-C1       (claim-level origin mapping)

Run:  uv run python prototypes/seed_review_hinge.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kqed as K
from kqed import escape_string, get_timestamp

REVIEW_PAPER = "scilit-paper-21632e9ffb04"
REVIEW_INV   = "scinv-3e0aa419866c"
SIRT3_PAPER  = "scilit-paper-a5c569d48e76"
ORIGIN_CLAIM = "kqed-claim-C1"

ART          = "artifact-hmreview-text"
ART_CP       = "extracted/hallmarks_review.md"   # resolves under ~/.alhazen/cache
REVIEW_CLAIM = "scilit-claim-hm-ref123"
FRAG         = "frag-hm-ref123"
CFC          = "PUse"   # uses the cited finding as established support

CITATION_SENTENCE = (
    "Overexpression of mitochondrial SIRT3 reverses the regenerative capacity "
    "lost in aged hematopoietic stem cells (HSCs) and can mediate the beneficial "
    "effects of dietary restriction in longevity."
)


def ensure_text_artifact(d):
    """Register a text artifact over the extracted review markdown so the citing
    sentence can be located with byte offsets (the paper's other artifact is the
    raw PDF, which does not whitespace-match)."""
    if not K._exists(d, ART):
        ts = get_timestamp()
        K.w(d, f'insert $a isa alh-artifact, has id "{ART}", '
               f'has name "Hallmarks of aging: an expanding universe [extracted text]", '
               f'has cache-path "{ART_CP}", has format "pdf-extracted-text", has created-at {ts};')
    if not K._has(d, f'$a isa alh-artifact, has id "{ART}"; $p isa scilit-paper, has id "{REVIEW_PAPER}"; '
                     f'(alh-artifact: $a, referent: $p) isa alh-representation;'):
        K.w(d, f'match $a isa alh-artifact, has id "{ART}"; $p isa scilit-paper, has id "{REVIEW_PAPER}"; '
               f'insert (alh-artifact: $a, referent: $p) isa alh-representation;')


def ensure_review_claim(d):
    """The citing-claim as it appears in the review (System 1 rhetorical node)."""
    if not K._exists(d, REVIEW_CLAIM):
        ts = get_timestamp()
        K.w(d, f'match $inv isa scilit-investigation, has id "{REVIEW_INV}"; '
               f'insert $c isa scilit-claim, has id "{REVIEW_CLAIM}", '
               f'has name "{escape_string(CITATION_SENTENCE[:60])}", '
               f'has scilit-claim-type "citing", '
               f'has scilit-claim-statement "{escape_string(CITATION_SENTENCE)}", has created-at {ts}; '
               f'(parent-note: $inv, child-note: $c) isa alh-note-threading;')
        # aboutness: this claim is stated *in* the review paper
        K.w(d, f'match $c isa scilit-claim, has id "{REVIEW_CLAIM}"; $p isa scilit-paper, has id "{REVIEW_PAPER}"; '
               f'insert (note: $c, subject: $p) isa alh-aboutness;')


def main():
    d = K.get_driver()
    try:
        ensure_text_artifact(d)
        ensure_review_claim(d)

        # ground the citing-claim in its verbatim citation sentence
        frag = K.add_fragment(d, ART, "sentence", CITATION_SENTENCE, fid=FRAG)
        K.ground_note(d, REVIEW_CLAIM, [frag])

        # the two hinges: paper-level citation, then claim-level origin mapping
        K.add_hinge(d, REVIEW_CLAIM, SIRT3_PAPER, CFC)    # -> scilit-paper
        K.add_hinge(d, REVIEW_CLAIM, ORIGIN_CLAIM, CFC)   # -> scilit-claim (origin)

        # ---- verification ----------------------------------------------------
        off = K.r(d, f'match $f isa alh-fragment, has id "{FRAG}", has offset $o, has length $l; '
                     f'fetch {{"offset": $o, "length": $l}};')
        print(f"review-claim : {REVIEW_CLAIM}")
        print(f"fragment     : {FRAG}  {off[0] if off else '(no offset)'}")

        hinges = K.r(d, f'match $c isa scilit-claim, has id "{REVIEW_CLAIM}"; '
                        f'$h isa scilit-hinge, links (hinging-claim: $c, hinged-to: $t), has scilit-hinge-term-id $cfc; '
                        f'$t has id $tid; fetch {{"cfc": $cfc, "target": $tid}};')
        print("hinges from review-claim:")
        for h in hinges:
            print(f"   [{h['cfc']}] -> {h['target']}")

        # round-trip: from review-claim, hop the claim-level hinge to the origin
        # claim, then show the origin claim's grounding fragments (its warrant base)
        rt = K.r(d, f'match $c isa scilit-claim, has id "{REVIEW_CLAIM}"; '
                    f'$h isa scilit-hinge, links (hinging-claim: $c, hinged-to: $o); '
                    f'$o isa scilit-claim, has id "{ORIGIN_CLAIM}", has scilit-claim-statement $s; '
                    f'fetch {{"origin": $s}};')
        if rt:
            print(f"round-trip   : ref-123 --PUse--> {ORIGIN_CLAIM}")
            print(f"   origin claim: {rt[0]['origin']}")
    finally:
        d.close()


if __name__ == "__main__":
    main()
