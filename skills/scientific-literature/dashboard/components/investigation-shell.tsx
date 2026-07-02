'use client';

import { useState, useEffect, useMemo } from 'react';
import Link from 'next/link';
import { T } from './tokens';
import { Icon } from './atoms';
import { withDb, syncDbFromUrl } from './db';
import { DatabaseSelector } from './database-selector';
import { StageView } from './stage-view';
import type { InvestigationDetail, InvestigationPhase, StageDetail } from '@/lib/scientific-literature';

const STAGE_ORDER = ['discovery', 'ingest', 'sensemaking', 'analysis', 'report'];
const STAGE_LABEL: Record<string, string> = {
  discovery: 'Discovery', ingest: 'Ingestion', sensemaking: 'Sensemaking', analysis: 'Analysis', report: 'Report',
};

// Investigation shell: a persistent left-nav of iterations → stages, plus the selected
// stage's content. The active stage is the phase id in the URL hash (shareable).
export function InvestigationShell({ id }: { id: string }) {
  const [inv, setInv] = useState<InvestigationDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activePhase, setActivePhase] = useState<string | null>(null);
  const [stage, setStage] = useState<StageDetail | null>(null);
  const [stageLoading, setStageLoading] = useState(false);

  useEffect(() => {
    syncDbFromUrl();
    fetch(withDb(`/api/scientific-literature/investigation/${id}`))
      .then((r) => (r.ok ? r.json() : Promise.reject(`API ${r.status}`)))
      .then((json) => {
        if (json.error || json.success === false) { setError(json.error || 'not found'); return; }
        setInv(json);
        const phases: InvestigationPhase[] = json.phases || [];
        const fromHash = typeof window !== 'undefined' ? window.location.hash.replace('#', '') : '';
        const initial = phases.find((p) => p.id === fromHash)
          || phases.find((p) => p.phase === 'sensemaking')
          || phases[0];
        if (initial) setActivePhase(initial.id);
      })
      .catch((err) => setError(String(err)));
  }, [id]);

  // group phases by iteration and sort stages canonically
  const iterations = useMemo(() => {
    const phases: InvestigationPhase[] = inv?.phases || [];
    const byIter = new Map<number, InvestigationPhase[]>();
    for (const p of phases) {
      const it = p.iteration ?? 1;
      if (!byIter.has(it)) byIter.set(it, []);
      byIter.get(it)!.push(p);
    }
    for (const list of byIter.values()) list.sort((a, b) => STAGE_ORDER.indexOf(a.phase) - STAGE_ORDER.indexOf(b.phase));
    return Array.from(byIter.entries()).sort((a, b) => a[0] - b[0]);
  }, [inv]);

  useEffect(() => {
    if (!activePhase) return;
    if (typeof window !== 'undefined') window.history.replaceState(null, '', `#${activePhase}`);
    setStageLoading(true);
    fetch(withDb(`/api/scientific-literature/stage/${activePhase}`))
      .then((r) => (r.ok ? r.json() : Promise.reject(`API ${r.status}`)))
      .then((json) => setStage(json.error ? null : json))
      .catch(() => setStage(null))
      .finally(() => setStageLoading(false));
  }, [activePhase]);

  return (
    <div style={{ minHeight: '100vh', background: T.bg, color: T.fg, fontFamily: T.sans }}>
      <header style={{ borderBottom: `1px solid ${T.borderDim}`, background: T.bgRaised, padding: '16px 24px' }}>
        <div style={{ maxWidth: 1200, margin: '0 auto', display: 'flex', alignItems: 'center', gap: 18 }}>
          <Link href="/scientific-literature" style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontFamily: T.mono, fontSize: 12, color: T.teal, textDecoration: 'none' }}>
            <Icon name="arrow-left" size={14} color={T.teal} /> Investigations
          </Link>
          <div style={{ flex: 1, minWidth: 0 }}>
            <h1 style={{ margin: 0, fontFamily: T.serif, fontSize: 20, fontWeight: 400, color: T.fg, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{inv?.name || id}</h1>
            <span style={{ fontFamily: T.mono, fontSize: 10.5, color: T.fgFaint }}>{inv?.type || '—'} · {inv?.status || '—'}</span>
          </div>
          <DatabaseSelector />
        </div>
      </header>

      {error && <div style={{ maxWidth: 1200, margin: '16px auto', padding: '0 24px', color: '#e05555', fontFamily: T.mono, fontSize: 12 }}>{error}</div>}

      <div style={{ maxWidth: 1200, margin: '0 auto', display: 'grid', gridTemplateColumns: '220px 1fr', gap: 20, padding: '20px 24px' }}>
        {/* left nav */}
        <nav style={{ display: 'flex', flexDirection: 'column', gap: 14, position: 'sticky', top: 16, alignSelf: 'start' }}>
          {iterations.map(([iter, phases]) => (
            <div key={iter}>
              <div style={{ fontFamily: T.mono, fontSize: 10, letterSpacing: '1px', textTransform: 'uppercase', color: T.fgDim, marginBottom: 6 }}>Iteration {iter}</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                {phases.map((p) => {
                  const active = p.id === activePhase;
                  return (
                    <button
                      key={p.id}
                      onClick={() => setActivePhase(p.id)}
                      style={{
                        textAlign: 'left', cursor: 'pointer', fontFamily: T.sans, fontSize: 13,
                        color: active ? T.teal : T.fgDim, background: active ? T.tealDim : 'transparent',
                        border: `1px solid ${active ? T.borderHi : 'transparent'}`, borderRadius: 3, padding: '6px 10px',
                        display: 'flex', alignItems: 'center', gap: 8,
                      }}
                    >
                      <span style={{ width: 6, height: 6, borderRadius: 6, background: active ? T.teal : T.fgFaint }} />
                      {STAGE_LABEL[p.phase] || p.phase}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
          {!inv && !error && <span style={{ fontFamily: T.mono, fontSize: 11, color: T.fgFaint }}>Loading…</span>}
        </nav>

        {/* stage content */}
        <main style={{ display: 'flex', flexDirection: 'column', gap: 16, minWidth: 0 }}>
          {stageLoading && <span style={{ fontFamily: T.mono, fontSize: 11, color: T.fgFaint }}>Loading stage…</span>}
          {stage && <StageView stage={stage} />}
          {!stage && !stageLoading && inv && <span style={{ fontFamily: T.mono, fontSize: 11, color: T.fgFaint }}>Select a stage.</span>}
        </main>
      </div>
    </div>
  );
}
