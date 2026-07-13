'use client';

// KEfED protocol-graph renderer, styled after the original OOEVV/KEfED design elements:
// a vertical chain of process steps; independent variables (parameters) enter from the LEFT as
// labelled inputs feeding their step; a measurement is shown as the terminal data-grid; the
// generic quality + specificity (parameter -> entity) are made explicit. Hierarchy is nested.

import Link from 'next/link';
import { T } from './tokens';
import type { ExperimentGraph, OoevvProcess, OoevvVarBrief } from '@/lib/scientific-literature';

/** Deep-link an OOEVV vocabulary term (quality / entity) to the ontology search. */
function ooevvHref(term: string): string {
  return `/scientific-literature/ontology?q=${encodeURIComponent(term)}`;
}

const TYPE_STYLE: Record<string, { bg: string; border: string; radius: number; label: string }> = {
  'material-processing': { bg: 'rgba(91,138,184,0.10)', border: T.blue, radius: 6, label: 'material' },
  'assay': { bg: 'rgba(90,173,175,0.12)', border: T.teal, radius: 22, label: 'assay' },
  'data-transformation': { bg: 'rgba(184,200,74,0.10)', border: T.olive, radius: 6, label: 'compute' },
};

function ParamInput({ p }: { p: OoevvVarBrief }) {
  const vals = p.scale?.values?.length ? ` = [${p.scale.values.join(' | ')}]` : '';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'flex-end' }}>
      <div style={{ textAlign: 'right', fontFamily: T.mono, fontSize: 10.5, color: T.fgDim, maxWidth: 230 }}>
        <span style={{ color: T.fg }} title={p.quality?.definition || ''}>{p.name}</span>
        <span style={{ color: T.fgFaint }}>{vals}</span>
        {p.target_entity && (
          <Link href={ooevvHref(p.target_entity.name || '')} title={p.target_entity.definition || 'OOEVV entity — open in ontology'}
            style={{ color: T.rust, textDecoration: 'none' }}> → {p.target_entity.name}</Link>
        )}
      </div>
      {/* the little stacked "value bar" from the KEfED figures */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        {[0, 1, 2].map((i) => (
          <span key={i} style={{ width: 14, height: 4, background: p.target_entity ? T.rust : T.blue, opacity: 0.55, borderRadius: 1 }} />
        ))}
      </div>
      <span style={{ color: T.fgFaint }}>→</span>
    </div>
  );
}

function MeasurementGrid({ m }: { m: OoevvVarBrief }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span style={{ color: T.fgFaint }}>→</span>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 10px)', gridTemplateRows: 'repeat(3, 10px)', gap: 1.5 }}>
        {Array.from({ length: 9 }).map((_, i) => (
          <span key={i} style={{ background: T.tealDim, border: `1px solid ${T.border}` }} />
        ))}
      </div>
      <div style={{ fontFamily: T.mono, fontSize: 11 }}>
        <div style={{ color: T.fg }}>{m.name}</div>
        <div style={{ color: T.teal }} title={m.quality?.definition || ''}>
          [{m.quality?.quality
            ? <Link href={ooevvHref(m.quality.quality)} style={{ color: T.teal, textDecoration: 'none' }} title="OOEVV quality — open in ontology">{m.quality.quality}</Link>
            : '?'}]{m.scale?.type ? ` · ${m.scale.type}${m.scale.unit ? ` (${m.scale.unit})` : ''}` : ''}
        </div>
      </div>
    </div>
  );
}

function ProcessRow({ p, depth }: { p: OoevvProcess; depth: number }) {
  const st = TYPE_STYLE[p.type || ''] || TYPE_STYLE['material-processing'];
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginLeft: depth * 28 }}>
      {/* left: parameter inputs */}
      <div style={{ flex: '0 0 280px', display: 'flex', flexDirection: 'column', gap: 4 }}>
        {(p.parameters || []).map((pm) => <ParamInput key={pm.id} p={pm} />)}
      </div>
      {/* center: the process node */}
      <div style={{ flex: '0 0 220px' }}>
        <div title={p.definition || ''} style={{
          background: st.bg, border: `1.5px solid ${st.border}`, borderRadius: st.radius,
          padding: '10px 14px', textAlign: 'center',
        }}>
          <div style={{ fontFamily: T.sans, fontSize: 12.5, color: T.fg }}>{p.name}</div>
          <div style={{ fontFamily: T.mono, fontSize: 9, color: st.border, textTransform: 'uppercase', letterSpacing: 0.5 }}>{st.label}</div>
        </div>
        {(p.inputs?.length || p.outputs?.length) ? (
          <div style={{ fontFamily: T.mono, fontSize: 9.5, color: T.fgFaint, textAlign: 'center', marginTop: 3 }}>
            {p.inputs?.length ? `in: ${p.inputs.join(', ')}` : ''}{p.inputs?.length && p.outputs?.length ? ' · ' : ''}{p.outputs?.length ? `out: ${p.outputs.join(', ')}` : ''}
          </div>
        ) : null}
      </div>
      {/* right: measurements (terminal data grid) */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
        {(p.measurements || []).map((m) => <MeasurementGrid key={m.id} m={m} />)}
      </div>
    </div>
  );
}

export function KefedProtocolGraph({ exp }: { exp: ExperimentGraph }) {
  const procs = exp.experiment?.processes || [];
  const childrenOf = (id: string) => procs.filter((p) => p.parent === id);
  const top = procs.filter((p) => !p.parent);
  // vertical order: material-processing first, then assays/compute; measurement-producing steps last
  const rank = (p: OoevvProcess) =>
    (p.measurements?.length ? 3 : 0) + (p.type === 'material-processing' ? 0 : p.type === 'assay' ? 1 : 2) * 0.1;
  top.sort((a, b) => rank(a) - rank(b));

  const rows: Array<{ p: OoevvProcess; depth: number }> = [];
  const walk = (p: OoevvProcess, depth: number) => {
    rows.push({ p, depth });
    childrenOf(p.id).forEach((c) => walk(c, depth + 1));
  };
  top.forEach((p) => walk(p, 0));

  if (!procs.length) return null;
  return (
    <div style={{ border: `1px solid ${T.border}`, borderRadius: 8, padding: '14px 16px', marginBottom: 12, background: T.bgRaised }}>
      <div style={{ fontFamily: T.serif, fontSize: 14, color: T.fg, marginBottom: 12 }}>{exp.name || exp.id}</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
        {rows.map((r, i) => (
          <div key={r.p.id}>
            <ProcessRow p={r.p} depth={r.depth} />
            {i < rows.length - 1 && (
              <div style={{ marginLeft: 280 + 110 + r.depth * 28, height: 14, borderLeft: `2px solid ${T.borderDim}`, width: 0 }} />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
