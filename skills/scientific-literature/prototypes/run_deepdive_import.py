#!/usr/bin/env python3
"""Persist the WF2 deep-dive KQED records (from /tmp/hm_deepdive_records.json)."""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kqed as K
from import_deepdive import import_record

records = json.load(open("/tmp/hm_deepdive_records.json"))
d = K.get_driver()
try:
    for r in records:
        out = import_record(d, r["pid"], r["doi"], r["title"], r["record"])
        print(json.dumps(out))
finally:
    d.close()
