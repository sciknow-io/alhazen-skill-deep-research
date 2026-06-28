'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { T } from '@/components/scientific-literature/tokens';
import { BackNav } from '@/components/scientific-literature/atoms';
import { KefedProtocolGraph } from '@/components/scientific-literature/kefed-graph';
import type { TemplateDetail } from '@/lib/scientific-literature';

export default function TemplatePage() {
  const params = useParams();
  const id = String(params?.id || '');
  const [tpl, setTpl] = useState<(TemplateDetail & { success: boolean }) | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    fetch('/api/scientific-literature/template/' + encodeURIComponent(id))
      .then((r) => (r.ok ? r.json() : Promise.reject(`template ${r.status}`)))
      .then((d) => (d.success === false ? setError('Template not found') : setTpl(d)))
      .catch((e) => setError(String(e)));
  }, [id]);

  return (
    <div style={{ minHeight: '100vh', background: T.bg, color: T.fg, fontFamily: T.sans }}>
      <header style={{ borderBottom: `1px solid ${T.borderDim}`, background: T.bgRaised, padding: '20px 24px' }}>
        <div style={{ maxWidth: 1100, margin: '0 auto', display: 'flex', alignItems: 'center', gap: 24 }}>
          <BackNav href="/scientific-literature/ontology" label="Methods & Ontology" />
          <div style={{ flex: 1 }}>
            <h1 style={{ margin: 0, fontFamily: T.serif, fontSize: 24, fontWeight: 400 }}>{tpl?.name || id}</h1>
            <span style={{ fontFamily: T.mono, fontSize: 11, color: T.olive }}>KEfED template — reusable experiment design</span>
          </div>
        </div>
      </header>

      <main style={{ maxWidth: 1100, margin: '0 auto', padding: 24, display: 'flex', flexDirection: 'column', gap: 16 }}>
        {error && <p style={{ fontFamily: T.mono, fontSize: 12, color: T.rust }}>{error}</p>}
        {tpl && (
          <>
            {tpl.long_form && <div style={{ fontFamily: T.mono, fontSize: 12, color: T.fgFaint }}>= {tpl.long_form}</div>}
            {tpl.definition && <p style={{ fontFamily: T.sans, fontSize: 14, color: T.fgDim, lineHeight: 1.5, margin: 0, maxWidth: 800 }}>{tpl.definition}</p>}

            {!!(tpl.slots || []).length && (
              <section>
                <h2 style={{ fontFamily: T.mono, fontSize: 11, color: T.rust, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 }}>Typed slots (filled per paper)</h2>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                  {tpl.slots!.map((s) => (
                    <div key={s.id} title={s.definition || ''} style={{ border: `1px solid ${T.borderDim}`, borderRadius: 6, padding: '6px 10px', cursor: s.definition ? 'help' : 'default' }}>
                      <span style={{ fontFamily: T.mono, fontSize: 10, color: T.rust, textTransform: 'uppercase', letterSpacing: 0.4 }}>{s.role}</span>
                      {s.kind && <span style={{ fontFamily: T.mono, fontSize: 10, color: T.fgFaint }}> · {s.kind}</span>}
                      {s.definition && <div style={{ fontFamily: T.sans, fontSize: 11.5, color: T.fgDim, maxWidth: 260, marginTop: 2 }}>{s.definition}</div>}
                    </div>
                  ))}
                </div>
              </section>
            )}

            {!!(tpl.variables || []).length && (
              <section>
                <h2 style={{ fontFamily: T.mono, fontSize: 11, color: T.teal, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 }}>Variables</h2>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {tpl.variables!.map((v) => (
                    <div key={v.id} style={{ fontFamily: T.sans, fontSize: 12.5, color: T.fg }}>
                      <span style={{ fontFamily: T.mono, fontSize: 10, color: v.role === 'measurement' ? T.teal : T.blue, marginRight: 6 }}>[{v.role}]</span>
                      {v.name}
                      {v.quality?.quality && <span style={{ color: T.fgFaint }}> · measures {v.quality.quality}</span>}
                      {v.definition && <div style={{ fontFamily: T.sans, fontSize: 11.5, color: T.fgDim, paddingLeft: 18 }}>{v.definition}</div>}
                    </div>
                  ))}
                </div>
              </section>
            )}

            {tpl.graph && (tpl.graph.processes || []).length > 0 && (
              <section>
                <h2 style={{ fontFamily: T.mono, fontSize: 11, color: T.fg, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 }}>KEfED protocol graph</h2>
                <KefedProtocolGraph exp={{ id: tpl.id, name: tpl.name, experiment: tpl.graph }} />
              </section>
            )}
          </>
        )}
      </main>
    </div>
  );
}
