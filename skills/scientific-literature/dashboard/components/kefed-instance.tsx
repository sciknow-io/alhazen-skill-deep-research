'use client';

// KEfED template INSTANCE renderer: the reusable design (template) is shown once with its
// typed slots; the per-paper execution fills those slots with curated entities and carries the
// data as a spreadsheet (independent-variable columns -> the measured dependent value). Each row
// links to its free-text observation (source quote) for provenance/click-through.

import { useState, Fragment } from 'react';
import { T } from './tokens';
import { KefedProtocolGraph } from './kefed-graph';
import type { InstanceDetail, TemplateDetail, DatumRow } from '@/lib/scientific-literature';

function SlotChip({ role, kind, filler }: { role?: string; kind?: string; filler?: string }) {
  const filled = !!filler;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'baseline', gap: 6, padding: '3px 9px', borderRadius: 5,
      border: `1px solid ${filled ? T.rust : T.borderDim}`,
      background: filled ? 'rgba(176,109,84,0.10)' : 'transparent', marginRight: 6, marginBottom: 6,
    }} title={kind ? `kind: ${kind}` : undefined}>
      <span style={{ fontFamily: T.mono, fontSize: 10, color: T.fgDim, textTransform: 'uppercase', letterSpacing: 0.4 }}>{role}</span>
      <span style={{ fontFamily: T.sans, fontSize: 12.5, color: filled ? T.rust : T.fgFaint }}>
        {filler || '⟨unfilled⟩'}
      </span>
    </span>
  );
}

function Spreadsheet({ tpl, data }: { tpl?: TemplateDetail | null; data: DatumRow[] }) {
  const [open, setOpen] = useState<string | null>(null);
  // column order: independents (parameter/constant) first, dependent (measurement) last
  const vars = (tpl?.variables || []).slice().sort((a, b) => {
    const w = (r?: string) => (r === 'measurement' ? 1 : 0);
    return w(a.role) - w(b.role);
  });
  // fall back to columns discovered in the data if the template has no variables
  const cols = vars.length
    ? vars.map((v) => ({ id: v.id, name: v.name, role: v.role, unit: v.scale?.unit, quality: v.quality?.quality }))
    : Array.from(new Map(data.flatMap((r) => r.cells).map((c) => [c.variable, { id: c.variable, name: c.name, role: c.role, unit: undefined, quality: undefined }])).values());

  const cellOf = (row: DatumRow, colId: string) => row.cells.find((c) => c.variable === colId);
  if (!data.length) return <div style={{ fontFamily: T.mono, fontSize: 11, color: T.fgFaint }}>No data rows yet.</div>;

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ borderCollapse: 'collapse', fontFamily: T.mono, fontSize: 11.5 }}>
        <thead>
          <tr>
            {cols.map((c) => (
              <th key={c.id} title={c.quality ? `measures: ${c.quality}` : undefined}
                style={{
                  textAlign: 'left', padding: '5px 10px', borderBottom: `2px solid ${T.border}`,
                  color: c.role === 'measurement' ? T.teal : T.blue, whiteSpace: 'nowrap',
                }}>
                {c.name}{c.unit ? <span style={{ color: T.fgFaint }}> ({c.unit})</span> : null}
                <div style={{ fontSize: 8.5, color: T.fgFaint, textTransform: 'uppercase', letterSpacing: 0.4 }}>
                  {c.role === 'measurement' ? 'dependent' : 'independent'}
                </div>
              </th>
            ))}
            <th style={{ borderBottom: `2px solid ${T.border}`, width: 24 }} />
          </tr>
        </thead>
        <tbody>
          {data.map((row) => {
            const isOpen = open === row.id;
            return (
              <Fragment key={row.id}>
                <tr onClick={() => setOpen(isOpen ? null : row.id)}
                  style={{ cursor: row.observation ? 'pointer' : 'default', background: isOpen ? T.bgRaised : 'transparent' }}>
                  {cols.map((c) => {
                    const cell = cellOf(row, c.id);
                    return (
                      <td key={c.id} style={{
                        padding: '4px 10px', borderBottom: `1px solid ${T.borderDim}`,
                        color: c.role === 'measurement' ? T.fg : T.fgDim,
                        fontWeight: c.role === 'measurement' ? 600 : 400, whiteSpace: 'nowrap',
                      }}>{cell?.value ?? ''}</td>
                    );
                  })}
                  <td style={{ padding: '4px 6px', borderBottom: `1px solid ${T.borderDim}`, color: T.fgFaint, textAlign: 'center' }}>
                    {row.observation ? (isOpen ? '▾' : '▸') : ''}
                  </td>
                </tr>
                {isOpen && row.observation && (
                  <tr>
                    <td colSpan={cols.length + 1} style={{ padding: '6px 10px 10px', background: T.bgRaised, borderBottom: `1px solid ${T.borderDim}` }}>
                      <div style={{ fontFamily: T.sans, fontSize: 12, color: T.fgDim, borderLeft: `2px solid ${T.oliveDim}`, paddingLeft: 8 }}>
                        <span style={{ fontFamily: T.mono, fontSize: 9.5, color: T.fgFaint, textTransform: 'uppercase', marginRight: 6 }}>source</span>
                        {row.observation.content || row.observation.name}
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function KefedInstance({ inst }: { inst: InstanceDetail }) {
  const tpl = inst.template_detail;
  const fillerFor = (role?: string) => inst.bindings?.find((b) => b.role === role)?.entity;
  const [showDesign, setShowDesign] = useState(false);
  return (
    <div style={{ border: `1px solid ${T.border}`, borderRadius: 8, padding: '14px 16px', marginBottom: 14, background: T.bgRaised }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10 }}>
        <div style={{ fontFamily: T.serif, fontSize: 14.5, color: T.fg }}>{inst.name || inst.id}</div>
        {inst.template?.name && (
          <div style={{ fontFamily: T.mono, fontSize: 10.5, color: T.fgDim }}>
            instance of <span style={{ color: T.olive }}>{inst.template.name}</span>
          </div>
        )}
      </div>

      {/* filled slots */}
      <div style={{ marginTop: 10 }}>
        {(tpl?.slots || []).map((s) => (
          <SlotChip key={s.id} role={s.role} kind={s.kind} filler={fillerFor(s.role)} />
        ))}
      </div>

      {/* data spreadsheet: independents -> dependent, click a row for its source quote */}
      <div style={{ marginTop: 10 }}>
        <Spreadsheet tpl={tpl} data={inst.data || []} />
      </div>

      {/* the reusable template design graph, collapsed by default */}
      {tpl?.graph && (tpl.graph.processes || []).length > 0 && (
        <div style={{ marginTop: 10 }}>
          <button onClick={() => setShowDesign(!showDesign)} style={{
            background: 'none', border: 'none', cursor: 'pointer', padding: 0,
            fontFamily: T.mono, fontSize: 10.5, color: T.olive,
          }}>
            {showDesign ? '▾' : '▸'} template design (KEfED protocol graph)
          </button>
          {showDesign && (
            <div style={{ marginTop: 8 }}>
              <KefedProtocolGraph exp={{ id: tpl.id, name: tpl.name, experiment: tpl.graph }} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
