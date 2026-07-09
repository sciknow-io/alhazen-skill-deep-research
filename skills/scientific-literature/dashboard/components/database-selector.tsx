'use client';

import { useEffect, useState } from 'react';
import { T } from './tokens';
import { getDb, setDb } from './db';
import type { DatabaseInfo } from '@/lib/scientific-literature';

// Dropdown to pick which TypeDB database the scientific-literature dashboard reads.
// Only scilit-bearing databases are offered (different DBs carry different skills' data);
// changing it persists the choice and reloads so every view refetches from the new DB.
export function DatabaseSelector() {
  const [dbs, setDbs] = useState<string[]>([]);
  const [cur, setCur] = useState<string>('');

  useEffect(() => {
    setCur(getDb());
    fetch('/api/scientific-literature/databases')
      .then((r) => (r.ok ? r.json() : { databases: [] }))
      .then((j) => {
        const info: DatabaseInfo[] = j.info || [];
        // prefer the lookup: only databases that actually hold scilit data
        const scilit = info.filter((e) => e.hasScilit).map((e) => e.name);
        setDbs(scilit.length ? scilit : (j.databases || []));
      })
      .catch(() => { /* leave list empty; current db still shown */ });
  }, []);

  return (
    <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontFamily: T.mono, fontSize: 10.5, color: T.fgFaint, letterSpacing: '0.6px', textTransform: 'uppercase' }}>
      db
      <select
        value={cur}
        onChange={(e) => { setDb(e.target.value); window.location.reload(); }}
        style={{ background: T.bgSunken, color: T.teal, border: `1px solid ${T.borderHi}`, borderRadius: 3, padding: '4px 8px', fontFamily: T.mono, fontSize: 11 }}
      >
        {cur && !dbs.includes(cur) && <option value={cur}>{cur}</option>}
        {dbs.map((d) => <option key={d} value={d}>{d}</option>)}
      </select>
    </label>
  );
}
