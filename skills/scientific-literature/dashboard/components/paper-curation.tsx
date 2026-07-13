'use client';

// Claim-centric reading of a paper's sensemaking curation. One section per reported claim,
// gathering everything that stands behind it: the claim statement, the rhetorical observations
// that ground it (each shown with its verbatim fragment quotes), and — grouped heuristically by
// observation-name prefix (rhetorical "OF3A" ⊂ datum "OF3A frag2 …") — the KEfED experiment
// designs (rendered as JS protocol graphs, not mermaid) and their data as pivot tables.
// Instances that match no claim fall into a trailing "Additional evidence models" section so
// nothing is silently dropped. The sensemaking linter sits in a collapsible box up top.

import { type ReactNode, useState, useEffect } from 'react';
import Link from 'next/link';
import { T } from './tokens';
import { Panel } from './atoms';
import { KefedProtocolGraph } from './kefed-graph';
import { Spreadsheet } from './kefed-instance';
import { withDb } from './db';
import type {
  PaperCurationDetail, BundleDetail, ReportedClaimNode, ObservationNode,
  InstanceDetail, SensemakingCheck, InvestigationPaperRef,
} from '@/lib/scientific-literature';

// ─── styles ─────────────────────────────────────────────────────
const subheadS: React.CSSProperties = { fontFamily: T.mono, fontSize: 10, fontWeight: 600, color: T.fgDim, textTransform: 'uppercase', letterSpacing: '0.7px', margin: '0 0 6px' };
const tagS: React.CSSProperties = { fontFamily: T.mono, fontSize: 9.5, color: T.fgFaint, textTransform: 'uppercase', letterSpacing: '0.5px', border: `1px solid ${T.borderDim}`, borderRadius: 3, padding: '1px 6px' };

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

// ─── one observation + its verbatim fragments ───────────────────
function ObservationBlock({ obs, quotes }: { obs: ObservationNode; quotes: Array<{ frag: string; quote: string }> }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
        {obs.name && <span style={{ fontFamily: T.mono, fontSize: 11, color: T.olive }}>{obs.name}</span>}
        {obs.knowledge_level && <span style={tagS}>{obs.knowledge_level}</span>}
        {obs.bio_scale && <span style={tagS}>{obs.bio_scale}</span>}
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

// ─── one KEfED instance: template-design diagram + pivot data table ──
function InstanceBlock({ inst }: { inst: InstanceDetail }) {
  const tpl = inst.template_detail;
  return (
    <div style={{ border: `1px solid ${T.borderDim}`, borderRadius: 6, padding: '12px 14px', background: T.bgRaised, marginBottom: 12 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ fontFamily: T.serif, fontSize: 14.5, color: T.fg }}>{inst.name || inst.id}</span>
        {inst.template?.id && (
          <Link
            href={`/scientific-literature/template/${encodeURIComponent(inst.template.id)}`}
            title={tpl?.definition || 'reusable KEfED experiment design'}
            style={{ fontFamily: T.mono, fontSize: 10.5, color: T.olive, textDecoration: 'none', whiteSpace: 'nowrap' }}
          >KEfED template: {inst.template.name || inst.template.id} →</Link>
        )}
      </div>

      {tpl?.graph && (tpl.graph.processes || []).length > 0 && (
        <div style={{ marginTop: 10 }}>
          <div style={subheadS}>KEfED template design</div>
          <KefedProtocolGraph exp={{ id: tpl.id, name: tpl.name, experiment: tpl.graph }} />
        </div>
      )}

      <div style={{ marginTop: 10 }}>
        <div style={subheadS}>Data table</div>
        <Spreadsheet tpl={tpl} data={inst.data || []} />
      </div>
    </div>
  );
}

// ─── cite chip (cross-paper hinge) ──────────────────────────────
function CiteChip({ ref }: { ref: InvestigationPaperRef }) {
  const label = ref.name || ref.id;
  if (ref.id) {
    return <Link href={`/scientific-literature/paper/${encodeURIComponent(ref.id)}`}
      style={{ fontFamily: T.mono, fontSize: 10.5, color: T.teal, textDecoration: 'none' }}>{label}</Link>;
  }
  return <span style={{ fontFamily: T.mono, fontSize: 10.5, color: T.fgDim }}>{label}</span>;
}

// ─── word-boundary prefix match (rhetorical obs name ⊂ datum obs name) ──
function nameMatches(datumName: string | undefined, obsName: string | undefined): boolean {
  if (!datumName || !obsName) return false;
  if (datumName === obsName) return true;
  if (!datumName.startsWith(obsName)) return false;
  const next = datumName.charAt(obsName.length);
  return next === '' || /[^A-Za-z0-9]/.test(next);
}

// ─── main claim-centric walkthrough ─────────────────────────────
export function PaperCuration({ data }: { data: PaperCurationDetail }) {
  const b = data.bundle || ({} as BundleDetail);
  const claims = b.reported_claims || [];
  const observations = b.observations || [];
  const gaps = b.reported_gaps || [];
  const instances = b.instances || [];

  const obsById = new Map(observations.map((o) => [o.id, o] as const));

  // claim -> observation ids (scilit-claim-observation edges)
  const claimObsIds = new Map<string, string[]>();
  for (const co of data.claim_observations || []) {
    const arr = claimObsIds.get(co.claim) || [];
    arr.push(co.observation);
    claimObsIds.set(co.claim, arr);
  }

  // observation id -> verbatim fragment quotes (alh-derivation: note == observation id)
  const quotesByObs = new Map<string, Array<{ frag: string; quote: string }>>();
  for (const dv of data.derivations || []) {
    if (!dv.quote) continue;
    const arr = quotesByObs.get(dv.note) || [];
    arr.push({ frag: dv.frag, quote: dv.quote });
    quotesByObs.set(dv.note, arr);
  }

  // heuristic grouping: an instance belongs to a claim when any of its datum-row observation
  // names shares a name-prefix with one of the claim's rhetorical observations.
  const matchedInstanceIds = new Set<string>();
  const instancesForClaim = (claimId: string): InstanceDetail[] => {
    const names = (claimObsIds.get(claimId) || [])
      .map((id) => obsById.get(id)?.name)
      .filter(Boolean) as string[];
    if (!names.length) return [];
    const hits = instances.filter((inst) =>
      (inst.data || []).some((r) => names.some((n) => nameMatches(r.observation?.name, n)))
    );
    hits.forEach((i) => matchedInstanceIds.add(i.id));
    return hits;
  };

  // pre-compute so matchedInstanceIds is populated before the leftover bucket is derived
  const claimBlocks = claims.map((c) => ({
    claim: c,
    obs: (claimObsIds.get(c.id) || []).map((id) => obsById.get(id)).filter(Boolean) as ObservationNode[],
    insts: instancesForClaim(c.id),
  }));
  const leftover = instances.filter((i) => !matchedInstanceIds.has(i.id));

  // TOC entries
  const toc: Array<{ id: string; label: string }> = claimBlocks.map((cb, i) => ({
    id: `claim-${i}`, label: `Claim ${i + 1}`,
  }));
  if (leftover.length) toc.push({ id: 'additional', label: 'Additional models' });
  if (gaps.length) toc.push({ id: 'gaps', label: 'Gaps' });

  const claimSection = (cb: typeof claimBlocks[number], i: number): ReactNode => (
    <section key={cb.claim.id} id={`claim-${i}`} style={{ scrollMarginTop: 60 }}>
      <Panel title={`Claim ${i + 1}`} action={<ClaimBadge type={cb.claim.type} />}>
        <p style={{ margin: 0, fontFamily: T.serif, fontSize: 16, lineHeight: 1.55, color: T.fg }}>{cb.claim.statement}</p>
        {cb.claim.cites && cb.claim.cites.length > 0 && (
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'baseline' }}>
            <span style={{ fontFamily: T.mono, fontSize: 9.5, color: T.fgFaint, textTransform: 'uppercase' }}>cites</span>
            {cb.claim.cites.map((c) => <CiteChip key={c.id} ref={c} />)}
          </div>
        )}

        <div>
          <div style={subheadS}>Observations ({cb.obs.length})</div>
          {cb.obs.length
            ? cb.obs.map((o) => <ObservationBlock key={o.id} obs={o} quotes={quotesByObs.get(o.id) || []} />)
            : <span style={{ fontFamily: T.mono, fontSize: 11, color: T.fgFaint }}>— none linked —</span>}
        </div>

        {cb.insts.length > 0 && (
          <div>
            <div style={subheadS}>Evidence — KEfED models &amp; data ({cb.insts.length})</div>
            {cb.insts.map((inst) => <InstanceBlock key={inst.id} inst={inst} />)}
          </div>
        )}
      </Panel>
    </section>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <SensemakingChecksBox paperId={data.paper?.id} />

      {/* sticky claim TOC */}
      {toc.length > 1 && (
        <nav style={{
          position: 'sticky', top: 0, zIndex: 5, background: T.panelHi, backdropFilter: 'blur(6px)',
          border: `1px solid ${T.border}`, borderRadius: 4, padding: '10px 14px',
          display: 'flex', flexWrap: 'wrap', gap: 12,
        }}>
          <span style={{ fontFamily: T.mono, fontSize: 10, letterSpacing: '1.2px', textTransform: 'uppercase', color: T.fgDim }}>Claims:</span>
          {toc.map((t) => (
            <a key={t.id} href={`#${t.id}`} style={{ fontFamily: T.mono, fontSize: 10.5, color: T.teal, textDecoration: 'none' }}>{t.label}</a>
          ))}
        </nav>
      )}

      {claimBlocks.map(claimSection)}

      {/* instances that matched no claim — never silently dropped */}
      {leftover.length > 0 && (
        <section id="additional" style={{ scrollMarginTop: 60 }}>
          <Panel title={`Additional evidence models (${leftover.length})`}>
            <p style={{ margin: '0 0 8px', fontSize: 12.5, color: T.fgDim }}>
              KEfED instances not matched to a specific claim by observation name.
            </p>
            {leftover.map((inst) => <InstanceBlock key={inst.id} inst={inst} />)}
          </Panel>
        </section>
      )}

      {/* stated gaps (open questions the paper names) */}
      {gaps.length > 0 && (
        <section id="gaps" style={{ scrollMarginTop: 60 }}>
          <Panel title={`Gaps (${gaps.length})`}>
            {gaps.map((g) => (
              <div key={g.id} style={{ marginBottom: 8 }}>
                <p style={{ margin: 0, fontSize: 13, color: T.fg }}>{g.name}</p>
                {g.goal && <span style={{ fontFamily: T.mono, fontSize: 10.5, color: T.fgFaint }}>{g.goal}</span>}
              </div>
            ))}
          </Panel>
        </section>
      )}
    </div>
  );
}
