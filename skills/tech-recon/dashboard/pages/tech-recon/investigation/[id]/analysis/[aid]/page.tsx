'use client';

import { useState, useEffect, use } from 'react';
import Link from 'next/link';
import { T } from '@/components/tech-recon/tokens';
import { Icon, BackNav, Panel } from '@/components/tech-recon/atoms';
import { AnalysisRunner } from '@/components/tech-recon/analysis-runner';
import type { TechReconAnalysis } from '@/lib/tech-recon';

function CodeBlock({ title, code, language }: { title: string; code: string; language?: string }) {
  const [open, setOpen] = useState(false);
  const unescaped = code.replace(/\\n/g, '\n');
  const lines = unescaped.split('\n');
  const lineCount = lines.length;
  const charCount = code.length;
  const isLarge = charCount > 10000;
  const displayCode = open
    ? (isLarge ? unescaped.slice(0, 10000) : unescaped)
    : lines.slice(0, 3).join('\n');

  const sizeLabel = charCount > 100000
    ? `${(charCount / 1000).toFixed(0)}K chars`
    : `${lineCount} lines`;

  return (
    <div style={{ marginTop: 20, paddingTop: 20, borderTop: `1px solid ${T.borderDim}` }}>
      <button
        onClick={() => setOpen(!open)}
        style={{
          display: 'flex', alignItems: 'center', gap: 8,
          background: 'transparent', border: 'none', cursor: 'pointer',
          color: T.fgDim, fontFamily: T.mono, fontSize: 10.5, fontWeight: 600,
          textTransform: 'uppercase', letterSpacing: '1px', padding: 0, marginBottom: 12,
        }}
      >
        <Icon name={open ? 'chevron-down' : 'chevron-right'} size={12} color={T.fgFaint} />
        {title}
        <span style={{
          fontWeight: 400, fontSize: 10, color: T.fgFaint,
          textTransform: 'none', letterSpacing: '0',
        }}>
          {language && `${language} · `}{sizeLabel}
        </span>
      </button>
      <pre style={{
        fontFamily: T.mono, fontSize: 12, background: T.bgSunken,
        border: `1px solid ${T.borderDim}`, borderRadius: 4,
        padding: 16, overflowX: 'auto', color: T.fg,
        maxHeight: open ? '600px' : '4.5em',
        overflow: open ? 'auto' : 'hidden',
        position: 'relative',
      }}>
        <code>{displayCode}</code>
        {!open && lineCount > 3 && (
          <div style={{
            position: 'absolute', bottom: 0, left: 0, right: 0, height: 32,
            background: `linear-gradient(transparent, ${T.bgSunken})`,
          }} />
        )}
      </pre>
      {open && isLarge && (
        <p style={{ fontSize: 11, color: T.fgFaint, fontStyle: 'italic', marginTop: 6 }}>
          Showing first 10K of {(charCount / 1000).toFixed(0)}K chars (contains embedded data)
        </p>
      )}
    </div>
  );
}

function SourceCodeSections({ analysis }: { analysis: TechReconAnalysis }) {
  const sections: { title: string; code: string; language: string }[] = [];

  if (analysis.query) {
    sections.push({ title: 'TypeQL Query', code: analysis.query, language: 'typeql' });
  }
  if (analysis.plot_code) {
    sections.push({ title: 'Observable Plot Code', code: analysis.plot_code, language: 'javascript' });
  }
  if (analysis.pipeline_script) {
    sections.push({ title: 'Pipeline Script', code: analysis.pipeline_script, language: 'python' });
  }
  if (analysis.pipeline_config) {
    sections.push({ title: 'Pipeline Config', code: analysis.pipeline_config, language: 'json' });
  }

  if (sections.length === 0) return null;

  return (
    <>
      {sections.map(s => (
        <CodeBlock key={s.title} title={s.title} code={s.code} language={s.language} />
      ))}
    </>
  );
}

export default function AnalysisPage({ params }: { params: Promise<{ id: string; aid: string }> }) {
  const { id, aid } = use(params);
  const [analysis, setAnalysis] = useState<TechReconAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetch(`/api/tech-recon/analysis/${aid}`)
      .then(r => { if (!r.ok) throw new Error(`API error: ${r.status}`); return r.json(); })
      .then(json => setAnalysis(json.analysis || json))
      .catch(err => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, [aid]);

  if (loading) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: T.bg }}>
        <Icon name="refresh" size={24} color={T.fgFaint} />
      </div>
    );
  }

  if (error || !analysis) {
    return (
      <div style={{ minHeight: '100vh', background: T.bg, color: T.fg, fontFamily: T.sans }}>
        <header style={{ borderBottom: `1px solid ${T.borderDim}`, background: T.bgRaised, padding: '12px 24px' }}>
          <BackNav href={`/tech-recon/investigation/${id}`} label="Investigation" />
        </header>
        <main style={{ maxWidth: 1200, margin: '0 auto', padding: '48px 24px', textAlign: 'center' }}>
          <p style={{ color: '#e05555' }}>{error || 'Analysis not found'}</p>
        </main>
      </div>
    );
  }

  const typeColor = T.analysisTypeColor(analysis.type);

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', background: T.bg, color: T.fg, fontFamily: T.sans }}>
      {/* Header breadcrumb */}
      <header style={{
        borderBottom: `1px solid ${T.borderDim}`,
        background: T.bgRaised,
        padding: '12px 24px',
      }}>
        <div style={{ maxWidth: 1200, margin: '0 auto', display: 'flex', alignItems: 'center', gap: 12, fontSize: 12 }}>
          <BackNav href="/tech-recon" label="Tech Recon" />
          <span style={{ color: T.fgFaint }}>/</span>
          <Link href={`/tech-recon/investigation/${id}`} style={{ color: T.teal, textDecoration: 'none', fontFamily: T.mono, fontSize: 12 }}>
            Investigation
          </Link>
        </div>
      </header>

      <main style={{ maxWidth: 1200, margin: '0 auto', padding: 24, flex: 1, width: '100%' }}>
        {/* Title + type badge */}
        <div style={{ marginBottom: 24 }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 8 }}>
            <h1 style={{
              margin: 0, fontFamily: T.serif, fontSize: 28, lineHeight: 1.15,
              fontWeight: 400, color: T.fg, letterSpacing: '-0.4px', flex: 1,
            }}>{analysis.title}</h1>
            {analysis.type && (
              <span style={{
                fontFamily: T.mono, fontSize: 10.5, letterSpacing: '0.6px', fontWeight: 600,
                textTransform: 'uppercase', padding: '3px 8px', borderRadius: 2,
                color: typeColor, border: `1px solid ${typeColor}66`,
                background: T.tintBg(typeColor), flexShrink: 0, marginTop: 4,
              }}>{analysis.type}</span>
            )}
          </div>

          {analysis.description && !analysis.description.trimStart().startsWith('[') && !analysis.description.trimStart().startsWith('{') && (
            <p style={{ fontSize: 13.5, lineHeight: 1.55, color: T.fgDim, maxWidth: 640, margin: 0 }}>
              {analysis.description}
            </p>
          )}
        </div>

        {/* Analysis panel */}
        <Panel title="Analysis">
          <AnalysisRunner
            analysisId={aid}
            title={analysis.title}
            description={analysis.description}
            plotCode={analysis.plot_code}
            analysisType={analysis.type || 'plot'}
          />

          <SourceCodeSections analysis={analysis} />
        </Panel>
      </main>

      <footer style={{ borderTop: `1px solid ${T.borderDim}`, marginTop: 'auto', padding: '16px 24px' }}>
        <div style={{
          maxWidth: 1200, margin: '0 auto',
          display: 'flex', alignItems: 'center', gap: 10,
          fontFamily: T.mono, fontSize: 10, color: T.fgFaint, letterSpacing: '0.6px',
        }}>
          <span>analysis · {aid}</span>
          <span>·</span>
          <span>shape: show-analysis --json</span>
        </div>
      </footer>
    </div>
  );
}
