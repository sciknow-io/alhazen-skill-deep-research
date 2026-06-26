'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { T } from './tokens';
import { BackNav, HeaderStrip, Panel, Icon, MarkdownContent } from './atoms';
import { Shell, Loading, ErrorBox } from './corpus-detail';
import type { InvestigationDetail, InvestigationPhase, ClaimNode, ImpactNode, InvestigationPaperRef } from '@/lib/scientific-literature';

const CLAIM_TIER_COLOR: Record<string, string> = {
  primary: T.rust,
  secondary: T.olive,
  peripheral: T.fgFaint,
};

// Canonical lifecycle order; the timeline always renders all five rows so that
// not-yet-recorded phases read as "pending" placeholders.
const PHASES: Array<{ key: string; label: string }> = [
  { key: 'discovery', label: 'Discovery' },
  { key: 'ingest', label: 'Ingest' },
  { key: 'sensemaking', label: 'Sensemaking' },
  { key: 'analysis', label: 'Analysis' },
  { key: 'report', label: 'Report' },
];

function statusColor(status?: string): string {
  switch (status) {
    case 'complete':
      return T.teal;
    case 'report':
    case 'analysis':
      return T.olive;
    case 'scoping':
      return T.fgFaint;
    default:
      return T.blue;
  }
}

export function InvestigationDetailView({ id }: { id: string }) {
  const [data, setData] = useState<InvestigationDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`/api/scientific-literature/investigation/${id}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(`API returned ${r.status}`)))
      .then((json) => {
        if (json.error || json.success === false) setError(json.error || 'Investigation not found');
        else setData(json);
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, [id]);

  const byPhase: Record<string, InvestigationPhase> = {};
  for (const p of data?.phases || []) byPhase[p.phase] = p;

  const isDeepDive = data?.type === 'deep-dive';

  return (
    <Shell>
      <BackNav href="/scientific-literature" label="Corpora" />
      {loading && !data && <Loading />}
      {error && <ErrorBox message={error} />}
      {data && (
        <>
          <HeaderStrip
            typeChip={
              isDeepDive
                ? { short: 'DEEP DIVE', color: T.rust, icon: 'search' }
                : { short: 'INVESTIGATION', color: T.rust, icon: 'search' }
            }
            context={data.id}
            title={data.name || data.id}
            kvPairs={[
              { label: 'type', value: data.type || 'corpus' },
              { label: 'status', value: data.status || '—', accent: statusColor(data.status) },
              { label: 'started', value: data['created-at']?.slice(0, 10) || '—' },
              { label: 'phases', value: `${data.phases.length}/5` },
            ]}
            action={
              isDeepDive && data.focal_paper ? (
                <Link
                  href={`/scientific-literature/paper/${data.focal_paper.id}`}
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: 6,
                    fontFamily: T.mono, fontSize: 11, color: T.rust, textDecoration: 'none',
                    border: `1px solid ${T.borderHi}`, borderRadius: 3, padding: '4px 10px',
                  }}
                >
                  <Icon name="doc" size={13} color={T.rust} /> {data.focal_paper.name || data.focal_paper.id}
                </Link>
              ) : data.corpus ? (
                <Link
                  href={`/scientific-literature/corpus/${data.corpus.id}`}
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: 6,
                    fontFamily: T.mono, fontSize: 11, color: T.teal, textDecoration: 'none',
                    border: `1px solid ${T.borderHi}`, borderRadius: 3, padding: '4px 10px',
                  }}
                >
                  <Icon name="folder" size={13} color={T.teal} /> {data.corpus.name || data.corpus.id}
                </Link>
              ) : undefined
            }
          />

          {data.purpose && (
            <Panel title="Purpose">
              <MarkdownContent content={data.purpose} />
            </Panel>
          )}

          {isDeepDive && <ClaimsPanel claims={data.claims || []} />}
          {isDeepDive && <CitationImpactPanel impacts={data.citation_impacts || []} />}

          <PapersPanel papers={data.papers || []} collection={data.collection} />

          <Panel title="Lifecycle">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
              {PHASES.map(({ key, label }, i) => {
                const phase = byPhase[key];
                const done = !!phase;
                return (
                  <div
                    key={key}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '24px 1fr',
                      gap: 14,
                      paddingBottom: i < PHASES.length - 1 ? 18 : 0,
                    }}
                  >
                    {/* Timeline rail + node */}
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                      <div style={{
                        width: 14, height: 14, borderRadius: '50%',
                        background: done ? T.rust : 'transparent',
                        border: `1.5px solid ${done ? T.rust : T.borderHi}`,
                        marginTop: 2, flexShrink: 0,
                      }} />
                      {i < PHASES.length - 1 && (
                        <div style={{ width: 1.5, flex: 1, minHeight: 24, background: T.borderDim, marginTop: 4 }} />
                      )}
                    </div>

                    {/* Phase content */}
                    <div style={{ minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
                        <span style={{
                          fontFamily: T.mono, fontSize: 11, fontWeight: 600,
                          letterSpacing: '1px', textTransform: 'uppercase',
                          color: done ? T.fg : T.fgFaint,
                        }}>{label}</span>
                        <span style={{ fontFamily: T.mono, fontSize: 10, color: T.fgFaint }}>
                          {done ? (phase['created-at']?.slice(0, 10) || '') : 'pending'}
                        </span>
                      </div>

                      {done && phase.content && (
                        <div style={{
                          marginTop: 8, padding: '10px 14px',
                          background: T.panel, border: `1px solid ${T.borderDim}`, borderRadius: 4,
                        }}>
                          <MarkdownContent content={phase.content} />
                        </div>
                      )}

                      {key === 'analysis' && done && (phase.faceting_notes?.length ?? 0) > 0 && (
                        <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
                          {phase.faceting_notes!.map((fn) => (
                            <Link
                              key={fn.id}
                              href={`/scientific-literature/faceting-note/${fn.id}`}
                              style={{
                                display: 'inline-flex', alignItems: 'center', gap: 8,
                                fontFamily: T.mono, fontSize: 11.5, color: T.olive, textDecoration: 'none',
                                border: `1px solid ${T.oliveDim}`, borderRadius: 3, padding: '6px 10px',
                                background: T.oliveDim,
                              }}
                            >
                              <Icon name="bar-chart" size={12} color={T.olive} />
                              {fn.name || fn.id}
                            </Link>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </Panel>
        </>
      )}
    </Shell>
  );
}

function PaperLink({ paper, color }: { paper: { id: string; name?: string; doi?: string }; color: string }) {
  return (
    <Link
      href={`/scientific-literature/paper/${paper.id}`}
      style={{
        fontFamily: T.mono, fontSize: 11.5, color, textDecoration: 'none',
        borderBottom: `1px dotted ${color}`,
      }}
    >
      {paper.name || paper.doi || paper.id}
    </Link>
  );
}

function PapersPanel({
  papers,
  collection,
}: {
  papers: InvestigationPaperRef[];
  collection?: { id: string; name?: string; count?: number };
}) {
  if (papers.length === 0 && !collection) return null;
  return (
    <Panel
      title={`Papers (${papers.length})`}
      action={
        collection ? (
          <Link
            href={`/scientific-literature/corpus/${collection.id}`}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              fontFamily: T.mono, fontSize: 11, color: T.teal, textDecoration: 'none',
              border: `1px solid ${T.borderHi}`, borderRadius: 3, padding: '4px 10px',
            }}
          >
            <Icon name="folder" size={13} color={T.teal} /> view as corpus
          </Link>
        ) : undefined
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        {papers.map((p, i) => (
          <Link
            key={p.id}
            href={`/scientific-literature/paper/${p.id}`}
            style={{
              display: 'grid', gridTemplateColumns: '52px 1fr auto', gap: 14, alignItems: 'center',
              padding: '9px 4px', borderTop: i === 0 ? 'none' : `1px solid ${T.borderDim}`,
              textDecoration: 'none', color: 'inherit',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(90,173,175,0.06)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
          >
            <span style={{ fontFamily: T.mono, fontSize: 11, color: T.fgFaint }}>{p.year ?? '—'}</span>
            <span style={{ fontSize: 13, color: T.fg, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.name || p.id}</span>
            {p.doi && <span style={{ fontFamily: T.mono, fontSize: 10, color: T.fgFaint }}>{p.doi}</span>}
          </Link>
        ))}
        {papers.length === 0 && (
          <span style={{ fontFamily: T.mono, fontSize: 11, color: T.fgFaint }}>No papers linked yet.</span>
        )}
      </div>
    </Panel>
  );
}

function ClaimsPanel({ claims }: { claims: ClaimNode[] }) {
  if (claims.length === 0) return null;
  const counts: Record<string, number> = {};
  for (const c of claims) counts[c.type || '?'] = (counts[c.type || '?'] || 0) + 1;
  const summary = Object.entries(counts).map(([k, v]) => `${v} ${k}`).join(' · ');
  return (
    <Panel title={`Claims & Evidence (${summary})`}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {claims.map((cl) => {
          const tier = CLAIM_TIER_COLOR[cl.type || ''] || T.blue;
          return (
            <div key={cl.id} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                <span style={{
                  fontFamily: T.mono, fontSize: 9.5, fontWeight: 600, letterSpacing: '0.8px',
                  textTransform: 'uppercase', color: tier, border: `1px solid ${tier}`,
                  borderRadius: 3, padding: '1px 6px', flexShrink: 0,
                }}>{cl.type || '?'}</span>
                <span style={{ fontSize: 13.5, color: T.fg, lineHeight: 1.5 }}>{cl.statement}</span>
              </div>
              {(cl.evidence?.length ?? 0) > 0 && (
                <div style={{ marginLeft: 16, display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {cl.evidence!.map((ev) => (
                    <div key={ev.id} style={{
                      padding: '8px 12px', background: T.panel,
                      border: `1px solid ${T.borderDim}`, borderRadius: 4,
                    }}>
                      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
                        <span style={{
                          fontFamily: T.mono, fontSize: 9.5, color: T.teal,
                          border: `1px solid ${T.borderHi}`, borderRadius: 3, padding: '1px 6px',
                        }}>{ev.evidence_type || '?'}</span>
                        {ev.source_paper
                          ? <PaperLink paper={ev.source_paper} color={T.teal} />
                          : ev.source_url
                            ? <a href={ev.source_url} style={{ fontFamily: T.mono, fontSize: 11.5, color: T.teal }}>{ev.source_url}</a>
                            : <span style={{ fontFamily: T.mono, fontSize: 11, color: T.fgFaint }}>no source</span>}
                      </div>
                      {ev.experimental_design && (
                        <div style={{ fontSize: 12, color: T.fgDim, marginTop: 4 }}>
                          <strong style={{ color: T.fg }}>Design:</strong> {ev.experimental_design}
                        </div>
                      )}
                      {ev.data_summary && (
                        <div style={{ fontSize: 12, color: T.fgDim, marginTop: 4 }}>
                          <strong style={{ color: T.fg }}>Data:</strong> {ev.data_summary}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

function CitationImpactPanel({ impacts }: { impacts: ImpactNode[] }) {
  if (impacts.length === 0) return null;
  const counts: Record<string, number> = {};
  for (const im of impacts) counts[im.impact_type || '?'] = (counts[im.impact_type || '?'] || 0) + 1;
  const summary = Object.entries(counts).map(([k, v]) => `${v} ${k}`).join(' · ');
  return (
    <Panel title={`Citation Impact (${impacts.length} citing · ${summary})`}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {impacts.map((im) => (
          <div key={im.id} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
              <span style={{
                fontFamily: T.mono, fontSize: 9.5, fontWeight: 600, letterSpacing: '0.8px',
                textTransform: 'uppercase', color: T.olive, border: `1px solid ${T.oliveDim}`,
                borderRadius: 3, padding: '1px 6px',
              }}>{im.impact_type || '?'}</span>
              {im.citing_paper && <PaperLink paper={im.citing_paper} color={T.olive} />}
            </div>
            {im.impact_summary && (
              <span style={{ fontSize: 12.5, color: T.fgDim, lineHeight: 1.5, marginLeft: 2 }}>{im.impact_summary}</span>
            )}
          </div>
        ))}
      </div>
    </Panel>
  );
}
