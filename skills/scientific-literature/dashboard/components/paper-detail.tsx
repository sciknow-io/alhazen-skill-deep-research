'use client';

import { useState, useEffect } from 'react';
import { T, FACETS, facetColor } from './tokens';
import { BackNav, HeaderStrip, Panel, FacetBadge, MarkdownContent } from './atoms';
import { Shell, Loading, ErrorBox } from './corpus-detail';
import type { PaperDetail as PaperDetailData } from '@/lib/scientific-literature';

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
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`/api/scientific-literature/paper/${id}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(`API returned ${r.status}`)))
      .then((json) => {
        if (json.error || json.success === false) setError(json.error || 'Paper not found');
        else setData(json);
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, [id]);

  const paper = data?.paper;
  const facetTags = data ? parseFacetTags(data.keywords || []) : [];
  const doi = paper?.doi;

  return (
    <Shell>
      <BackNav href="/scientific-literature" label="Corpora" />
      {loading && <Loading />}
      {error && <ErrorBox message={error} />}
      {paper && (
        <>
          <HeaderStrip
            typeChip={{ short: 'PAPER', color: T.blue, icon: 'doc' }}
            title={paper.name || paper.id}
            kvPairs={[
              { label: 'year', value: paper.year },
              { label: 'journal', value: paper.journal },
              { label: 'pmid', value: paper.pmid },
              { label: 'doi', value: doi },
            ]}
          />

          {facetTags.length > 0 && (
            <Panel title="Facets">
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {facetTags.map(({ facet, value }) => (
                  <FacetBadge key={`${facet}:${value}`} facet={facet} value={value} color={facetColor(facet, value)} />
                ))}
              </div>
            </Panel>
          )}

          {doi && (
            <a
              href={`https://doi.org/${doi}`}
              target="_blank"
              rel="noopener noreferrer"
              style={{ fontFamily: T.mono, fontSize: 12, color: T.teal, textDecoration: 'underline' }}
            >https://doi.org/{doi}</a>
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
        </>
      )}
    </Shell>
  );
}
