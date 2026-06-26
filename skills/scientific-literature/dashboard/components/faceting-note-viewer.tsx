'use client';

import { useState, useEffect, useCallback } from 'react';
import { T } from './tokens';
import { BackNav, HeaderStrip, Panel, CodeBlock, Icon, MarkdownContent } from './atoms';
import { Shell, Loading, ErrorBox } from './corpus-detail';
import type { FacetingNoteDetail } from '@/lib/scientific-literature';

export function FacetingNoteViewer({ id }: { id: string }) {
  const [data, setData] = useState<FacetingNoteDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [runMsg, setRunMsg] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    fetch(`/api/scientific-literature/faceting-note/${id}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(`API returned ${r.status}`)))
      .then((json) => {
        if (json.error || json.success === false) setError(json.error || 'Note not found');
        else setData(json);
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const runPipeline = useCallback(async () => {
    setRunning(true);
    setRunMsg(null);
    try {
      const res = await fetch(`/api/scientific-literature/faceting-note/${id}/run`, { method: 'POST' });
      const json = await res.json();
      if (json.error || json.success === false) {
        setRunMsg(`Error: ${json.error || 'run failed'}`);
      } else {
        const written = Object.keys(json.outputs_written || {}).join(', ') || 'none';
        setRunMsg(`Ran. Outputs written: ${written}`);
        load();
      }
    } catch (err) {
      setRunMsg(`Error: ${String(err)}`);
    } finally {
      setRunning(false);
    }
  }, [id, load]);

  const configStr = data?.config != null ? JSON.stringify(data.config, null, 2) : '';

  return (
    <Shell>
      <BackNav href="/scientific-literature" label="Corpora" />
      {loading && !data && <Loading />}
      {error && <ErrorBox message={error} />}
      {data && (
        <>
          <HeaderStrip
            typeChip={{ short: 'PIPELINE', color: T.olive, icon: 'bar-chart' }}
            context={data.note_id}
            title={data.name || data.note_id}
            action={
              <button
                onClick={runPipeline}
                disabled={running}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 6,
                  fontFamily: T.mono, fontSize: 11, letterSpacing: '0.6px',
                  color: running ? T.fgFaint : T.bg,
                  background: running ? 'transparent' : T.olive,
                  border: `1px solid ${T.olive}`, borderRadius: 3, padding: '5px 12px',
                  cursor: running ? 'default' : 'pointer',
                }}
              >
                <Icon name={running ? 'refresh' : 'play'} size={12} color={running ? T.fgFaint : T.bg} />
                {running ? 'running…' : 'run pipeline'}
              </button>
            }
          />

          {runMsg && (
            <div style={{
              fontFamily: T.mono, fontSize: 11, color: runMsg.startsWith('Error') ? '#e05555' : T.teal,
              background: T.panel, border: `1px solid ${T.borderDim}`, borderRadius: 4, padding: '8px 12px',
            }}>{runMsg}</div>
          )}

          {data.content && (
            <Panel title="Cross-tabulation">
              <MarkdownContent content={data.content} />
            </Panel>
          )}

          {data.script && (
            <Panel title="Hamilton script">
              <CodeBlock code={data.script} />
            </Panel>
          )}

          {configStr && (
            <Panel title="Config">
              <CodeBlock code={configStr} maxHeight={320} />
            </Panel>
          )}
        </>
      )}
    </Shell>
  );
}
