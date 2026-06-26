'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { T } from '@/components/scientific-literature/tokens';
import { Icon, BackNav, TypeChip } from '@/components/scientific-literature/atoms';
import type { Corpus, FacetingNoteSummary, InvestigationSummary } from '@/lib/scientific-literature';

export default function ScientificLiteraturePage() {
  const [corpora, setCorpora] = useState<Corpus[]>([]);
  const [notes, setNotes] = useState<FacetingNoteSummary[]>([]);
  const [investigations, setInvestigations] = useState<InvestigationSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch('/api/scientific-literature/corpora').then((r) => (r.ok ? r.json() : Promise.reject(`corpora ${r.status}`))),
      fetch('/api/scientific-literature/faceting-notes').then((r) => (r.ok ? r.json() : { notes: [] })),
      fetch('/api/scientific-literature/investigations').then((r) => (r.ok ? r.json() : { investigations: [] })),
    ])
      .then(([cor, fn, inv]) => {
        setCorpora(cor.collections || []);
        setNotes(fn.notes || []);
        setInvestigations(inv.investigations || []);
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div style={{ minHeight: '100vh', background: T.bg, color: T.fg, fontFamily: T.sans, display: 'flex', flexDirection: 'column' }}>
      <header style={{ borderBottom: `1px solid ${T.borderDim}`, background: T.bgRaised, padding: '20px 24px' }}>
        <div style={{ maxWidth: 1100, margin: '0 auto', display: 'flex', alignItems: 'center', gap: 24 }}>
          <BackNav href="/" label="Hub" />
          <div style={{ flex: 1 }}>
            <h1 style={{ margin: 0, fontFamily: T.serif, fontSize: 26, fontWeight: 400, color: T.fg, letterSpacing: '-0.4px' }}>Scientific Literature</h1>
            <span style={{ fontFamily: T.mono, fontSize: 11, color: T.fgDim }}>
              {corpora.length} corpora · paper embeddings · faceting pipelines
            </span>
          </div>
          <Link
            href="/scientific-literature/map"
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              fontFamily: T.mono, fontSize: 12, color: T.teal, textDecoration: 'none',
              border: `1px solid ${T.borderHi}`, borderRadius: 3, padding: '6px 12px',
            }}
          >
            <Icon name="map" size={14} color={T.teal} /> embedding map
          </Link>
        </div>
      </header>

      <main style={{ maxWidth: 1100, margin: '0 auto', padding: '24px', width: '100%', flex: 1, display: 'flex', flexDirection: 'column', gap: 24 }}>
        {loading && <span style={{ fontFamily: T.mono, fontSize: 11, color: T.fgFaint }}>Loading…</span>}
        {error && (
          <div style={{ background: 'rgba(200,80,80,0.1)', color: '#e05555', padding: '12px 16px', borderRadius: 4, border: '1px solid rgba(200,80,80,0.2)' }}>
            <strong style={{ fontFamily: T.mono, fontSize: 10.5, letterSpacing: '0.8px', textTransform: 'uppercase' }}>Error</strong>
            <p style={{ fontSize: 13, marginTop: 4, marginBottom: 0 }}>{error}</p>
          </div>
        )}

        {/* Corpora */}
        <section style={{ background: T.panel, border: `1px solid ${T.borderDim}`, borderRadius: 4 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, padding: '14px 16px 8px' }}>
            <h3 style={{ margin: 0, fontFamily: T.mono, fontSize: 10.5, fontWeight: 600, letterSpacing: '1.4px', textTransform: 'uppercase', color: T.fg }}>Corpora</h3>
            <span style={{ fontFamily: T.mono, fontSize: 10.5, color: T.fgFaint }}>{corpora.length}</span>
          </div>
          <div>
            {corpora.map((c) => (
              <Link
                key={c.id}
                href={`/scientific-literature/corpus/${c.id}`}
                style={{
                  display: 'grid', gridTemplateColumns: '70px 1fr', gap: 14, alignItems: 'center',
                  padding: '10px 16px', borderTop: `1px solid ${T.borderDim}`, textDecoration: 'none', color: 'inherit',
                }}
                onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(90,173,175,0.06)'; }}
                onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
              >
                <TypeChip short="CORPUS" color={T.teal} icon="folder" />
                <div style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
                  <span style={{ fontSize: 13.5, color: T.fg, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.name}</span>
                  {c.description && <span style={{ fontFamily: T.mono, fontSize: 10.5, color: T.fgFaint, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.description}</span>}
                </div>
              </Link>
            ))}
            {!loading && corpora.length === 0 && (
              <div style={{ padding: '16px', fontFamily: T.mono, fontSize: 11, color: T.fgFaint }}>No corpora yet.</div>
            )}
          </div>
        </section>

        {/* Investigations */}
        {investigations.length > 0 && (
          <section style={{ background: T.panel, border: `1px solid ${T.borderDim}`, borderRadius: 4 }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, padding: '14px 16px 8px' }}>
              <h3 style={{ margin: 0, fontFamily: T.mono, fontSize: 10.5, fontWeight: 600, letterSpacing: '1.4px', textTransform: 'uppercase', color: T.fg }}>Investigations</h3>
              <span style={{ fontFamily: T.mono, fontSize: 10.5, color: T.fgFaint }}>{investigations.length}</span>
            </div>
            <div>
              {investigations.map((inv) => (
                <Link
                  key={inv.id}
                  href={`/scientific-literature/investigation/${inv.id}`}
                  style={{
                    display: 'grid', gridTemplateColumns: '110px 1fr auto', gap: 14, alignItems: 'center',
                    padding: '10px 16px', borderTop: `1px solid ${T.borderDim}`, textDecoration: 'none', color: 'inherit',
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(200,122,74,0.06)'; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
                >
                  <TypeChip
                    short={inv.type === 'deep-dive' ? 'DEEP DIVE' : 'INQUIRY'}
                    color={T.rust}
                    icon="search"
                  />
                  <div style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
                    <span style={{ fontSize: 13.5, color: T.fg, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{inv.name || inv.id}</span>
                    <span style={{ fontFamily: T.mono, fontSize: 10.5, color: T.fgFaint, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {inv.type === 'deep-dive'
                        ? `${inv.focal_paper?.name ? `${inv.focal_paper.name} · ` : ''}${inv.phase_count ?? 0}/5 phases`
                        : `${inv.corpus?.name ? `${inv.corpus.name} · ` : ''}${inv.phase_count ?? 0}/5 phases`}
                    </span>
                  </div>
                  {inv.status && (
                    <span style={{ fontFamily: T.mono, fontSize: 10, color: T.rust, border: `1px solid ${T.rustDim}`, borderRadius: 3, padding: '2px 7px' }}>{inv.status}</span>
                  )}
                </Link>
              ))}
            </div>
          </section>
        )}

        {/* Faceting notes */}
        {notes.length > 0 && (
          <section style={{ background: T.panel, border: `1px solid ${T.borderDim}`, borderRadius: 4 }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, padding: '14px 16px 8px' }}>
              <h3 style={{ margin: 0, fontFamily: T.mono, fontSize: 10.5, fontWeight: 600, letterSpacing: '1.4px', textTransform: 'uppercase', color: T.fg }}>Faceting Pipelines</h3>
              <span style={{ fontFamily: T.mono, fontSize: 10.5, color: T.fgFaint }}>{notes.length}</span>
            </div>
            <div>
              {notes.map((n) => (
                <Link
                  key={n.id}
                  href={`/scientific-literature/faceting-note/${n.id}`}
                  style={{
                    display: 'grid', gridTemplateColumns: '84px 1fr', gap: 14, alignItems: 'center',
                    padding: '10px 16px', borderTop: `1px solid ${T.borderDim}`, textDecoration: 'none', color: 'inherit',
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(90,173,175,0.06)'; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
                >
                  <TypeChip short="PIPELINE" color={T.olive} icon="bar-chart" />
                  <div style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
                    <span style={{ fontSize: 13.5, color: T.fg, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{n.name}</span>
                    <span style={{ fontFamily: T.mono, fontSize: 10.5, color: T.fgFaint }}>
                      {(n.collections || []).map((c) => c.name).join(' · ') || (n.has_content ? 'has content' : 'no content')}
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
