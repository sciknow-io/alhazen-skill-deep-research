'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { T } from '@/components/scientific-literature/tokens';
import { BackNav } from '@/components/scientific-literature/atoms';
import type { OntologySearch } from '@/lib/scientific-literature';

type Kind = 'all' | 'methods' | 'measurands' | 'things';

const KIND_COLOR: Record<string, string> = { methods: T.olive, measurands: T.teal, things: T.rust };

function Card({ name, longForm, definition, badge, badgeColor, meta, href }: {
  name?: string; longForm?: string; definition?: string; badge: string; badgeColor: string;
  meta?: string; href?: string;
}) {
  const body = (
    <div style={{
      border: `1px solid ${T.borderDim}`, borderRadius: 7, padding: '10px 13px', background: T.bgRaised,
      height: '100%', display: 'flex', flexDirection: 'column', gap: 4,
    }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span style={{ fontFamily: T.mono, fontSize: 9, color: badgeColor, textTransform: 'uppercase', letterSpacing: 0.5, border: `1px solid ${badgeColor}`, borderRadius: 3, padding: '1px 5px' }}>{badge}</span>
        <span style={{ fontFamily: T.sans, fontSize: 13.5, color: T.fg, fontWeight: 500 }}>{name}</span>
        {href && <span style={{ marginLeft: 'auto', fontFamily: T.mono, fontSize: 10, color: T.olive }}>view →</span>}
      </div>
      {longForm && <div style={{ fontFamily: T.mono, fontSize: 10.5, color: T.fgFaint }}>= {longForm}</div>}
      {definition && <div style={{ fontFamily: T.sans, fontSize: 12, color: T.fgDim, lineHeight: 1.4 }}>{definition}</div>}
      {meta && <div style={{ fontFamily: T.mono, fontSize: 10, color: T.fgFaint, marginTop: 'auto', paddingTop: 4 }}>{meta}</div>}
    </div>
  );
  return href ? <Link href={href} style={{ textDecoration: 'none' }}>{body}</Link> : body;
}

function Grid({ children }: { children: React.ReactNode }) {
  return <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 10 }}>{children}</div>;
}

export default function OntologyPage() {
  const [q, setQ] = useState('');
  const [data, setData] = useState<OntologySearch | null>(null);
  const [kind, setKind] = useState<Kind>('all');
  const [loading, setLoading] = useState(true);

  // Seed the search box from a ?q= deep link (e.g. an OOEVV term clicked in a KEfED diagram).
  useEffect(() => {
    const initial = new URLSearchParams(window.location.search).get('q');
    if (initial) setQ(initial);
  }, []);

  useEffect(() => {
    setLoading(true);
    const t = setTimeout(() => {
      fetch('/api/scientific-literature/ontology?q=' + encodeURIComponent(q))
        .then((r) => (r.ok ? r.json() : Promise.reject(`ontology ${r.status}`)))
        .then((d) => setData(d))
        .catch(() => setData(null))
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  const templates = data?.templates || [];
  const qualities = data?.qualities || [];
  const entities = data?.entities || [];
  const show = (k: Kind) => kind === 'all' || kind === k;
  const total = templates.length + qualities.length + entities.length;

  const tabs: Array<{ k: Kind; label: string; n: number }> = [
    { k: 'all', label: 'All', n: total },
    { k: 'methods', label: 'Methods (templates)', n: templates.length },
    { k: 'measurands', label: 'Measurands (qualities)', n: qualities.length },
    { k: 'things', label: 'Things (entities)', n: entities.length },
  ];

  return (
    <div style={{ minHeight: '100vh', background: T.bg, color: T.fg, fontFamily: T.sans, display: 'flex', flexDirection: 'column' }}>
      <header style={{ borderBottom: `1px solid ${T.borderDim}`, background: T.bgRaised, padding: '20px 24px' }}>
        <div style={{ maxWidth: 1100, margin: '0 auto', display: 'flex', alignItems: 'center', gap: 24 }}>
          <BackNav href="/scientific-literature" label="Scientific Literature" />
          <div style={{ flex: 1 }}>
            <h1 style={{ margin: 0, fontFamily: T.serif, fontSize: 26, fontWeight: 400, letterSpacing: '-0.4px' }}>Methods &amp; Ontology</h1>
            <span style={{ fontFamily: T.mono, fontSize: 11, color: T.fgDim }}>
              browse the curated OOEVV / KEfED vocabulary — methods, measurands &amp; things, with definitions
            </span>
          </div>
        </div>
      </header>

      <main style={{ maxWidth: 1100, margin: '0 auto', padding: 24, width: '100%', flex: 1, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <input
          autoFocus
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search definitions, names, abbreviations…  (e.g. flow cytometry, ROS, lifespan, SIRT3)"
          style={{
            width: '100%', boxSizing: 'border-box', padding: '11px 14px', fontFamily: T.sans, fontSize: 14,
            background: T.bgRaised, color: T.fg, border: `1px solid ${T.borderHi}`, borderRadius: 6, outline: 'none',
          }}
        />
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {tabs.map((t) => (
            <button key={t.k} onClick={() => setKind(t.k)}
              style={{
                fontFamily: T.mono, fontSize: 11.5, padding: '5px 11px', borderRadius: 4, cursor: 'pointer',
                background: kind === t.k ? T.fg : 'transparent', color: kind === t.k ? T.bg : T.fgDim,
                border: `1px solid ${kind === t.k ? T.fg : T.borderDim}`,
              }}>
              {t.label} <span style={{ opacity: 0.7 }}>{t.n}</span>
            </button>
          ))}
        </div>

        {loading && <p style={{ fontFamily: T.mono, fontSize: 12, color: T.fgFaint }}>searching…</p>}
        {!loading && total === 0 && <p style={{ fontFamily: T.mono, fontSize: 12, color: T.fgFaint }}>No ontology terms match “{q}”.</p>}

        {show('methods') && templates.length > 0 && (
          <section>
            <h2 style={{ fontFamily: T.mono, fontSize: 11, color: T.olive, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 }}>Methods — KEfED templates ({templates.length})</h2>
            <Grid>
              {templates.map((t) => (
                <Card key={t.id} name={t.name} longForm={t.long_form} definition={t.definition} badge="method" badgeColor={T.olive}
                  href={`/scientific-literature/template/${t.id}`}
                  meta={`${t.instance_count ?? 0} instances · ${t.process_count ?? 0} steps · ${(t.slots || []).length} slots`} />
              ))}
            </Grid>
          </section>
        )}
        {show('measurands') && qualities.length > 0 && (
          <section>
            <h2 style={{ fontFamily: T.mono, fontSize: 11, color: T.teal, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 }}>Measurands — OOEVV qualities ({qualities.length})</h2>
            <Grid>
              {qualities.map((qa) => (
                <Card key={qa.id} name={qa.name} longForm={qa.long_form} definition={qa.definition} badge="measurand" badgeColor={T.teal} />
              ))}
            </Grid>
          </section>
        )}
        {show('things') && entities.length > 0 && (
          <section>
            <h2 style={{ fontFamily: T.mono, fontSize: 11, color: T.rust, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 }}>Things — curated entities ({entities.length})</h2>
            <Grid>
              {entities.map((en) => (
                <Card key={en.id} name={en.name} longForm={en.long_form} definition={en.definition}
                  badge={en.kind || 'entity'} badgeColor={T.rust} />
              ))}
            </Grid>
          </section>
        )}
      </main>
    </div>
  );
}
