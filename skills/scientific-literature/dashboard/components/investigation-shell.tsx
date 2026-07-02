'use client';

import { useState, useEffect, useMemo } from 'react';
import Link from 'next/link';
import { T } from './tokens';
import { Icon } from './atoms';
import { withDb, syncDbFromUrl } from './db';
import { DatabaseSelector } from './database-selector';
import { StageView, StagePlaceholder } from './stage-view';
import type { InvestigationDetail, InvestigationPhase, StageDetail } from '@/lib/scientific-literature';

const STAGE_ORDER = ['discovery', 'ingest', 'sensemaking', 'analysis', 'report'];
const STAGE_LABEL: Record<string, string> = {
  discovery: 'Discovery', ingest: 'Ingestion', sensemaking: 'Sensemaking', analysis: 'Analysis', report: 'Report',
};

// Investigation shell: a persistent left-nav that always shows the five canonical stages per
// iteration (a stage with no phase record yet is shown muted and renders a "not started"
// placeholder). The active stage is `<iter>:<kind>` in the URL hash (shareable).
export function InvestigationShell({ id }: { id: string }) {
  const [inv, setInv] = useState<InvestigationDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<{ iter: number; kind: string } | null>(null);
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
        const firstIter = phases.length ? Math.min(...phases.map((p) => p.iteration ?? 1)) : 1;
        const [hi, hk] = (typeof window !== 'undefined' ? window.location.hash.replace('#', '') : '').split(':');
        if (hk && STAGE_ORDER.includes(hk)) {
          setActive({ iter: Number(hi) || firstIter, kind: hk });
        } else {
          const sens = phases.find((p) => p.phase === 'sensemaking');
          if (sens) setActive({ iter: sens.iteration ?? 1, kind: 'sensemaking' });
          else if (phases[0]) setActive({ iter: phases[0].iteration ?? 1, kind: phases[0].phase });
          else setActive({ iter: firstIter, kind: 'discovery' });
        }
      })
      .catch((err) => setError(String(err)));
  }, [id]);

  // (iteration, kind) -> phase record (only the ones that exist)
  const phaseMap = useMemo(() => {
    const m = new Map<string, InvestigationPhase>();
    for (const p of inv?.phases || []) m.set(`${p.iteration ?? 1}:${p.phase}`, p);
    return m;
  }, [inv]);

  const iterIndices = useMemo(() => {
    const s = new Set<number>((inv?.phases || []).map((p) => p.iteration ?? 1));
    if (!s.size) s.add(1);
    return Array.from(s).sort((a, b) => a - b);
  }, [inv]);

  const activePhaseId = active ? (phaseMap.get(`${active.iter}:${active.kind}`)?.id ?? null) : null;

  useEffect(() => {
    if (!active) return;
    if (typeof window !== 'undefined') window.history.replaceState(null, '', `#${active.iter}:${active.kind}`);
    const pid = phaseMap.get(`${active.iter}:${active.kind}`)?.id;
    if (!pid) { setStage(null); return; }   // not-started stage -> placeholder (no fetch)
    setStageLoading(true);
    fetch(withDb(`/api/scientific-literature/stage/${pid}`))
      .then((r) => (r.ok ? r.json() : Promise.reject(`API ${r.status}`)))
      .then((json) => setStage(json.error ? null : json))
      .catch(() => setStage(null))
      .finally(() => setStageLoading(false));
  }, [active, phaseMap]);

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
        {/* left nav — always the five canonical stages */}
        <nav style={{ display: 'flex', flexDirection: 'column', gap: 14, position: 'sticky', top: 16, alignSelf: 'start' }}>
          {iterIndices.map((iter) => (
            <div key={iter}>
              <div style={{ fontFamily: T.mono, fontSize: 10, letterSpacing: '1px', textTransform: 'uppercase', color: T.fgDim, marginBottom: 6 }}>Iteration {iter}</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                {STAGE_ORDER.map((kind) => {
                  const exists = !!phaseMap.get(`${iter}:${kind}`)?.id;
                  const isActive = active?.iter === iter && active?.kind === kind;
                  return (
                    <button
                      key={kind}
                      onClick={() => setActive({ iter, kind })}
                      title={exists ? undefined : 'Not started'}
                      style={{
                        textAlign: 'left', cursor: 'pointer', fontFamily: T.sans, fontSize: 13,
                        color: isActive ? T.teal : exists ? T.fgDim : T.fgFaint,
                        background: isActive ? T.tealDim : 'transparent',
                        border: `1px solid ${isActive ? T.borderHi : 'transparent'}`, borderRadius: 3, padding: '6px 10px',
                        display: 'flex', alignItems: 'center', gap: 8, opacity: exists ? 1 : 0.6,
                      }}
                    >
                      <span style={{ width: 6, height: 6, borderRadius: 6, background: isActive ? T.teal : exists ? T.fgFaint : 'transparent', border: exists ? 'none' : `1px solid ${T.fgFaint}` }} />
                      {STAGE_LABEL[kind] || kind}
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
          {active && !activePhaseId && <StagePlaceholder kind={active.kind} />}
          {activePhaseId && stageLoading && <span style={{ fontFamily: T.mono, fontSize: 11, color: T.fgFaint }}>Loading stage…</span>}
          {activePhaseId && !stageLoading && stage && <StageView stage={stage} />}
          {!active && inv && <span style={{ fontFamily: T.mono, fontSize: 11, color: T.fgFaint }}>Select a stage.</span>}
        </main>
      </div>
    </div>
  );
}
