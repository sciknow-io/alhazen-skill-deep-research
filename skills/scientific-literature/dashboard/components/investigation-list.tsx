'use client';

import { useState, useEffect, useMemo } from 'react';
import Link from 'next/link';
import { T } from './tokens';
import { Icon, TypeChip } from './atoms';
import { withDb, syncDbFromUrl } from './db';
import { DatabaseSelector } from './database-selector';
import type { InvestigationSummary } from '@/lib/scientific-literature';

// Top level of the scientific-literature dashboard: a searchable list of investigations.
export function InvestigationList() {
  const [investigations, setInvestigations] = useState<InvestigationSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');

  useEffect(() => {
    syncDbFromUrl();
    fetch(withDb('/api/scientific-literature/investigations'))
      .then((r) => (r.ok ? r.json() : Promise.reject(`API ${r.status}`)))
      .then((json) => setInvestigations(json.investigations || []))
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return investigations;
    return investigations.filter((inv) => (inv.name || inv.id).toLowerCase().includes(s));
  }, [q, investigations]);

  return (
    <div style={{ minHeight: '100vh', background: T.bg, color: T.fg, fontFamily: T.sans, display: 'flex', flexDirection: 'column' }}>
      <header style={{ borderBottom: `1px solid ${T.borderDim}`, background: T.bgRaised, padding: '20px 24px' }}>
        <div style={{ maxWidth: 1100, margin: '0 auto', display: 'flex', alignItems: 'center', gap: 24 }}>
          <Link href="/" style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontFamily: T.mono, fontSize: 12, color: T.teal, textDecoration: 'none' }}>
            <Icon name="arrow-left" size={14} color={T.teal} /> Hub
          </Link>
          <div style={{ flex: 1 }}>
            <h1 style={{ margin: 0, fontFamily: T.serif, fontSize: 26, fontWeight: 400, color: T.fg, letterSpacing: '-0.4px' }}>Scientific Literature</h1>
            <span style={{ fontFamily: T.mono, fontSize: 11, color: T.fgDim }}>{investigations.length} investigations · discovery → ingestion → sensemaking → analysis → report</span>
          </div>
          <DatabaseSelector />
          <Link href="/scientific-literature/ontology" style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontFamily: T.mono, fontSize: 12, color: T.olive, textDecoration: 'none', border: `1px solid ${T.borderHi}`, borderRadius: 3, padding: '6px 12px' }}>
            <Icon name="search" size={14} color={T.olive} /> methods &amp; ontology
          </Link>
        </div>
      </header>

      <main style={{ maxWidth: 1100, margin: '0 auto', padding: '24px', width: '100%', flex: 1, display: 'flex', flexDirection: 'column', gap: 18 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: T.panel, border: `1px solid ${T.border}`, borderRadius: 4, padding: '8px 12px' }}>
          <Icon name="search" size={15} color={T.fgFaint} />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search investigations by name…"
            style={{ flex: 1, background: 'transparent', border: 'none', outline: 'none', color: T.fg, fontFamily: T.sans, fontSize: 14 }}
          />
          {q && <span style={{ fontFamily: T.mono, fontSize: 10.5, color: T.fgFaint }}>{filtered.length}/{investigations.length}</span>}
        </div>

        {loading && <span style={{ fontFamily: T.mono, fontSize: 11, color: T.fgFaint }}>Loading…</span>}
        {error && (
          <div style={{ background: 'rgba(200,80,80,0.1)', color: '#e05555', padding: '12px 16px', borderRadius: 4, border: '1px solid rgba(200,80,80,0.2)' }}>{error}</div>
        )}

        <section style={{ background: T.panel, border: `1px solid ${T.borderDim}`, borderRadius: 4 }}>
          {filtered.map((inv) => (
            <Link
              key={inv.id}
              href={`/scientific-literature/investigation/${inv.id}`}
              style={{ display: 'grid', gridTemplateColumns: '110px 1fr auto', gap: 14, alignItems: 'center', padding: '11px 16px', borderTop: `1px solid ${T.borderDim}`, textDecoration: 'none', color: 'inherit' }}
              onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(200,122,74,0.06)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
            >
              <TypeChip short={inv.type === 'deep-dive' ? 'DEEP DIVE' : 'INQUIRY'} color={T.rust} icon="search" />
              <div style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
                <span style={{ fontSize: 14, color: T.fg, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{inv.name || inv.id}</span>
                <span style={{ fontFamily: T.mono, fontSize: 10.5, color: T.fgFaint }}>
                  {inv.focal_paper?.name ? `${inv.focal_paper.name} · ` : inv.corpus?.name ? `${inv.corpus.name} · ` : ''}
                  {inv.iteration_count ?? 0} iteration{(inv.iteration_count ?? 0) === 1 ? '' : 's'}
                </span>
              </div>
              {inv.status && (
                <span style={{ fontFamily: T.mono, fontSize: 10, color: T.rust, border: `1px solid ${T.rustDim}`, borderRadius: 3, padding: '2px 7px' }}>{inv.status}</span>
              )}
            </Link>
          ))}
          {!loading && filtered.length === 0 && (
            <div style={{ padding: '16px', fontFamily: T.mono, fontSize: 11, color: T.fgFaint }}>No investigations{q ? ' match' : ' yet'}.</div>
          )}
        </section>
      </main>
    </div>
  );
}
