'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { T } from '@/components/scientific-literature/tokens';
import { BackNav, Panel } from '@/components/scientific-literature/atoms';
import type { SynthesisView } from '@/lib/scientific-literature';

const STANCE_COLOR: Record<string, string> = {
  consensus: T.mint, contested: T.rust, emerging: T.olive,
};

export function KqedView({ id }: { id: string }) {
  const [data, setData] = useState<SynthesisView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`/api/scientific-literature/kqed/${id}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(`API ${r.status}`)))
      .then((j) => (j.error ? setError(j.error) : setData(j)))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [id]);

  return (
    <div style={{ minHeight: '100vh', background: T.bg, color: T.fg, fontFamily: T.sans }}>
      <header style={{ borderBottom: `1px solid ${T.borderDim}`, background: T.bgRaised, padding: '20px 24px' }}>
        <div style={{ maxWidth: 1100, margin: '0 auto', display: 'flex', alignItems: 'center', gap: 24 }}>
          <BackNav href="/scientific-literature" label="Scientific Literature" />
          <div style={{ flex: 1 }}>
            <div style={{ fontFamily: T.mono, fontSize: 11, color: T.fgDim, marginBottom: 4 }}>KQED INVESTIGATION · {id}</div>
            <h1 style={{ margin: 0, fontFamily: T.serif, fontSize: 24, fontWeight: 400, letterSpacing: '-0.3px' }}>
              {data?.question || 'Investigation'}
            </h1>
          </div>
        </div>
      </header>

      <main style={{ maxWidth: 1100, margin: '0 auto', padding: '24px', display: 'flex', flexDirection: 'column', gap: 20 }}>
        {loading && <div style={{ color: T.fgDim, fontFamily: T.mono, fontSize: 12 }}>Loading…</div>}
        {error && <div style={{ color: T.rust, fontFamily: T.mono, fontSize: 12 }}>Error: {error}</div>}

        {data && (
          <>
            <Panel title={`Analysis — synthesis (${data.synthesis.length})`}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {data.synthesis.map((n) => (
                  <div key={n.id} style={{ display: 'flex', gap: 12, alignItems: 'baseline' }}>
                    <span style={{
                      fontFamily: T.mono, fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.5px',
                      color: T.bg, background: STANCE_COLOR[n.stance] || T.fgDim, padding: '2px 7px',
                      borderRadius: 4, whiteSpace: 'nowrap',
                    }}>{n.stance}</span>
                    <div>
                      <div style={{ fontSize: 14 }}>{n.statement}</div>
                      <div style={{ display: 'flex', gap: 6, marginTop: 4, flexWrap: 'wrap' }}>
                        {n.concepts.map((c) => (
                          <a key={c.curie} href={`https://www.ebi.ac.uk/ols4/search?q=${encodeURIComponent(c.curie)}`}
                            target="_blank" rel="noreferrer"
                            style={{ fontFamily: T.mono, fontSize: 10, color: T.teal, textDecoration: 'none',
                              border: `1px solid ${T.borderDim}`, padding: '1px 6px', borderRadius: 4 }}>
                            {c.name} · {c.curie}
                          </a>
                        ))}
                      </div>
                    </div>
                  </div>
                ))}
                {!data.synthesis.length && <div style={{ color: T.fgFaint, fontFamily: T.mono, fontSize: 12 }}>
                  No synthesis yet — run analyze-investigation.</div>}
              </div>
            </Panel>
          </>
        )}
      </main>
    </div>
  );
}
