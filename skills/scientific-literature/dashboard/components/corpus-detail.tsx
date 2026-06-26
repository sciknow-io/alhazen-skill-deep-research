'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { T } from './tokens';
import { BackNav, HeaderStrip, Icon, TypeChip } from './atoms';
import type { Corpus, Paper } from '@/lib/scientific-literature';

interface CorpusResponse {
  corpus: Corpus | null;
  papers: Paper[];
  count: number;
  error?: string;
}

export function CorpusDetail({ id }: { id: string }) {
  const [data, setData] = useState<CorpusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`/api/scientific-literature/corpus/${id}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(`API returned ${r.status}`)))
      .then((json) => {
        if (json.error) setError(json.error);
        else setData(json);
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, [id]);

  return (
    <Shell>
      <BackNav href="/scientific-literature" label="Corpora" />
      {loading && <Loading />}
      {error && <ErrorBox message={error} />}
      {data && (
        <>
          <HeaderStrip
            typeChip={{ short: 'CORPUS', color: T.teal, icon: 'folder' }}
            title={data.corpus?.name || id}
            description={data.corpus?.description}
            kvPairs={[{ label: 'papers', value: data.count }]}
            action={
              <Link
                href={`/scientific-literature/map?collection=${encodeURIComponent(id)}`}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 6,
                  fontFamily: T.mono, fontSize: 11, color: T.teal, textDecoration: 'none',
                  border: `1px solid ${T.borderHi}`, borderRadius: 3, padding: '4px 10px',
                }}
              >
                <Icon name="map" size={13} color={T.teal} /> open in map
              </Link>
            }
          />

          <div style={{
            background: T.panel,
            border: `1px solid ${T.borderDim}`,
            borderRadius: 4,
            overflow: 'hidden',
          }}>
            {data.papers.map((p) => (
              <Link
                key={p.id}
                href={`/scientific-literature/paper/${p.id}`}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '52px 1fr auto',
                  gap: 14,
                  alignItems: 'center',
                  padding: '9px 14px',
                  borderTop: `1px solid ${T.borderDim}`,
                  textDecoration: 'none',
                  color: 'inherit',
                }}
                onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(90,173,175,0.06)'; }}
                onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
              >
                <span style={{ fontFamily: T.mono, fontSize: 11, color: T.fgFaint }}>{p.year ?? '—'}</span>
                <span style={{ fontSize: 13, color: T.fg, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.name || p.id}</span>
                {p.doi && <span style={{ fontFamily: T.mono, fontSize: 10, color: T.fgFaint }}>{p.doi}</span>}
              </Link>
            ))}
            {data.papers.length === 0 && (
              <div style={{ padding: '16px', fontFamily: T.mono, fontSize: 11, color: T.fgFaint }}>No papers in this corpus.</div>
            )}
          </div>
        </>
      )}
    </Shell>
  );
}

// Shared layout/state helpers (used across scilit detail components)

export function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ minHeight: '100vh', background: T.bg, color: T.fg, fontFamily: T.sans }}>
      <main style={{ maxWidth: 1100, margin: '0 auto', padding: '24px', display: 'flex', flexDirection: 'column', gap: 18 }}>
        {children}
      </main>
    </div>
  );
}

export function Loading() {
  return <span style={{ fontFamily: T.mono, fontSize: 11, color: T.fgFaint }}>Loading…</span>;
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div style={{
      background: 'rgba(200,80,80,0.1)', color: '#e05555', padding: '12px 16px',
      borderRadius: 4, border: '1px solid rgba(200,80,80,0.2)',
    }}>
      <strong style={{ fontFamily: T.mono, fontSize: 10.5, letterSpacing: '0.8px', textTransform: 'uppercase' }}>Error</strong>
      <p style={{ fontSize: 13, marginTop: 4, marginBottom: 0 }}>{message}</p>
    </div>
  );
}
