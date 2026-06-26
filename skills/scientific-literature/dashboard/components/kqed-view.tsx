'use client';

import { useState, useEffect, useMemo } from 'react';
import Link from 'next/link';
import { T } from '@/components/scientific-literature/tokens';
import { BackNav, Panel } from '@/components/scientific-literature/atoms';
import type { SynthesisView, MechEdge } from '@/lib/scientific-literature';

const STANCE_COLOR: Record<string, string> = {
  consensus: T.mint, contested: T.rust, emerging: T.olive,
};
const POSITIVE = new Set(['activates', 'maintains', 'promotes']);

function MechanismGraph({ edges }: { edges: MechEdge[] }) {
  const { nodes, pos, W, H } = useMemo(() => {
    const names = Array.from(new Set(edges.flatMap((e) => [e.s_name, e.o_name])));
    const W = 760, H = 420, cx = W / 2, cy = H / 2, R = Math.min(W, H) / 2 - 70;
    const pos: Record<string, { x: number; y: number }> = {};
    names.forEach((n, i) => {
      const a = (2 * Math.PI * i) / Math.max(names.length, 1) - Math.PI / 2;
      pos[n] = { x: cx + R * Math.cos(a), y: cy + R * Math.sin(a) };
    });
    return { nodes: names, pos, W, H };
  }, [edges]);

  if (!edges.length) return <div style={{ color: T.fgFaint, fontFamily: T.mono, fontSize: 12 }}>No grounded mechanism edges yet.</div>;

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ background: T.bgSunken, borderRadius: 8 }}>
      <defs>
        <marker id="arrowPos" markerWidth="9" markerHeight="9" refX="8" refY="3" orient="auto">
          <path d="M0,0 L8,3 L0,6 Z" fill={T.mint} />
        </marker>
        <marker id="arrowNeg" markerWidth="9" markerHeight="9" refX="8" refY="3" orient="auto">
          <path d="M0,0 L8,3 L0,6 Z" fill={T.rust} />
        </marker>
      </defs>
      {edges.map((e, i) => {
        const a = pos[e.s_name], b = pos[e.o_name];
        if (!a || !b) return null;
        const positive = POSITIVE.has(e.mech_type);
        const col = positive ? T.mint : T.rust;
        // shorten the line so the arrow sits at the node edge
        const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy) || 1;
        const ux = dx / len, uy = dy / len, pad = 34;
        const x1 = a.x + ux * pad, y1 = a.y + uy * pad, x2 = b.x - ux * pad, y2 = b.y - uy * pad;
        return (
          <g key={i}>
            <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={col} strokeWidth={1.6} opacity={0.7}
              markerEnd={`url(#${positive ? 'arrowPos' : 'arrowNeg'})`} />
            <text x={(x1 + x2) / 2} y={(y1 + y2) / 2 - 3} fill={T.fgFaint} fontSize={9}
              fontFamily={T.mono} textAnchor="middle">{e.mech_type}</text>
          </g>
        );
      })}
      {nodes.map((n) => (
        <g key={n}>
          <circle cx={pos[n].x} cy={pos[n].y} r={6} fill={T.blue} stroke={T.borderHi} />
          <text x={pos[n].x} y={pos[n].y - 12} fill={T.fg} fontSize={11} fontFamily={T.sans}
            textAnchor="middle">{n.length > 22 ? n.slice(0, 21) + '…' : n}</text>
        </g>
      ))}
    </svg>
  );
}

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

            <Panel title="Mechanism (System 3 — grounded relationships)">
              <MechanismGraph edges={data.edges} />
              <div style={{ marginTop: 8, fontFamily: T.mono, fontSize: 10, color: T.fgFaint }}>
                <span style={{ color: T.mint }}>▸ positive (activates/maintains)</span>{'   '}
                <span style={{ color: T.rust }}>▸ negative (inhibits/suppresses)</span>{'   '}
                {data.edges.length} grounded edges
              </div>
            </Panel>
          </>
        )}
      </main>
    </div>
  );
}
