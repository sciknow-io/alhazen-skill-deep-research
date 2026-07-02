'use client';

import { useEffect, useState } from 'react';
import { T } from './tokens';

// Client-side Mermaid renderer. Diagrams are drawn on a light "card" (matching the
// SIRT3 walkthrough template) so the template's classDef fills + dark text/lines read
// correctly regardless of the dark dashboard chrome.

let _seq = 0;

export function Mermaid({ chart, caption }: { chart: string; caption?: string }) {
  const [svg, setSvg] = useState('');
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const mermaid = (await import('mermaid')).default;
        mermaid.initialize({
          startOnLoad: false,
          theme: 'base',
          securityLevel: 'loose',
          themeVariables: { fontSize: '13px' },
          flowchart: { useMaxWidth: true, htmlLabels: true },
        });
        const id = `mmd_${Date.now()}_${_seq++}`;
        const out = await mermaid.render(id, chart);
        if (!cancelled) { setSvg(out.svg); setErr(null); }
      } catch (e) {
        if (!cancelled) setErr(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => { cancelled = true; };
  }, [chart]);

  return (
    <div style={{ background: '#fbfaf8', border: `1px solid ${T.borderDim}`, borderRadius: 6, padding: 16, overflowX: 'auto' }}>
      {err ? (
        <pre style={{ color: '#b0342c', fontFamily: T.mono, fontSize: 11, whiteSpace: 'pre-wrap', margin: 0 }}>
          diagram error: {err}
        </pre>
      ) : (
        <div style={{ textAlign: 'center' }} dangerouslySetInnerHTML={{ __html: svg }} />
      )}
      {caption && (
        <div style={{ marginTop: 8, textAlign: 'center', fontFamily: T.mono, fontSize: 10.5, color: '#6b6560' }}>{caption}</div>
      )}
    </div>
  );
}
