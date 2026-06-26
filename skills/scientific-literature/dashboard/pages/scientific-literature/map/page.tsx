'use client';

import { useState, useEffect, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { T } from '@/components/scientific-literature/tokens';
import { BackNav } from '@/components/scientific-literature/atoms';
import { EmbeddingMap } from '@/components/scientific-literature/embedding-map';
import type { MapData } from '@/lib/scientific-literature';

export default function MapPage() {
  return (
    <Suspense fallback={null}>
      <MapView />
    </Suspense>
  );
}

function MapView() {
  const searchParams = useSearchParams();
  const [data, setData] = useState<MapData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const collections = searchParams.getAll('collection');
    const qs = collections.length > 0
      ? '?' + collections.map((c) => `collection=${encodeURIComponent(c)}`).join('&')
      : '';
    fetch(`/api/scientific-literature/map${qs}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(`API returned ${r.status}`)))
      .then((json) => {
        if (json.error || json.success === false) setError(json.error || 'map failed');
        else setData(json);
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, [searchParams]);

  return (
    <div style={{ height: '100vh', background: T.bg, color: T.fg, fontFamily: T.sans, display: 'flex', flexDirection: 'column' }}>
      <header style={{ borderBottom: `1px solid ${T.borderDim}`, background: T.bgRaised, padding: '14px 24px', display: 'flex', alignItems: 'center', gap: 20 }}>
        <BackNav href="/scientific-literature" label="Corpora" />
        <div>
          <h1 style={{ margin: 0, fontFamily: T.serif, fontSize: 20, fontWeight: 400, color: T.fg }}>Embedding Map</h1>
          <span style={{ fontFamily: T.mono, fontSize: 10.5, color: T.fgDim }}>
            UMAP-2D · HDBSCAN clusters {data ? `· ${data.num_clusters} clusters` : ''}
          </span>
        </div>
      </header>

      <main style={{ flex: 1, minHeight: 0, padding: '16px 24px', display: 'flex', flexDirection: 'column' }}>
        {loading && <span style={{ fontFamily: T.mono, fontSize: 11, color: T.fgFaint }}>Computing projection…</span>}
        {error && (
          <div style={{ background: 'rgba(200,80,80,0.1)', color: '#e05555', padding: '12px 16px', borderRadius: 4, border: '1px solid rgba(200,80,80,0.2)' }}>
            <strong style={{ fontFamily: T.mono, fontSize: 10.5, letterSpacing: '0.8px', textTransform: 'uppercase' }}>Error</strong>
            <p style={{ fontSize: 13, marginTop: 4, marginBottom: 0 }}>{error}</p>
          </div>
        )}
        {data && data.items.length > 0 && <EmbeddingMap items={data.items} />}
        {data && data.items.length === 0 && (
          <span style={{ fontFamily: T.mono, fontSize: 11, color: T.fgFaint }}>No embedded papers found. Embed a corpus first.</span>
        )}
      </main>
    </div>
  );
}
