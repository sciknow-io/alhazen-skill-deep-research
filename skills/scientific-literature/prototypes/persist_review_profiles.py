#!/usr/bin/env python3
"""
Persist the WF3 rhetorical profiles of held review papers.
Per review: a rhetorical investigation + a rhetorical-profile note (CFC
distribution + characterization + representative classified claims), and
set the paper's acquisition-status -> "rhetorical-done".

Input: /tmp/hm_review_profiles.json  (list of {pid, doi, title, profile})
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kqed as K
from kqed import escape_string, get_timestamp


def _set_status(d, pid, value):
    if K._has(d, f'$p isa scilit-paper, has id "{pid}", has scilit-acquisition-status $v;'):
        K.w(d, f'match $p isa scilit-paper, has id "{pid}", has scilit-acquisition-status $v; delete has $v of $p;')
    K.w(d, f'match $p isa scilit-paper, has id "{pid}"; insert $p has scilit-acquisition-status "{escape_string(value)}";')


def main():
    reviews = json.load(open("/tmp/hm_review_profiles.json"))
    d = K.get_driver()
    try:
        for r in reviews:
            pid = r["pid"]; pid12 = pid.split("-")[-1]
            prof = r["profile"]
            inv = f"scinv-rhet-{pid12}"
            if not K._exists(d, inv):
                ts = get_timestamp()
                K.w(d, f'insert $i isa scilit-investigation, has id "{inv}", '
                       f'has name "{escape_string("Rhetorical profile (CFC): " + r["title"][:80])}", '
                       f'has scilit-investigation-status "analysis", has scilit-investigation-type "inquiry", '
                       f'has created-at {ts};')
                K.w(d, f'match $i isa scilit-investigation, has id "{inv}"; $p isa scilit-paper, has id "{pid}"; '
                       f'insert (note: $i, subject: $p) isa alh-aboutness;')
            dist = prof.get("cfc_distribution", {})
            dist_str = ", ".join(f"{k}:{v}" for k, v in dist.items() if v)
            sampled = prof.get("claims", [])
            # render the representative classified claims as markdown
            body = [prof.get("profile", "").strip(),
                    "",
                    f"Estimated total citing claims: {prof.get('estimated_total_citing_claims','?')}",
                    f"CFC distribution: {dist_str}",
                    "",
                    "Representative citing claims:"]
            for c in sampled:
                body.append(f"- [{c.get('cfc','?')}] {c.get('statement','').strip()}")
            statement = "\n".join(body)
            nid = f"scclaim-rhet-{pid12}-profile"
            if not K._exists(d, nid):
                ts = get_timestamp()
                K.w(d, f'match $inv isa scilit-investigation, has id "{inv}"; '
                       f'insert $c isa scilit-claim, has id "{nid}", '
                       f'has name "{escape_string("Rhetorical profile: " + r["title"][:50])}", '
                       f'has scilit-claim-type "rhetorical-profile", '
                       f'has scilit-claim-statement "{escape_string(statement)}", has created-at {ts}; '
                       f'(parent-note: $inv, child-note: $c) isa alh-note-threading;')
                K.w(d, f'match $c isa scilit-claim, has id "{nid}"; $p isa scilit-paper, has id "{pid}"; '
                       f'insert (note: $c, subject: $p) isa alh-aboutness;')
            _set_status(d, pid, "rhetorical-done")
            print(json.dumps({"review": pid, "investigation": inv,
                              "sampled_claims": len(sampled), "distribution": dist_str}))
    finally:
        d.close()


if __name__ == "__main__":
    main()
