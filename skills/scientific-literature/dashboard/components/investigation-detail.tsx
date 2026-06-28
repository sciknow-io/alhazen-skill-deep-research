'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { T } from './tokens';
import { BackNav, Panel, MarkdownContent } from './atoms';
import { Shell, Loading, ErrorBox } from './corpus-detail';
import { KefedProtocolGraph } from './kefed-graph';
import { KefedInstance } from './kefed-instance';
import type {
  InvestigationDetail, InvestigationPhase, BundleSummary, BundleDetail,
  SynthesizedClaimNode, ImpactNode, InvestigationPaperRef,
} from '@/lib/scientific-literature';

const STAGES: Array<{ key: string; label: string }> = [
  { key: 'discovery', label: 'Discovery' },
  { key: 'ingest', label: 'Ingest' },
  { key: 'sensemaking', label: 'Sensemaking' },
  { key: 'analysis', label: 'Analysis' },
  { key: 'report', label: 'Report' },
];

const CLAIM_TIER_COLOR: Record<string, string> = {
  primary: T.rust, secondary: T.olive, peripheral: T.fgFaint,
};

function statusColor(status?: string): string {
  switch (status) {
    case 'complete': return T.teal;
    case 'report': case 'analysis': return T.olive;
    case 'scoping': return T.fgFaint;
    default: return T.blue;
  }
}

function PaperLink({ paper }: { paper?: InvestigationPaperRef | null }) {
  if (!paper) return null;
  const yr = paper.year ? ` (${paper.year})` : '';
  return (
    <Link href={`/scientific-literature/paper/${paper.id}`}
      style={{ color: T.blue, textDecoration: 'none' }}>
      {paper.name || paper.id}{yr}
    </Link>
  );
}

export function InvestigationDetailView({ id }: { id: string }) {
  const [data, setData] = useState<InvestigationDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [stage, setStage] = useState<string>('sensemaking');
  const [iter, setIter] = useState<number>(1);

  useEffect(() => {
    fetch(`/api/scientific-literature/investigation/${id}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(`API returned ${r.status}`)))
      .then((json) => {
        if (json.error || json.success === false) setError(json.error || 'Investigation not found');
        else {
          setData(json);
          const iters = (json.phases || []).map((p: InvestigationPhase) => p.iteration || 1);
          if (iters.length) setIter(Math.max(...iters));
        }
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <Shell><Loading /></Shell>;
  if (error || !data) return <Shell><ErrorBox message={error || 'Not found'} /></Shell>;

  const iterations = Array.from(new Set((data.phases || []).map((p) => p.iteration || 1))).sort((a, b) => a - b);
  const phaseFor = (key: string): InvestigationPhase | undefined =>
    (data.phases || []).find((p) => p.phase === key && (p.iteration || 1) === iter);

  const stageCount = (key: string): number => {
    if (key === 'sensemaking') return (phaseFor('sensemaking')?.bundles || []).length;
    if (key === 'analysis') return (data.synthesized_claims || []).length;
    return phaseFor(key)?.content ? 1 : 0;
  };

  return (
    <Shell>
      <BackNav href="/scientific-literature" label="Scientific Literature" />

      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <h1 style={{ fontFamily: T.serif, fontSize: 26, color: T.fg, margin: 0 }}>
            {data.name || data.id}
          </h1>
          {data.status && (
            <span style={{
              fontFamily: T.mono, fontSize: 11, padding: '3px 10px', borderRadius: 12,
              color: statusColor(data.status), background: T.tintBg(statusColor(data.status)),
              border: `1px solid ${statusColor(data.status)}`,
            }}>{data.status}</span>
          )}
        </div>
        <div style={{ fontFamily: T.mono, fontSize: 12, color: T.fgDim, marginTop: 8, display: 'flex', gap: 18, flexWrap: 'wrap' }}>
          {data.corpus && <span>corpus: {data.corpus.name || data.corpus.id}</span>}
          {data.collection?.count != null && <span>{data.collection.count} papers</span>}
          {data.focal_paper && <span>seed: <PaperLink paper={data.focal_paper} /></span>}
        </div>
        {iterations.length > 1 && (
          <div style={{ display: 'flex', gap: 6, marginTop: 12, alignItems: 'center' }}>
            <span style={{ fontFamily: T.mono, fontSize: 11, color: T.fgFaint }}>iteration:</span>
            {iterations.map((n) => (
              <button key={n} onClick={() => setIter(n)} style={{
                fontFamily: T.mono, fontSize: 11, padding: '2px 10px', borderRadius: 10, cursor: 'pointer',
                color: n === iter ? T.bg : T.fgDim,
                background: n === iter ? T.olive : 'transparent',
                border: `1px solid ${n === iter ? T.olive : T.border}`,
              }}>v{n}</button>
            ))}
          </div>
        )}
      </div>

      {/* Two-column: stage sidebar + main */}
      <div style={{ display: 'flex', gap: 28, alignItems: 'flex-start' }}>
        <aside style={{ width: 188, flexShrink: 0, position: 'sticky', top: 16 }}>
          <nav style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {STAGES.map(({ key, label }) => {
              const active = key === stage;
              const count = stageCount(key);
              const done = key === 'sensemaking' || key === 'analysis' ? count > 0 : !!phaseFor(key)?.content;
              return (
                <button key={key} onClick={() => setStage(key)} style={{
                  display: 'flex', alignItems: 'center', gap: 10, textAlign: 'left', cursor: 'pointer',
                  padding: '9px 12px', borderRadius: 6, border: 'none',
                  borderLeft: `3px solid ${active ? T.rust : 'transparent'}`,
                  background: active ? T.tintBg(T.rust) : 'transparent',
                  color: active ? T.rust : T.fgDim, fontFamily: T.sans, fontSize: 13,
                }}>
                  <span style={{
                    width: 7, height: 7, borderRadius: 4, flexShrink: 0,
                    background: done ? (active ? T.rust : T.olive) : 'rgba(200,221,232,0.15)',
                  }} />
                  <span style={{ flex: 1 }}>{label}</span>
                  {count > 0 && (
                    <span style={{ fontFamily: T.mono, fontSize: 11, color: active ? T.rust : T.fgFaint }}>{count}</span>
                  )}
                </button>
              );
            })}
          </nav>
        </aside>

        <main style={{ flex: 1, minWidth: 0 }}>
          {stage === 'sensemaking'
            ? <SensemakingStage phase={phaseFor('sensemaking')} />
            : stage === 'analysis'
              ? <AnalysisStage phase={phaseFor('analysis')} claims={data.synthesized_claims || []} impacts={data.citation_impacts || []} />
              : <NarrativeStage phase={phaseFor(stage)} label={STAGES.find((s) => s.key === stage)?.label || stage} purpose={stage === 'discovery' ? data.purpose : undefined} />}
        </main>
      </div>
    </Shell>
  );
}

function NarrativeStage({ phase, label, purpose }: { phase?: InvestigationPhase; label: string; purpose?: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {purpose && (
        <Panel title="Purpose" borderColor={T.border}>
          <MarkdownContent content={purpose} />
        </Panel>
      )}
      <Panel title={`${label} stage`} borderColor={T.border}>
        {phase?.content
          ? <MarkdownContent content={phase.content} />
          : <p style={{ color: T.fgFaint, fontFamily: T.mono, fontSize: 13 }}>Not recorded for this iteration.</p>}
      </Panel>
    </div>
  );
}

function SensemakingStage({ phase }: { phase?: InvestigationPhase }) {
  const bundles = phase?.bundles || [];
  const [openId, setOpenId] = useState<string | null>(null);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Panel title={`Per-paper sensemaking (${bundles.length} bundles)`} borderColor={T.border}>
        {bundles.length === 0 && (
          <p style={{ color: T.fgFaint, fontFamily: T.mono, fontSize: 13 }}>No sensemaking bundles yet.</p>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {bundles.map((b) => (
            <BundleRow key={b.id} bundle={b} open={openId === b.id}
              onToggle={() => setOpenId(openId === b.id ? null : b.id)} />
          ))}
        </div>
      </Panel>
    </div>
  );
}

function BundleRow({ bundle, open, onToggle }: { bundle: BundleSummary; open: boolean; onToggle: () => void }) {
  const [detail, setDetail] = useState<BundleDetail | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (open && !detail) {
      setBusy(true);
      fetch(`/api/scientific-literature/bundle/${bundle.id}`)
        .then((r) => r.json()).then((j) => { if (!j.error) setDetail(j); })
        .finally(() => setBusy(false));
    }
  }, [open, detail, bundle.id]);
  const pap = bundle.paper;
  return (
    <div style={{ border: `1px solid ${open ? T.borderHi : T.border}`, borderRadius: 6, overflow: 'hidden' }}>
      <button onClick={onToggle} style={{
        width: '100%', textAlign: 'left', cursor: 'pointer', background: open ? T.panelHi : 'transparent',
        border: 'none', padding: '10px 14px', color: T.fg, display: 'flex', gap: 12, alignItems: 'baseline',
      }}>
        <span style={{ flex: 1, fontFamily: T.sans, fontSize: 13 }}>{pap?.name || bundle.name || bundle.id}{pap?.year ? <span style={{ color: T.fgFaint }}> ({pap.year})</span> : null}</span>
        <span style={{ fontFamily: T.mono, fontSize: 11, color: T.fgFaint, flexShrink: 0 }}>
          {bundle.observation_count || 0} obs · {bundle.reported_claim_count || 0} claims · {bundle.reported_gap_count || 0} gaps
        </span>
      </button>
      {open && (
        <div style={{ padding: '4px 14px 14px', borderTop: `1px solid ${T.borderDim}` }}>
          {busy && <p style={{ color: T.fgFaint, fontFamily: T.mono, fontSize: 12 }}>loading…</p>}
          {detail && <BundleBody detail={detail} />}
        </div>
      )}
    </div>
  );
}

function BundleBody({ detail }: { detail: BundleDetail }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginTop: 10 }}>
      {!!(detail.instances || []).length && (
        <Section label={`Template instances (${detail.instances!.length}) — design reused, data filled`}>
          {detail.instances!.map((i) => <KefedInstance key={i.id} inst={i} />)}
        </Section>
      )}
      {!!(detail.experiments || []).length && (
        <Section label={`KEfED protocol graphs (${detail.experiments!.length} experiments)`}>
          {detail.experiments!.map((e) => <KefedProtocolGraph key={e.id} exp={e} />)}
        </Section>
      )}
      {!!(detail.observations || []).length && (
        <Section label="Observations">
          {detail.observations!.map((o) => (
            <div key={o.id} style={{ marginBottom: 10 }}>
              <div style={{ fontFamily: T.sans, fontSize: 13, color: T.fg }}>
                <span style={{ fontFamily: T.mono, fontSize: 10, color: T.teal, marginRight: 6 }}>
                  [{o.knowledge_level || '?'}/{o.bio_scale || '?'}]
                </span>
                {o.content || o.name}
              </div>
              {o.kefed_frame && (o.kefed_frame.variables || []).length > 0 && (
                <div style={{ fontFamily: T.mono, fontSize: 11, color: T.fgDim, marginTop: 3, paddingLeft: 8 }}>
                  design: {o.kefed_frame.variables!.map((v) => `${v.name} (${v.role})`).join(' · ')}
                </div>
              )}
            </div>
          ))}
        </Section>
      )}
      {!!(detail.reported_claims || []).length && (
        <Section label="Reported claims">
          {detail.reported_claims!.map((c) => (
            <div key={c.id} style={{ marginBottom: 8 }}>
              <span style={{ fontFamily: T.mono, fontSize: 10, color: CLAIM_TIER_COLOR[c.type || ''] || T.fgFaint, marginRight: 6 }}>
                [{c.type || '?'}]
              </span>
              <span style={{ fontFamily: T.sans, fontSize: 13, color: T.fg }}>{c.statement}</span>
              {!!(c.cites || []).length && (
                <div style={{ fontFamily: T.mono, fontSize: 11, color: T.fgDim, marginTop: 2, paddingLeft: 8 }}>
                  cites: {c.cites!.map((p, i) => <span key={p.id}>{i ? ', ' : ''}<PaperLink paper={p} /></span>)}
                </div>
              )}
            </div>
          ))}
        </Section>
      )}
      {!!(detail.reported_gaps || []).length && (
        <Section label="Reported gaps">
          {detail.reported_gaps!.map((g) => (
            <div key={g.id} style={{ fontFamily: T.sans, fontSize: 13, color: T.fg, marginBottom: 6 }}>
              {g.name}{g.goal ? <span style={{ color: T.fgFaint }}> — goal: {g.goal}</span> : null}
            </div>
          ))}
        </Section>
      )}
    </div>
  );
}

function AnalysisStage({ phase, claims, impacts }: { phase?: InvestigationPhase; claims: SynthesizedClaimNode[]; impacts: ImpactNode[] }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {phase?.content && (
        <Panel title="Analysis notes" borderColor={T.border}><MarkdownContent content={phase.content} /></Panel>
      )}
      {!!(phase?.faceting_notes || []).length && (
        <Panel title="Faceting pipelines" borderColor={T.border}>
          {phase!.faceting_notes!.map((f) => (
            <Link key={f.id} href={`/scientific-literature/faceting-note/${f.id}`}
              style={{ display: 'block', color: T.blue, textDecoration: 'none', fontFamily: T.mono, fontSize: 12, marginBottom: 4 }}>
              {f.name || f.id}
            </Link>
          ))}
        </Panel>
      )}
      <Panel title={`Synthesized claims & warrants (${claims.length})`} borderColor={T.border}>
        {claims.length === 0 && <p style={{ color: T.fgFaint, fontFamily: T.mono, fontSize: 13 }}>None yet.</p>}
        {claims.map((c) => (
          <div key={c.id} style={{ marginBottom: 14, paddingBottom: 12, borderBottom: `1px solid ${T.borderDim}` }}>
            <div>
              <span style={{ fontFamily: T.mono, fontSize: 10, color: CLAIM_TIER_COLOR[c.type || ''] || T.fgFaint, marginRight: 6 }}>[{c.type || '?'}]</span>
              <span style={{ fontFamily: T.sans, fontSize: 14, color: T.fg }}>{c.statement}</span>
            </div>
            {(c.evidence || []).map((w) => (
              <div key={w.id} style={{ marginTop: 8, paddingLeft: 12, borderLeft: `2px solid ${T.oliveDim}` }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
                  {w.confidence != null && (
                    <span style={{ fontFamily: T.mono, fontSize: 11, color: T.olive }}>conf {Number(w.confidence).toFixed(2)}</span>
                  )}
                  <span style={{ fontFamily: T.sans, fontSize: 13, color: T.fgDim }}>{w.argument}</span>
                </div>
                {!!(w.grounding_instances || []).length && (
                  <div style={{ fontFamily: T.mono, fontSize: 11, color: T.fgFaint, marginTop: 4 }}>
                    grounded in data:{' '}
                    {w.grounding_instances!.map((gi, i) => (
                      <span key={gi.id} style={{ color: T.rust }} title={`${gi.paper || ''} — open this bundle in the Sensemaking stage to see the data rows`}>
                        {i ? ' · ' : ''}{gi.name || gi.id}
                        {gi.paper ? <span style={{ color: T.fgFaint }}> ({gi.paper})</span> : null}
                      </span>
                    ))}
                  </div>
                )}
                {!!(w.grounds || []).length && (
                  <div style={{ fontFamily: T.mono, fontSize: 11, color: T.fgFaint, marginTop: 3 }}>
                    grounds: {w.grounds!.length} reported-claim(s)
                  </div>
                )}
              </div>
            ))}
          </div>
        ))}
      </Panel>
      {!!impacts.length && (
        <Panel title={`Citation impact (${impacts.length})`} borderColor={T.border}>
          {impacts.map((im) => (
            <div key={im.id} style={{ marginBottom: 8 }}>
              <span style={{ fontFamily: T.mono, fontSize: 10, color: T.blue, marginRight: 6 }}>[{im.impact_type || '?'}]</span>
              <PaperLink paper={im.citing_paper} />
              <div style={{ fontFamily: T.sans, fontSize: 13, color: T.fgDim, marginTop: 2 }}>{im.impact_summary}</div>
            </div>
          ))}
        </Panel>
      )}
    </div>
  );
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{ fontFamily: T.mono, fontSize: 11, color: T.teal, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 }}>{label}</div>
      {children}
    </div>
  );
}
