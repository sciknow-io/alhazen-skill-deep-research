'use client';

import { type ReactNode, useState, useEffect } from 'react';
import { T } from './tokens';
import { Panel } from './atoms';
import { Mermaid } from './mermaid';
import { withDb } from './db';
import {
  layerOverviewMermaid, rawLayerMermaid, investigationSpineMermaid,
  claimObservationMermaid, kefedModelMermaid,
  verticalSliceMermaid, signatureCaption,
} from './curation-diagrams';
import type { PaperCurationDetail, OoevvVarBrief, BundleDetail, SensemakingCheck } from '@/lib/scientific-literature';

// Sensemaking linter panel — fetches lint-sensemaking and shows pass/warn/fail per check so a
// curator (or Claude) can see whether the paper's KEfED/OOEVV/KQED curation is well-formed.
function SensemakingChecksPanel({ paperId }: { paperId?: string }) {
  const [checks, setChecks] = useState<SensemakingCheck[] | null>(null);
  const [summary, setSummary] = useState<{ passed: number; warned: number; failed: number } | null>(null);

  useEffect(() => {
    if (!paperId) return;
    fetch(withDb(`/api/scientific-literature/paper/${paperId}/checks`))
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => { if (j && j.checks) { setChecks(j.checks); setSummary(j.summary); } })
      .catch(() => { /* linter unavailable — panel stays quiet */ });
  }, [paperId]);

  if (!checks) return <span style={{ fontFamily: T.mono, fontSize: 11, color: T.fgFaint }}>Running checks…</span>;
  const color = (s: string) => (s === 'pass' ? T.olive : s === 'warn' ? T.rust : '#e05555');
  const glyph = (s: string) => (s === 'pass' ? '✓' : s === 'warn' ? '!' : '✗');
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {summary && (
        <div style={{ fontFamily: T.mono, fontSize: 11, color: T.fgDim, marginBottom: 4 }}>
          <span style={{ color: T.olive }}>{summary.passed} pass</span> · <span style={{ color: T.rust }}>{summary.warned} warn</span> · <span style={{ color: '#e05555' }}>{summary.failed} fail</span>
        </div>
      )}
      {checks.map((c) => (
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
  );
}

// ─── small styled table ────────────────────────────────────────
const thS: React.CSSProperties = {
  fontFamily: T.mono, fontSize: 10, fontWeight: 600, color: T.fgDim, textAlign: 'left',
  padding: '5px 9px', border: `1px solid ${T.borderDim}`, textTransform: 'uppercase', letterSpacing: '0.5px',
  position: 'sticky', top: 0, background: T.bgSunken,
};
const tdS: React.CSSProperties = { padding: '4px 9px', border: `1px solid ${T.borderDim}`, color: T.fg, fontSize: 12, verticalAlign: 'top' };

function DataTable({ headers, rows }: { headers: string[]; rows: ReactNode[][] }) {
  if (!rows.length) return <p style={{ fontFamily: T.mono, fontSize: 11, color: T.fgFaint, margin: 0 }}>— none —</p>;
  return (
    <div style={{ overflowX: 'auto', maxHeight: 460, overflowY: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead><tr>{headers.map((h) => <th key={h} style={thS}>{h}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} style={tdS}>{c}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

const mono = (s: ReactNode) => <code style={{ fontFamily: T.mono, fontSize: 10.5, color: T.teal }}>{s}</code>;

function specLabel(v: OoevvVarBrief): string {
  const s = v.scale;
  if (!s) return '—';
  const vals = s.values?.length ? ` {${s.values.join('/')}}` : '';
  return `${s.type || '?'}${s.unit ? ` (${s.unit})` : ''}${vals}`;
}

// ─── main walkthrough ──────────────────────────────────────────
export function PaperCuration({ data }: { data: PaperCurationDetail }) {
  const b = data.bundle || ({} as BundleDetail);
  const experiments = b.experiments || [];

  // aggregate OOEVV vocabulary from the experiments' variables
  const qualities = new Map<string, { name: string; definition?: string; curie?: string; state?: string; specs: Set<string> }>();
  const specs = new Set<string>();
  const varRows: { name: string; role: string; quality: string; spec: string }[] = [];
  for (const e of experiments) {
    for (const p of e.experiment?.processes || []) {
      for (const v of [...(p.parameters || []), ...(p.measurements || [])]) {
        const sl = specLabel(v);
        const qn = v.quality?.quality;
        if (qn) {
          if (!qualities.has(qn)) qualities.set(qn, { name: qn, definition: v.quality?.definition, curie: v.quality?.curie, state: v.quality?.grounding_state, specs: new Set() });
          qualities.get(qn)!.specs.add(sl);
        }
        if (v.scale) specs.add(sl);
        varRows.push({ name: v.name || '?', role: v.role || '?', quality: qn || '—', spec: sl });
      }
    }
  }

  const sections: { id: string; title: string; body: ReactNode }[] = [];

  // ⓪ sensemaking linter
  sections.push({ id: 'checks', title: 'Sensemaking checks', body: <SensemakingChecksPanel paperId={data.paper?.id} /> });

  // ① overview
  sections.push({ id: 'overview', title: 'The five layers', body: <Mermaid chart={layerOverviewMermaid(data)} /> });

  // ② raw
  sections.push({
    id: 'raw', title: '1 · Raw layer — paper, full text & fragments',
    body: (
      <>
        <DataTable headers={['attribute', 'value']} rows={[
          ['id', mono(data.paper?.id)],
          ['name', data.paper?.name],
          ['doi', data.paper?.doi ? <a href={`https://doi.org/${data.paper.doi}`} target="_blank" rel="noreferrer" style={{ color: T.teal }}>{data.paper.doi}</a> : '—'],
          ['year', data.paper?.year ?? '—'],
          ['acquisition-status', data.paper?.acquisition_status ?? '—'],
          ['full-text artifact', data.fulltext ? mono(data.fulltext.id) : '— none —'],
        ]} />
        {data.fragments && data.fragments.length > 0 && (
          <DataTable headers={['frag', 'kind', 'offset', 'verbatim quote']} rows={data.fragments.map((f) => [
            mono(f.id), f.kind || '—', f.offset != null ? `@${f.offset}` : '—',
            <span style={{ color: T.fgDim }}>{f.content}</span>,
          ])} />
        )}
        <Mermaid chart={rawLayerMermaid(data)} />
      </>
    ),
  });

  // ③ investigation spine
  sections.push({ id: 'spine', title: '2 · Investigation spine', body: <Mermaid chart={investigationSpineMermaid(data)} /> });

  // ④ bundle hub
  sections.push({
    id: 'bundle', title: '3 · The sensemaking bundle (the hub)',
    body: <DataTable headers={['relation', 'count', 'meaning']} rows={[
      ['sensemaking-observation', (b.observations || []).length, 'measurements-in-context'],
      ['sensemaking-reported-claim', (b.reported_claims || []).length, 'claims the paper asserts'],
      ['sensemaking-reported-gap', (b.reported_gaps || []).length, 'gaps the paper states'],
      ['sensemaking-experiment', experiments.length + (b.instances || []).length, 'KEfED models + data instances'],
    ].map((r) => [mono(r[0]), r[1], r[2]])} />,
  });

  // ⑤ rhetorical
  const obsById = new Map((b.observations || []).map((o) => [o.id, o]));
  const derivByNote = new Map<string, string[]>();
  for (const dv of data.derivations || []) {
    if (!derivByNote.has(dv.note)) derivByNote.set(dv.note, []);
    if (dv.quote) derivByNote.get(dv.note)!.push(dv.quote);
  }
  sections.push({
    id: 'rhetorical', title: '4 · Rhetorical layer — claims, gaps, observations',
    body: (
      <>
        <h4 style={h4S}>Observations ({(b.observations || []).length})</h4>
        <DataTable headers={['id', 'name', 'knowledge-level', 'bio-scale', 'statement']} rows={(b.observations || []).map((o) => [
          mono(o.id), o.name || '—', o.knowledge_level || '—', o.bio_scale || '—', <span style={{ color: T.fgDim }}>{o.content}</span>,
        ])} />
        <h4 style={h4S}>Claims ({(b.reported_claims || []).length})</h4>
        <DataTable headers={['id', 'type', 'statement', 'cites']} rows={(b.reported_claims || []).map((c) => [
          mono(c.id), c.type || '—', <span style={{ color: T.fgDim }}>{c.statement}</span>,
          (c.cites || []).length ? (c.cites || []).map((x) => x.name || x.id).join('; ') : '—',
        ])} />
        <h4 style={h4S}>Gaps ({(b.reported_gaps || []).length})</h4>
        <DataTable headers={['id', 'statement', 'knowledge-goal']} rows={(b.reported_gaps || []).map((g) => [
          mono(g.id), <span style={{ color: T.fgDim }}>{g.name}</span>, g.goal || '—',
        ])} />
        <h4 style={h4S}>How claims stand on observations</h4>
        {data.claim_observations && data.claim_observations.length > 0
          ? <Mermaid chart={claimObservationMermaid(data)} />
          : <p style={emptyS}>— no claim→observation links —</p>}
        <h4 style={h4S}>Span-anchoring — notes → verbatim fragments ({(data.derivations || []).length} edges)</h4>
        <DataTable headers={['note', 'anchored verbatim quote(s)']} rows={Array.from(derivByNote.entries()).map(([note, quotes]) => [
          mono(note), <span style={{ color: T.fgDim }}>{quotes.join('  ·  ')}</span>,
        ])} />
      </>
    ),
  });

  // ⑤ KEfED experiments
  sections.push({
    id: 'kefed', title: '5 · KEfED experiments as node graphs',
    body: (
      <>
        {experiments.map((e) => (
          <div key={e.id} style={{ marginBottom: 14 }}>
            <div style={{ fontFamily: T.serif, fontSize: 15, color: T.fg, margin: '6px 0' }}>{e.name || e.id} {mono(e.id)}</div>
            <Mermaid chart={kefedModelMermaid(e)} caption={signatureCaption(data.signatures?.[e.id])} />
          </div>
        ))}
      </>
    ),
  });

  // ⑧ OOEVV vocabulary
  sections.push({
    id: 'ooevv', title: '6 · OOEVV vocabulary — qualities, value-specs, variables',
    body: (
      <>
        <h4 style={h4S}>Qualities ({qualities.size})</h4>
        <DataTable headers={['quality', 'grounding', '# specs', 'definition']} rows={Array.from(qualities.values()).map((q) => [
          q.name,
          q.curie ? mono(q.curie) : <span style={{ color: T.fgFaint }}>{q.state || 'ungrounded'}</span>,
          q.specs.size, <span style={{ color: T.fgDim }}>{q.definition || '—'}</span>,
        ])} />
        <h4 style={h4S}>Value-specifications ({specs.size})</h4>
        <DataTable headers={['value-spec']} rows={Array.from(specs).map((s) => [s])} />
        <h4 style={h4S}>Variable inventory ({varRows.length})</h4>
        <DataTable headers={['variable', 'role', 'quality', 'value-spec']} rows={varRows.map((v) => [v.name, v.role, v.quality, v.spec])} />
      </>
    ),
  });

  // ⑨ data table
  if ((b.instances || []).length) {
    sections.push({
      id: 'data', title: '7 · Template, instance & the data table',
      body: (
        <>
          {(b.instances || []).map((inst) => (
            <div key={inst.id} style={{ marginBottom: 12 }}>
              <div style={{ fontFamily: T.mono, fontSize: 11, color: T.fgDim, marginBottom: 6 }}>
                {inst.name || inst.id} {inst.template?.name ? `· template: ${inst.template.name}` : ''}
              </div>
              {(inst.data || []).map((row) => (
                <DataTable key={row.id} headers={['variable', 'value', 'role']} rows={(row.cells || []).map((c) => [
                  c.name || c.variable, <b key="v">{c.value}</b>, c.role || '—',
                ])} />
              ))}
            </div>
          ))}
        </>
      ),
    });
  }

  // ⑩ vertical slice
  sections.push({ id: 'slice', title: '8 · The full vertical slice', body: <Mermaid chart={verticalSliceMermaid(data)} /> });

  // ⑪ appendix — entity inventory + id registry
  sections.push({
    id: 'appendix', title: '9 · Appendix — inventory & id registry',
    body: (
      <>
        <h4 style={h4S}>Entity inventory</h4>
        <DataTable headers={['entity type', 'count']} rows={[
          ['scilit-sentence / -section (fragments)', (data.fragments || []).length],
          ['scilit-observation', (b.observations || []).length],
          ['scilit-claim', (b.reported_claims || []).length],
          ['scilit-gap', (b.reported_gaps || []).length],
          ['kefed-model (experiments)', experiments.length],
          ['kefed-instance', (b.instances || []).length],
          ['ooevv-quality', qualities.size],
          ['ooevv-variable', varRows.length],
        ].map((r) => [mono(r[0]), r[1]])} />
        <h4 style={h4S}>Id registry</h4>
        <DataTable headers={['role', 'id']} rows={[
          ['investigation', mono(data.spine?.id)],
          ['bundle', mono(data.bundle_id)],
          ['focal paper', mono(data.paper?.id)],
          ...experiments.map((e) => [`experiment: ${(e.name || '').slice(0, 30)}`, mono(e.id)] as ReactNode[]),
        ]} />
      </>
    ),
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* sticky TOC */}
      <nav style={{
        position: 'sticky', top: 0, zIndex: 5, background: T.panelHi, backdropFilter: 'blur(6px)',
        border: `1px solid ${T.border}`, borderRadius: 4, padding: '10px 14px',
        display: 'flex', flexWrap: 'wrap', gap: 10,
      }}>
        <span style={{ fontFamily: T.mono, fontSize: 10, letterSpacing: '1.2px', textTransform: 'uppercase', color: T.fgDim }}>Curation walkthrough:</span>
        {sections.map((s) => (
          <a key={s.id} href={`#${s.id}`} style={{ fontFamily: T.mono, fontSize: 10.5, color: T.teal, textDecoration: 'none' }}>{s.title.split('·').pop()?.trim()}</a>
        ))}
      </nav>
      {sections.map((s) => (
        <section key={s.id} id={s.id} style={{ scrollMarginTop: 60 }}>
          <Panel title={s.title}>{s.body}</Panel>
        </section>
      ))}
    </div>
  );
}

const h4S: React.CSSProperties = { fontFamily: T.mono, fontSize: 11, fontWeight: 600, color: T.fgDim, textTransform: 'uppercase', letterSpacing: '0.6px', margin: '10px 0 4px' };
const emptyS: React.CSSProperties = { fontFamily: T.mono, fontSize: 11, color: T.fgFaint, margin: 0 };
