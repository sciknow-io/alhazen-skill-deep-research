'use client';

import { useState, useEffect } from 'react';
import { T } from '@/components/scientific-literature/tokens';
import { Icon, BackNav } from '@/components/scientific-literature/atoms';
import type { AcquisitionWorklist, WorklistItem } from '@/lib/scientific-literature';

const STATUS_COLOR: Record<string, string> = {
  needed: '#e0913a',
  held: T.teal,
  ingested: T.teal,
  'rhetorical-done': T.olive,
  sensemade: T.olive,
};

function StatusChip({ status }: { status: string }) {
  const c = STATUS_COLOR[status] || T.fgFaint;
  return (
    <span style={{ fontFamily: T.mono, fontSize: 10, color: c, border: `1px solid ${c}55`, borderRadius: 3, padding: '2px 7px', whiteSpace: 'nowrap' }}>
      {status}
    </span>
  );
}

function Stat({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 70 }}>
      <span style={{ fontFamily: T.mono, fontSize: 22, color, lineHeight: 1 }}>{value}</span>
      <span style={{ fontFamily: T.mono, fontSize: 9.5, letterSpacing: '0.8px', textTransform: 'uppercase', color: T.fgFaint }}>{label}</span>
    </div>
  );
}

export default function AcquisitionPage() {
  const [data, setData] = useState<AcquisitionWorklist | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'needed' | 'all'>('needed');

  useEffect(() => {
    fetch('/api/scientific-literature/acquisition')
      .then((r) => (r.ok ? r.json() : Promise.reject(`acquisition ${r.status}`)))
      .then((d) => setData(d))
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, []);

  const items = (data?.items || []).filter((it) => (filter === 'needed' ? it.status === 'needed' : true));
  const summary = data?.summary || {};

  return (
    <div style={{ minHeight: '100vh', background: T.bg, color: T.fg, fontFamily: T.sans, display: 'flex', flexDirection: 'column' }}>
      <header style={{ borderBottom: `1px solid ${T.borderDim}`, background: T.bgRaised, padding: '20px 24px' }}>
        <div style={{ maxWidth: 1100, margin: '0 auto', display: 'flex', alignItems: 'center', gap: 24 }}>
          <BackNav href="/scientific-literature" label="Scilit" />
          <div style={{ flex: 1 }}>
            <h1 style={{ margin: 0, fontFamily: T.serif, fontSize: 26, fontWeight: 400, letterSpacing: '-0.4px' }}>Citation-Target Acquisition</h1>
            <span style={{ fontFamily: T.mono, fontSize: 11, color: T.fgDim }}>
              references cited by the Hallmarks-2023 review · download worklist, prioritised by citation-load
            </span>
          </div>
        </div>
      </header>

      <main style={{ maxWidth: 1100, margin: '0 auto', padding: '24px', width: '100%', flex: 1, display: 'flex', flexDirection: 'column', gap: 20 }}>
        {loading && <span style={{ fontFamily: T.mono, fontSize: 11, color: T.fgFaint }}>Loading…</span>}
        {error && (
          <div style={{ background: 'rgba(200,80,80,0.1)', color: '#e05555', padding: '12px 16px', borderRadius: 4, border: '1px solid rgba(200,80,80,0.2)' }}>
            <strong style={{ fontFamily: T.mono, fontSize: 10.5 }}>Error</strong>
            <p style={{ fontSize: 13, margin: '4px 0 0' }}>{error}</p>
          </div>
        )}

        {data && (
          <>
            <section style={{ background: T.panel, border: `1px solid ${T.borderDim}`, borderRadius: 4, padding: '16px 20px', display: 'flex', gap: 32, alignItems: 'center', flexWrap: 'wrap' }}>
              <Stat label="needed" value={summary.needed || 0} color="#e0913a" />
              <Stat label="held" value={summary.held || 0} color={T.teal} />
              <Stat label="sensemade" value={summary.sensemade || 0} color={T.olive} />
              <Stat label="total refs" value={data.total} color={T.fg} />
              <div style={{ flex: 1 }} />
              <div style={{ display: 'flex', gap: 6 }}>
                {(['needed', 'all'] as const).map((f) => (
                  <button
                    key={f}
                    onClick={() => setFilter(f)}
                    style={{
                      fontFamily: T.mono, fontSize: 11, cursor: 'pointer',
                      color: filter === f ? T.bg : T.fgDim,
                      background: filter === f ? T.teal : 'transparent',
                      border: `1px solid ${filter === f ? T.teal : T.borderHi}`,
                      borderRadius: 3, padding: '5px 12px',
                    }}
                  >
                    {f}
                  </button>
                ))}
              </div>
            </section>

            <section style={{ background: T.panel, border: `1px solid ${T.borderDim}`, borderRadius: 4 }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, padding: '14px 16px 8px' }}>
                <h3 style={{ margin: 0, fontFamily: T.mono, fontSize: 10.5, fontWeight: 600, letterSpacing: '1.4px', textTransform: 'uppercase' }}>
                  {filter === 'needed' ? 'To Download' : 'All References'}
                </h3>
                <span style={{ fontFamily: T.mono, fontSize: 10.5, color: T.fgFaint }}>{items.length}</span>
              </div>
              <div>
                {items.map((it: WorklistItem) => (
                  <div
                    key={it.id}
                    style={{
                      display: 'grid', gridTemplateColumns: '46px 1fr 90px 96px', gap: 14, alignItems: 'center',
                      padding: '10px 16px', borderTop: `1px solid ${T.borderDim}`,
                    }}
                  >
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1 }}>
                      <span style={{ fontFamily: T.mono, fontSize: 15, color: it.load > 0 ? T.rust : T.fgFaint }}>{it.load}</span>
                      <span style={{ fontFamily: T.mono, fontSize: 8.5, color: T.fgFaint, letterSpacing: '0.5px' }}>LOAD</span>
                    </div>
                    <div style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
                      <span style={{ fontSize: 13.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{it.name}</span>
                      <span style={{ fontFamily: T.mono, fontSize: 10.5, color: T.fgFaint }}>
                        {it.journal ? `${it.journal} · ` : ''}{it.year || ''}{it.ref_numbers.length ? ` · ref ${it.ref_numbers.join(', ')}` : ''}
                      </span>
                    </div>
                    <span style={{
                      fontFamily: T.mono, fontSize: 10, textAlign: 'center',
                      color: it.genre === 'review' ? T.olive : T.teal,
                      border: `1px solid ${(it.genre === 'review' ? T.olive : T.teal)}44`, borderRadius: 3, padding: '2px 6px',
                    }}>
                      {it.genre}
                    </span>
                    {it.status === 'needed' && it.doi_url ? (
                      <a
                        href={it.doi_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{
                          display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 5,
                          fontFamily: T.mono, fontSize: 11, color: '#e0913a', textDecoration: 'none',
                          border: '1px solid #e0913a55', borderRadius: 3, padding: '5px 8px',
                        }}
                        title={it.doi || ''}
                      >
                        <Icon name="download" size={12} color="#e0913a" /> get
                      </a>
                    ) : (
                      <div style={{ display: 'flex', justifyContent: 'center' }}>
                        <StatusChip status={it.status} />
                      </div>
                    )}
                  </div>
                ))}
                {!loading && items.length === 0 && (
                  <div style={{ padding: '16px', fontFamily: T.mono, fontSize: 11, color: T.fgFaint }}>Nothing here.</div>
                )}
              </div>
            </section>
            <p style={{ fontFamily: T.mono, fontSize: 10.5, color: T.fgFaint, margin: 0 }}>
              "get" opens the DOI so you can download the PDF manually. Drop it into the cache and re-run the registry builder to flip the row to "held".
            </p>
          </>
        )}
      </main>
    </div>
  );
}
