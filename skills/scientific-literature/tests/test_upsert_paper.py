import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import kqed as K
from paper_identity import paper_identity

def test_upsert_is_idempotent_and_deterministic():
    d = K.get_driver()
    try:
        meta = {"doi": "10.9999/itest.paper.identity", "name": "Test Paper", "pmid": "99999999"}
        expected_id, _, _ = paper_identity(meta)
        K.w(d, f'match $p isa scilit-paper, has id "{expected_id}"; delete $p;') if K._exists(d, expected_id) else None
        id1 = K.upsert_paper(d, meta)
        id2 = K.upsert_paper(d, meta)            # second call must not create a duplicate
        assert id1 == id2 == expected_id
        count = sum(1 for _ in K.r(d, f'match $p isa scilit-paper, has id "{expected_id}"; select $p;'))
        assert count == 1
        assert K._has(d, f'$p isa scilit-paper, has id "{expected_id}", has scilit-identity-basis "doi";')
    finally:
        K.w(d, f'match $p isa scilit-paper, has id "{expected_id}"; delete $p;')
        d.close()
