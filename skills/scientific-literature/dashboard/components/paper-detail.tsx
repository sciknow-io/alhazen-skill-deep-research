'use client';

import { useState, useEffect } from 'react';
import { T, FACETS, facetColor } from './tokens';
import { BackNav, TypeChip, Panel, FacetBadge, MarkdownContent } from './atoms';
import { Shell, Loading, ErrorBox } from './corpus-detail';
import { PaperCuration } from './paper-curation';
import { withDb } from './db';
import type { PaperDetail as PaperDetailData, PaperCurationDetail, Paper } from '@/lib/scientific-literature';

/** Standard academic citation header: Authors (year). Title. Journal Vol(Issue):Pages. doi. */
function CitationHeader({ paper }: { paper: Paper }) {
  const authors = paper.authors ? paper.authors.split(';').map((s) => s.trim()).filter(Boolean) : [];
  const authorStr = authors.length
    ? (authors.length > 6 ? `${authors.slice(0, 6).join(', ')}, et al.` : authors.join(', '))
    : null;
  // journal locator: "Vol(Issue):Pages", degrading gracefully as pieces are missing
  const locator = [
    paper.volume ? `${paper.volume}${paper.issue ? `(${paper.issue})` : ''}` : '',
    paper.pages || '',
  ].filter(Boolean).join(':');

  return (
    <header style={{
      background: T.bgRaised, border: `1px solid ${T.border}`, borderRadius: 4,
      padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 10,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <TypeChip short="PAPER" color={T.blue} icon="doc" />
        {paper.pmid && <span style={{ fontFamily: T.mono, fontSize: 11, color: T.fgFaint }}>PMID {paper.pmid}</span>}
      </div>

      {authorStr && (
        <div style={{ fontSize: 13.5, color: T.fgDim, lineHeight: 1.5 }}>
          {authorStr}{paper.year ? ` (${paper.year})` : ''}
        </div>
      )}

      <h1 style={{
        margin: 0, fontFamily: T.serif, fontSize: 26, lineHeight: 1.2, fontWeight: 400,
        color: T.fg, letterSpacing: '-0.3px',
      }}>{paper.name || paper.id}</h1>

      {(paper.journal || locator || (!authorStr && paper.year)) && (
        <div style={{ fontSize: 13, color: T.fgDim }}>
          {paper.journal && <span style={{ fontStyle: 'italic' }}>{paper.journal}</span>}
          {locator && <span> {locator}</span>}
          {!authorStr && paper.year ? <span> ({paper.year})</span> : null}
        </div>
      )}

      {paper.doi && (
        <a href={`https://doi.org/${paper.doi}`} target="_blank" rel="noopener noreferrer"
          style={{ fontFamily: T.mono, fontSize: 12, color: T.teal, textDecoration: 'underline', textUnderlineOffset: 2 }}
        >doi:{paper.doi}</a>
      )}
    </header>
  );
}

/** Split a "<facet>:<value>" keyword into [facet, value] when facet is one of the 8. */
function parseFacetTags(keywords: string[]): Array<{ facet: string; value: string }> {
  const out: Array<{ facet: string; value: string }> = [];
  for (const kw of keywords) {
    const idx = kw.indexOf(':');
    if (idx <= 0) continue;
    const facet = kw.slice(0, idx);
    const value = kw.slice(idx + 1);
    if ((FACETS as readonly string[]).includes(facet)) out.push({ facet, value });
  }
  return out;
}

export function PaperDetail({ id }: { id: string }) {
  const [data, setData] = useState<PaperDetailData | null>(null);
  const [curation, setCuration] = useState<PaperCurationDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(withDb(`/api/scientific-literature/paper/${id}`))
      .then((r) => (r.ok ? r.json() : Promise.reject(`API returned ${r.status}`)))
      .then((json) => {
        if (json.error || json.success === false) setError(json.error || 'Paper not found');
        else setData(json);
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
    // progressive: the heavier curation walkthrough loads after the header
    fetch(withDb(`/api/scientific-literature/paper/${id}/curation`))
      .then((r) => (r.ok ? r.json() : null))
      .then((json) => { if (json && json.hasCuration) setCuration(json); })
      .catch(() => { /* no curation — bibliographic view only */ });
  }, [id]);

  const paper = data?.paper;
  const facetTags = data ? parseFacetTags(data.keywords || []) : [];

  return (
    <Shell>
      <BackNav href="/scientific-literature" label="Corpora" />
      {loading && <Loading />}
      {error && <ErrorBox message={error} />}
      {paper && (
        <>
          <CitationHeader paper={paper} />

          {facetTags.length > 0 && (
            <Panel title="Facets">
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {facetTags.map(({ facet, value }) => (
                  <FacetBadge key={`${facet}:${value}`} facet={facet} value={value} color={facetColor(facet, value)} />
                ))}
              </div>
            </Panel>
          )}

          {paper['abstract-text'] && (
            <Panel title="Abstract">
              <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.6, color: T.fgDim }}>{paper['abstract-text']}</p>
            </Panel>
          )}

          {data && data.notes.length > 0 && (
            <Panel title={`Notes (${data.notes.length})`}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                {data.notes.map((n) => (
                  <div key={n.id}>
                    {n.name && <div style={{ fontFamily: T.mono, fontSize: 11, color: T.fgDim, marginBottom: 4 }}>{n.name}</div>}
                    {n.content && <MarkdownContent content={n.content} />}
                  </div>
                ))}
              </div>
            </Panel>
          )}

          {curation && <PaperCuration data={curation} />}
        </>
      )}
    </Shell>
  );
}
