'use client';

import { useState } from 'react';
import Link from 'next/link';
import { T } from './tokens';
import { Panel, Icon, MarkdownContent } from './atoms';
import type { StageDetail, IngestPaper, BundleSummary, Corpus } from '@/lib/scientific-literature';

const rowS: React.CSSProperties = { display: 'grid', gap: 12, alignItems: 'center', padding: '9px 14px', borderTop: `1px solid ${T.borderDim}`, textDecoration: 'none', color: 'inherit' };
const faint: React.CSSProperties = { fontFamily: T.mono, fontSize: 10.5, color: T.fgFaint };

function StageNote({ content }: { content?: string }) {
  if (!content) return null;
  return <Panel title="Notes"><MarkdownContent content={content} /></Panel>;
}

function CorporaPanel({ corpora }: { corpora: Corpus[] }) {
  return (
    <Panel title={`Corpora (${corpora.length})`}>
      {corpora.length === 0 && <span style={faint}>No corpora scoped to this investigation.</span>}
      {corpora.map((c) => (
        <div key={c.id} style={{ display: 'flex', flexDirection: 'column', gap: 3, padding: '6px 0', borderTop: `1px solid ${T.borderDim}` }}>
          <span style={{ fontSize: 13, color: T.fg }}>{c.name || c.id}</span>
          {c.description && <span style={faint}>{c.description}</span>}
          {c['logical-query'] && <code style={{ fontFamily: T.mono, fontSize: 10.5, color: T.teal }}>{c['logical-query']}</code>}
        </div>
      ))}
    </Panel>
  );
}

function CopyFilenameButton({ paper }: { paper: IngestPaper }) {
  const [copied, setCopied] = useState(false);
  const name = paper.pdfFilename || `${paper.id}.pdf`;
  return (
    <button
      onClick={(e) => {
        e.preventDefault();
        navigator.clipboard?.writeText(name).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1200); });
      }}
      title={`Save your downloaded PDF as ${name}, then ingest with: fetch-pdf --id ${paper.id} --file ${name}`}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontFamily: T.mono, fontSize: 10, color: copied ? T.olive : T.teal, background: 'transparent', border: `1px solid ${T.borderHi}`, borderRadius: 3, padding: '3px 8px', cursor: 'pointer' }}
    >
      <Icon name={copied ? 'check' : 'doc'} size={11} color={copied ? T.olive : T.teal} /> {copied ? 'copied' : 'filename'}
    </button>
  );
}

function IngestionStage({ stage }: { stage: StageDetail }) {
  const papers = stage.papers || [];
  return (
    <>
      <CorporaPanel corpora={stage.corpora || []} />
      <Panel title={`Papers (${papers.length})`}>
        {papers.length === 0 && <span style={faint}>No papers ingested.</span>}
        {papers.map((p) => (
          <div key={p.id} style={{ ...rowS, gridTemplateColumns: '52px 1fr auto auto auto' }}>
            <span style={faint}>{p.year ?? '—'}</span>
            <Link href={`/scientific-literature/paper/${p.id}`} style={{ fontSize: 13, color: T.fg, textDecoration: 'none', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.name || p.id}</Link>
            <span style={{ fontFamily: T.mono, fontSize: 10, color: p.fulltextPresent ? T.olive : T.fgFaint, border: `1px solid ${p.fulltextPresent ? T.oliveDim : T.borderDim}`, borderRadius: 3, padding: '2px 6px' }}>
              {p.fulltextPresent ? 'full text' : (p.acquisition_status || 'no text')}
            </span>
            {p.doi
              ? <a href={`https://doi.org/${p.doi}`} target="_blank" rel="noreferrer" style={{ fontFamily: T.mono, fontSize: 10, color: T.teal }}>doi ↗</a>
              : <span style={faint}>—</span>}
            <CopyFilenameButton paper={p} />
          </div>
        ))}
      </Panel>
    </>
  );
}

function SensemakingStage({ bundles }: { bundles: BundleSummary[] }) {
  return (
    <Panel title={`Per-paper sensemaking bundles (${bundles.length})`}>
      {bundles.length === 0 && <span style={faint}>No sensemaking bundles yet.</span>}
      {bundles.map((bn) => (
        <Link
          key={bn.id}
          href={`/scientific-literature/paper/${bn.paper?.id ?? ''}`}
          style={{ ...rowS, gridTemplateColumns: '1fr auto' }}
          onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(90,173,175,0.06)'; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
        >
          <div style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
            <span style={{ fontSize: 13, color: T.fg, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{bn.paper?.name || bn.name || bn.id}</span>
            <span style={faint}>{bn.observation_count ?? 0} obs · {bn.reported_claim_count ?? 0} claims · {bn.reported_gap_count ?? 0} gaps</span>
          </div>
          <Icon name="arrow-right" size={14} color={T.teal} />
        </Link>
      ))}
    </Panel>
  );
}

function AnalysisStage({ stage }: { stage: StageDetail }) {
  const notes = stage.pipeline_notes || [];
  return (
    <Panel title={`Analysis pipelines (${notes.length})`}>
      {notes.length === 0 && <span style={faint}>No analysis pipelines yet. Embedding maps and visualizations are authored here as pipeline-notes.</span>}
      {notes.map((n) => (
        <Link key={n.id} href={`/scientific-literature/faceting-note/${n.id}`} style={{ ...rowS, gridTemplateColumns: '1fr auto' }}>
          <span style={{ fontSize: 13, color: T.fg }}>{n.name || n.id}</span>
          <Icon name="bar-chart" size={14} color={T.olive} />
        </Link>
      ))}
    </Panel>
  );
}

export function StageView({ stage }: { stage: StageDetail }) {
  switch (stage.kind) {
    case 'discovery':
      return (<><CorporaPanel corpora={stage.corpora || []} /><StageNote content={stage.content} /></>);
    case 'ingest':
      return <IngestionStage stage={stage} />;
    case 'sensemaking':
      return <SensemakingStage bundles={stage.bundles || []} />;
    case 'analysis':
      return <AnalysisStage stage={stage} />;
    case 'report':
      return stage.content ? <Panel title="Report"><MarkdownContent content={stage.content} /></Panel> : <Panel title="Report"><span style={faint}>No report authored for this iteration yet.</span></Panel>;
    default:
      return <StageNote content={stage.content} />;
  }
}
