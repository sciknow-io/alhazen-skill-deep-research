'use client';

// Paper sensemaking walkthrough, laid out like the standalone readout: a navigable chain
//   claim → grounding observation (↳ its data table) → data table (▸ the KEfED model that
//   generated it) → model diagram.
// Three sections after the checks box: (1) reported claims + observations, (2) KEfED
// experimental-design model diagrams (variables + protocol graph + variable-dependency
// signature), (3) instance data tables (Spreadsheet pivot). Rich components are reused:
// KefedProtocolGraph, Spreadsheet, and the SignatureBlock. In-page anchors make the chain
// click-navigable; gaps close the page.

import { useState, useEffect } from 'react';
import { T } from './tokens';
import { Panel } from './atoms';
import { KefedProtocolGraph } from './kefed-graph';
import { Spreadsheet } from './kefed-instance';
import { withDb } from './db';
import type {
  PaperCurationDetail, BundleDetail, ObservationNode, InstanceDetail, TemplateDetail,
  OoevvVarBrief, SensemakingCheck, InvestigationPaperRef, DataSignature,
} from '@/lib/scientific-literature';

// ─── styles ─────────────────────────────────────────────────────
const subheadS: React.CSSProperties = { fontFamily: T.mono, fontSize: 10, fontWeight: 600, color: T.fgDim, textTransform: 'uppercase', letterSpacing: '0.7px', margin: '0 0 6px' };
const tagS: React.CSSProperties = { fontFamily: T.mono, fontSize: 9.5, color: T.fgFaint, textTransform: 'uppercase', letterSpacing: '0.5px', border: `1px solid ${T.borderDim}`, borderRadius: 3, padding: '1px 6px' };
const jumpS: React.CSSProperties = { fontFamily: T.mono, fontSize: 10.5, color: T.teal, textDecoration: 'none', whiteSpace: 'nowrap' };
const panelBoxS: React.CSSProperties = { border: `1px solid ${T.borderDim}`, borderRadius: 6, padding: '12px 14px', background: T.bgRaised, marginBottom: 12, scrollMarginTop: 60 };

// ─── sensemaking linter (collapsible) ───────────────────────────
function SensemakingChecksBox({ paperId }: { paperId?: string }) {
  const [checks, setChecks] = useState<SensemakingCheck[] | null>(null);
  const [summary, setSummary] = useState<{ passed: number; warned: number; failed: number } | null>(null);

  useEffect(() => {
    if (!paperId) return;
    fetch(withDb(`/api/scientific-literature/paper/${paperId}/checks`))
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => { if (j && j.checks) { setChecks(j.checks); setSummary(j.summary); } })
      .catch(() => { /* linter unavailable — box stays quiet */ });
  }, [paperId]);

  const color = (s: string) => (s === 'pass' ? T.olive : s === 'warn' ? T.rust : '#e05555');
  const glyph = (s: string) => (s === 'pass' ? '✓' : s === 'warn' ? '!' : '✗');

  return (
    <details style={{ border: `1px solid ${T.border}`, borderRadius: 4, background: T.panel }}>
      <summary style={{
        cursor: 'pointer', padding: '11px 16px', display: 'flex', alignItems: 'center', gap: 12,
        fontFamily: T.mono, fontSize: 10.5, letterSpacing: '1.2px', textTransform: 'uppercase', color: T.fgDim,
      }}>
        <span>Sensemaking checks</span>
        {summary ? (
          <span style={{ fontFamily: T.mono, fontSize: 11, textTransform: 'none', letterSpacing: 0 }}>
            <span style={{ color: T.olive }}>{summary.passed} pass</span>
            <span style={{ color: T.fgFaint }}> · </span>
            <span style={{ color: T.rust }}>{summary.warned} warn</span>
            <span style={{ color: T.fgFaint }}> · </span>
            <span style={{ color: '#e05555' }}>{summary.failed} fail</span>
          </span>
        ) : <span style={{ color: T.fgFaint, textTransform: 'none', letterSpacing: 0 }}>running…</span>}
      </summary>
      <div style={{ padding: '4px 16px 14px', display: 'flex', flexDirection: 'column', gap: 6 }}>
        {!checks && <span style={{ fontFamily: T.mono, fontSize: 11, color: T.fgFaint }}>Running checks…</span>}
        {checks && checks.map((c) => (
          <div key={c.id} style={{ display: 'grid', gridTemplateColumns: '18px 1fr auto', gap: 8, alignItems: 'baseline' }}>
            <span style={{ color: color(c.status), fontFamily: T.mono, fontWeight: 700 }}>{glyph(c.status)}</span>
            <div>
              <span style={{ fontSize: 13, color: T.fg }}>{c.name}</span>
              <span style={{ marginLeft: 8, fontFamily: T.mono, fontSize: 10, color: T.fgFaint, textTransform: 'uppercase' }}>{c.category}</span>
              <div style={{ fontSize: 12, color: T.fgDim }}>{c.detail}</div>
            </div>
            {c.offenders.length > 0 && <span style={{ fontFamily: T.mono, fontSize: 10.5, color: color(c.status) }}>{c.offenders.length}</span>}
          </div>
        ))}
      </div>
    </details>
  );
}

// ─── claim type badge ───────────────────────────────────────────
const TYPE_COLOR: Record<string, string> = { primary: T.teal, secondary: T.blue, peripheral: T.fgFaint };
function ClaimBadge({ type }: { type?: string }) {
  const c = TYPE_COLOR[type || ''] || T.fgFaint;
  return (
    <span style={{
      fontFamily: T.mono, fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.8px',
      color: c, border: `1px solid ${c}66`, borderRadius: 3, padding: '2px 8px',
    }}>{type || 'claim'}</span>
  );
}

// ─── one observation: label + content + verbatim quotes + ↳ link to its data table ──
function ObservationBlock({ obs, quotes, instanceId, instanceName }: {
  obs: ObservationNode;
  quotes: Array<{ frag: string; quote: string }>;
  instanceId?: string;
  instanceName?: string;
}) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
        {obs.name && <span style={{ fontFamily: T.mono, fontSize: 11, color: T.olive }}>{obs.name}</span>}
        {obs.knowledge_level && <span style={tagS}>{obs.knowledge_level}</span>}
        {obs.bio_scale && <span style={tagS}>{obs.bio_scale}</span>}
        {instanceId && <a href={`#inst-${instanceId}`} style={jumpS}>↳ {instanceName || 'data table'}</a>}
      </div>
      {obs.content && <p style={{ margin: '4px 0 0', fontSize: 13, lineHeight: 1.55, color: T.fg }}>{obs.content}</p>}
      {quotes.map((q, i) => (
        <blockquote key={i} style={{
          margin: '6px 0 0', padding: '2px 0 2px 10px', borderLeft: `2px solid ${T.oliveDim}`,
          fontSize: 12.5, lineHeight: 1.5, color: T.fgDim, fontStyle: 'italic',
        }}>
          “{q.quote}”
          {q.frag && <span style={{ fontFamily: T.mono, fontSize: 9.5, color: T.fgFaint, fontStyle: 'normal', marginLeft: 6 }}>{q.frag}</span>}
        </blockquote>
      ))}
    </div>
  );
}

// ─── cite chip (cross-paper hinge) ──────────────────────────────
function CiteChip({ paper }: { paper: InvestigationPaperRef }) {
  const label = paper.name || paper.id;
  if (paper.id) {
    return <a href={`/scientific-literature/paper/${encodeURIComponent(paper.id)}`}
      style={{ fontFamily: T.mono, fontSize: 10.5, color: T.teal, textDecoration: 'none' }}>{label}</a>;
  }
  return <span style={{ fontFamily: T.mono, fontSize: 10.5, color: T.fgDim }}>{label}</span>;
}

// ─── VARIABLES list (mirrors the /template page) ────────────────
function VariablesList({ vars }: { vars?: OoevvVarBrief[] }) {
  if (!vars || !vars.length) return null;
  const roleColor = (r?: string) => (r === 'measurement' ? T.teal : r === 'constant' ? T.fgFaint : T.blue);
  return (
    <div style={{ marginBottom: 4 }}>
      <div style={subheadS}>Variables</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {vars.map((v) => (
          <div key={v.id} style={{ fontFamily: T.sans, fontSize: 12.5, color: T.fg }}>
            <span style={{ fontFamily: T.mono, fontSize: 10, color: roleColor(v.role), marginRight: 6 }}>[{v.role}]</span>
            {v.name}
            {v.quality?.quality && <span style={{ color: T.fgFaint }}> · measures {v.quality.quality}</span>}
            {v.definition && <div style={{ fontFamily: T.sans, fontSize: 11.5, color: T.fgDim, paddingLeft: 18 }}>{v.definition}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── variable-dependency signature: the structure a data table must conform to ──
function SignatureBlock({ sig }: { sig?: DataSignature }) {
  if (!sig || Object.keys(sig).length === 0) return null;
  return (
    <div style={{ marginTop: 10 }}>
      <div style={subheadS}>Variable dependencies — each measurement is indexed by</div>
      {Object.entries(sig).map(([vid, v]) => (
        <div key={vid} style={{ fontFamily: T.mono, fontSize: 11, color: T.fgDim, margin: '3px 0', lineHeight: 1.5 }}>
          <span style={{ color: T.teal }}>◆ {v.name}</span>
          {' ⟵ '}
          {(v.index || []).map((x) => x.name).join(', ') || '—'}
          {v.consumed && v.consumed.length > 0 && (
            <span style={{ color: T.rust }}> · ✕ consumes {v.consumed.map((x) => x.name).join(', ')}</span>
          )}
        </div>
      ))}
    </div>
  );
}

// ─── one KEfED model diagram: variables + protocol graph + dependency signature ──
function ModelBlock({ tid, name, tpl, sig }: { tid: string; name?: string; tpl?: TemplateDetail | null; sig?: DataSignature }) {
  return (
    <div id={`model-${tid}`} style={panelBoxS}>
      <div style={{ fontFamily: T.serif, fontSize: 14.5, color: T.fg, marginBottom: 6 }}>{name || tid}</div>
      {tpl?.definition && <p style={{ margin: '0 0 10px', fontSize: 12.5, color: T.fgDim, lineHeight: 1.5 }}>{tpl.definition}</p>}
      <VariablesList vars={tpl?.variables} />
      {tpl?.graph && (tpl.graph.processes || []).length > 0 && (
        <div style={{ marginTop: 10 }}>
          <div style={subheadS}>KEfED protocol graph</div>
          <KefedProtocolGraph exp={{ id: tid, name, experiment: tpl.graph }} />
        </div>
      )}
      <SignatureBlock sig={sig} />
    </div>
  );
}

// ─── one instance data table (Spreadsheet pivot) + ▸ link to its model ──
function TableBlock({ inst, modelName }: { inst: InstanceDetail; modelName?: string }) {
  const tid = inst.template?.id;
  return (
    <div id={`inst-${inst.id}`} style={panelBoxS}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap', marginBottom: 8 }}>
        <span style={{ fontFamily: T.serif, fontSize: 14, color: T.fg }}>{inst.name || inst.id}</span>
        {tid && <a href={`#model-${tid}`} style={{ fontFamily: T.mono, fontSize: 10.5, color: T.olive, textDecoration: 'none' }}>▸ generated by KEfED model: {modelName || tid} ↑</a>}
      </div>
      <Spreadsheet tpl={inst.template_detail} data={inst.data || []} />
    </div>
  );
}

// ─── main walkthrough ───────────────────────────────────────────
export function PaperCuration({ data }: { data: PaperCurationDetail }) {
  const b = data.bundle || ({} as BundleDetail);
  const claims = b.reported_claims || [];
  const observations = b.observations || [];
  const gaps = b.reported_gaps || [];
  const instances = b.instances || [];

  const obsById = new Map(observations.map((o) => [o.id, o] as const));

  // claim -> observation ids (scilit-claim-observation)
  const claimObsIds = new Map<string, string[]>();
  for (const co of data.claim_observations || []) {
    const arr = claimObsIds.get(co.claim) || [];
    arr.push(co.observation);
    claimObsIds.set(co.claim, arr);
  }
  // observation id -> verbatim fragment quotes (alh-derivation)
  const quotesByObs = new Map<string, Array<{ frag: string; quote: string }>>();
  for (const dv of data.derivations || []) {
    if (!dv.quote) continue;
    const arr = quotesByObs.get(dv.note) || [];
    arr.push({ frag: dv.frag, quote: dv.quote });
    quotesByObs.set(dv.note, arr);
  }
  // observation id -> instance it evidences (real kefed-datum-observation link)
  const obsInstances = data.observation_instances || {};
  const instById = new Map(instances.map((i) => [i.id, i] as const));

  // unique KEfED models (dedup by template id), order-stable by first instance
  const modelOrder: string[] = [];
  const modelMeta = new Map<string, { name?: string; tpl?: TemplateDetail | null }>();
  for (const inst of instances) {
    const tid = inst.template?.id;
    if (tid && !modelMeta.has(tid)) {
      modelMeta.set(tid, { name: inst.template?.name || inst.template_detail?.name, tpl: inst.template_detail });
      modelOrder.push(tid);
    }
  }

  const nav = [
    claims.length && { id: 'claims', label: 'Claims' },
    modelOrder.length && { id: 'models', label: 'Model diagrams' },
    instances.length && { id: 'tables', label: 'Data tables' },
    gaps.length && { id: 'gaps', label: 'Gaps' },
  ].filter(Boolean) as Array<{ id: string; label: string }>;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <SensemakingChecksBox paperId={data.paper?.id} />

      {nav.length > 1 && (
        <nav style={{
          position: 'sticky', top: 0, zIndex: 5, background: T.panelHi, backdropFilter: 'blur(6px)',
          border: `1px solid ${T.border}`, borderRadius: 4, padding: '10px 14px', display: 'flex', flexWrap: 'wrap', gap: 12,
        }}>
          <span style={{ fontFamily: T.mono, fontSize: 10, letterSpacing: '1.2px', textTransform: 'uppercase', color: T.fgDim }}>
            claim → observation (↳) → data table → model (▸):
          </span>
          {nav.map((t) => <a key={t.id} href={`#${t.id}`} style={jumpS}>{t.label}</a>)}
        </nav>
      )}

      {/* 1. reported claims → grounding observations */}
      {claims.length > 0 && (
        <section id="claims" style={{ scrollMarginTop: 60 }}>
          <Panel title={`Reported claims → grounding observations (${claims.length})`}>
            {claims.map((c) => {
              const oids = claimObsIds.get(c.id) || [];
              return (
                <div key={c.id} id={`claim-${c.id}`} style={{ borderLeft: `3px solid ${T.blue}`, paddingLeft: 12, margin: '14px 0', scrollMarginTop: 60 }}>
                  <ClaimBadge type={c.type} />
                  <p style={{ margin: '5px 0', fontFamily: T.serif, fontSize: 15, lineHeight: 1.5, color: T.fg }}>{c.statement}</p>
                  {c.cites && c.cites.length > 0 && (
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'baseline', marginBottom: 4 }}>
                      <span style={{ fontFamily: T.mono, fontSize: 9.5, color: T.fgFaint, textTransform: 'uppercase' }}>cites</span>
                      {c.cites.map((p) => <CiteChip key={p.id} paper={p} />)}
                    </div>
                  )}
                  {oids.length
                    ? oids.map((oid) => {
                        const o = obsById.get(oid);
                        if (!o) return null;
                        const iid = obsInstances[oid]?.[0];
                        return <ObservationBlock key={oid} obs={o} quotes={quotesByObs.get(oid) || []}
                          instanceId={iid} instanceName={iid ? instById.get(iid)?.template?.name : undefined} />;
                      })
                    : <span style={{ fontFamily: T.mono, fontSize: 11, color: T.fgFaint }}>— no linked observation —</span>}
                </div>
              );
            })}
          </Panel>
        </section>
      )}

      {/* 2. KEfED experimental-design model diagrams */}
      {modelOrder.length > 0 && (
        <section id="models" style={{ scrollMarginTop: 60 }}>
          <Panel title={`KEfED experimental-design models (${modelOrder.length})`}>
            {modelOrder.map((tid) => (
              <ModelBlock key={tid} tid={tid} name={modelMeta.get(tid)?.name} tpl={modelMeta.get(tid)?.tpl} sig={data.signatures?.[tid]} />
            ))}
          </Panel>
        </section>
      )}

      {/* 3. instance data tables */}
      {instances.length > 0 && (
        <section id="tables" style={{ scrollMarginTop: 60 }}>
          <Panel title={`Data tables (${instances.length})`}>
            {instances.map((inst) => <TableBlock key={inst.id} inst={inst} modelName={inst.template?.name} />)}
          </Panel>
        </section>
      )}

      {/* 4. stated gaps */}
      {gaps.length > 0 && (
        <section id="gaps" style={{ scrollMarginTop: 60 }}>
          <Panel title={`Gaps (${gaps.length})`}>
            {gaps.map((g) => (
              <div key={g.id} style={{ marginBottom: 8 }}>
                <p style={{ margin: 0, fontSize: 13, color: T.fg }} title={g.content || g.name}>{g.content || g.name}</p>
                {g.goal && <span style={{ fontFamily: T.mono, fontSize: 10.5, color: T.fgFaint }}>{g.goal}</span>}
              </div>
            ))}
          </Panel>
        </section>
      )}
    </div>
  );
}
