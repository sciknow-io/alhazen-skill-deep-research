'use client';

import { type CSSProperties, type ReactNode } from 'react';
import Link from 'next/link';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { T } from './tokens';

// ─── Icon ──────────────────────────────────────────────────────

interface IconProps {
  name: string;
  size?: number;
  color?: string;
  style?: CSSProperties;
}

export function Icon({ name, size = 14, color = 'currentColor', style }: IconProps) {
  const common = {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: color,
    strokeWidth: 1.6,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    style,
  };
  switch (name) {
    case 'arrow-left':
      return <svg {...common}><path d="M19 12H5M12 19l-7-7 7-7" /></svg>;
    case 'arrow-right':
      return <svg {...common}><path d="M5 12h14M13 6l6 6-6 6" /></svg>;
    case 'external':
      return <svg {...common}><path d="M14 4h6v6" /><path d="M20 4l-9 9" /><path d="M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5" /></svg>;
    case 'refresh':
      return <svg {...common}><path d="M21 12a9 9 0 0 1-9 9 9 9 0 0 1-9-9 9 9 0 0 1 9-9 9 9 0 0 1 6.4 2.6L21 3v5h-5" /></svg>;
    case 'search':
      return <svg {...common}><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></svg>;
    case 'check':
      return <svg {...common}><path d="M5 12l4 4 10-10" /></svg>;
    case 'cross':
      return <svg {...common}><path d="M5 5l14 14M19 5L5 19" /></svg>;
    case 'play':
      return <svg {...common} fill={color}><path d="M6 4l14 8-14 8z" stroke="none" /></svg>;
    case 'code':
      return <svg {...common}><path d="M9 8l-5 4 5 4M15 8l5 4-5 4" /></svg>;
    case 'graph':
      return <svg {...common}><circle cx="6" cy="18" r="2" /><circle cx="12" cy="6" r="2" /><circle cx="18" cy="14" r="2" /><path d="M7.5 17l3-9M13.5 7.5l3 5.5" /></svg>;
    case 'doc':
      return <svg {...common}><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" /><path d="M14 3v6h6" /></svg>;
    case 'book':
      return <svg {...common}><path d="M4 4v15a2 2 0 0 1 2-2h14V3H6a2 2 0 0 0-2 2z" /><path d="M4 19a2 2 0 0 0 2 2h14" /></svg>;
    case 'map':
      return <svg {...common}><path d="M9 4L3 6v14l6-2 6 2 6-2V4l-6 2-6-2z" /><path d="M9 4v14M15 6v14" /></svg>;
    case 'folder':
      return <svg {...common}><path d="M4 4h5l2 2h9a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z" /></svg>;
    case 'sparkles':
      return <svg {...common}><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5L18 18M6 18l2.5-2.5M15.5 8.5L18 6" /></svg>;
    case 'bar-chart':
      return <svg {...common}><rect x="3" y="12" width="4" height="9" rx="1" /><rect x="10" y="7" width="4" height="14" rx="1" /><rect x="17" y="3" width="4" height="18" rx="1" /></svg>;
    default:
      return <svg {...common}><circle cx="12" cy="12" r="6" /></svg>;
  }
}

// ─── Panel ─────────────────────────────────────────────────────

interface PanelProps {
  title?: string;
  action?: ReactNode;
  borderColor?: string;
  bgColor?: string;
  children: ReactNode;
  style?: CSSProperties;
}

export function Panel({ title, action, borderColor, bgColor, children, style }: PanelProps) {
  return (
    <section style={{
      background: bgColor || T.panel,
      border: `1px solid ${borderColor || T.border}`,
      borderRadius: 4,
      padding: '14px 16px',
      display: 'flex',
      flexDirection: 'column',
      gap: 12,
      ...style,
    }}>
      {(title || action) && (
        <header style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <h3 style={{
            margin: 0,
            fontFamily: T.mono,
            fontSize: 10.5,
            fontWeight: 600,
            letterSpacing: '1.4px',
            textTransform: 'uppercase',
            color: T.fgDim,
          }}>{title}</h3>
          <div style={{ flex: 1 }} />
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

// ─── KV ────────────────────────────────────────────────────────

interface KVProps {
  label: string;
  value: string | number | null | undefined;
  mono?: boolean;
  accent?: string | null;
}

export function KV({ label, value, mono, accent }: KVProps) {
  if (value == null) return null;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
      <span style={{
        fontFamily: T.mono,
        fontSize: 9.5,
        letterSpacing: '1.2px',
        textTransform: 'uppercase',
        color: T.fgFaint,
      }}>{label}</span>
      <span style={{
        fontSize: 13,
        color: accent || T.fg,
        fontFamily: mono ? T.mono : T.sans,
      }}>{value}</span>
    </div>
  );
}

// ─── BackNav ───────────────────────────────────────────────────

interface BackNavProps {
  href: string;
  label: string;
}

export function BackNav({ href, label }: BackNavProps) {
  return (
    <Link
      href={href}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        fontFamily: T.mono,
        fontSize: 12,
        color: T.teal,
        textDecoration: 'none',
      }}
    >
      <Icon name="arrow-left" size={14} color={T.teal} />
      {label}
    </Link>
  );
}

// ─── TypeChip ──────────────────────────────────────────────────

interface TypeChipProps {
  short: string;
  color: string;
  icon?: string;
}

export function TypeChip({ short, color, icon }: TypeChipProps) {
  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 4,
      padding: '3px 8px',
      borderRadius: 3,
      background: 'transparent',
      border: `1px solid ${color}`,
      color,
      fontFamily: T.mono,
      fontSize: 10.5,
      letterSpacing: '1px',
      fontWeight: 600,
    }}>
      {icon && <Icon name={icon} size={11} color={color} />}
      {short}
    </span>
  );
}

// ─── FacetBadge ────────────────────────────────────────────────
// A "<facet>:<value>" pill tinted by the facet color.

interface FacetBadgeProps {
  facet: string;
  value: string;
  color: string;
}

export function FacetBadge({ facet, value, color }: FacetBadgeProps) {
  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'baseline',
      gap: 5,
      padding: '2px 8px',
      borderRadius: 3,
      background: `${color}18`,
      border: `1px solid ${color}55`,
      fontFamily: T.mono,
      fontSize: 10.5,
    }}>
      <span style={{ color: T.fgFaint, letterSpacing: '0.4px' }}>{facet}</span>
      <span style={{ color, fontWeight: 600 }}>{value}</span>
    </span>
  );
}

// ─── HeaderStrip ───────────────────────────────────────────────

interface HeaderStripProps {
  typeChip?: { short: string; color: string; icon?: string };
  context?: string;
  title: string;
  description?: string;
  kvPairs?: Array<{ label: string; value: string | number | null | undefined; accent?: string | null }>;
  action?: ReactNode;
}

export function HeaderStrip({ typeChip, context, title, description, kvPairs, action }: HeaderStripProps) {
  return (
    <header style={{
      background: T.bgRaised,
      border: `1px solid ${T.border}`,
      borderRadius: 4,
      padding: '18px 22px',
      display: 'flex',
      flexDirection: 'column',
      gap: 14,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        {typeChip && <TypeChip short={typeChip.short} color={typeChip.color} icon={typeChip.icon} />}
        {context && (
          <>
            <span style={{ color: T.fgFaint, fontFamily: T.mono, fontSize: 11 }}>·</span>
            <span style={{ color: T.fgDim, fontSize: 13, fontFamily: T.mono }}>{context}</span>
          </>
        )}
        <div style={{ flex: 1 }} />
        {action}
      </div>

      <h1 style={{
        margin: 0,
        fontFamily: T.serif,
        fontSize: 28,
        lineHeight: 1.15,
        fontWeight: 400,
        color: T.fg,
        letterSpacing: '-0.4px',
      }}>{title}</h1>

      {description && (
        <p style={{
          margin: 0,
          fontSize: 13.5,
          lineHeight: 1.55,
          color: T.fgDim,
          maxWidth: 720,
        }}>{description}</p>
      )}

      {kvPairs && kvPairs.length > 0 && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 14,
          flexWrap: 'wrap',
          paddingTop: 10,
          borderTop: `1px solid ${T.borderDim}`,
          marginTop: 4,
        }}>
          {kvPairs.map(kv => (
            <KV key={kv.label} label={kv.label} value={kv.value} mono accent={kv.accent} />
          ))}
        </div>
      )}
    </header>
  );
}

// ─── CodeBlock ─────────────────────────────────────────────────
// Monospace scrollable code panel for the Hamilton script / config.

interface CodeBlockProps {
  code: string;
  maxHeight?: number;
}

export function CodeBlock({ code, maxHeight = 420 }: CodeBlockProps) {
  return (
    <pre style={{
      fontFamily: T.mono,
      fontSize: 11.5,
      lineHeight: 1.5,
      background: T.bgSunken,
      border: `1px solid ${T.borderDim}`,
      borderRadius: 4,
      padding: '12px 14px',
      overflow: 'auto',
      maxHeight,
      margin: 0,
      color: T.fg,
      whiteSpace: 'pre',
    }}>{code}</pre>
  );
}

// ─── MarkdownContent ───────────────────────────────────────────

interface MarkdownContentProps {
  content: string;
  style?: CSSProperties;
}

/* eslint-disable @typescript-eslint/no-explicit-any */
const mdComponents: Record<string, React.ComponentType<any>> = {
  p: ({ children }: any) => (
    <p style={{ margin: '0 0 10px', lineHeight: 1.55, color: T.fg, fontSize: 13.5 }}>{children}</p>
  ),
  h1: ({ children }: any) => (
    <h1 style={{ fontFamily: T.serif, fontSize: 22, fontWeight: 400, color: T.fg, margin: '16px 0 8px', letterSpacing: '-0.3px' }}>{children}</h1>
  ),
  h2: ({ children }: any) => (
    <h2 style={{ fontFamily: T.serif, fontSize: 18, fontWeight: 400, color: T.fg, margin: '14px 0 6px', letterSpacing: '-0.2px' }}>{children}</h2>
  ),
  h3: ({ children }: any) => (
    <h3 style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 600, color: T.fgDim, margin: '12px 0 6px', textTransform: 'uppercase', letterSpacing: '0.8px' }}>{children}</h3>
  ),
  h4: ({ children }: any) => (
    <h4 style={{ fontFamily: T.mono, fontSize: 12, fontWeight: 600, color: T.fgDim, margin: '10px 0 4px' }}>{children}</h4>
  ),
  a: ({ href, children }: any) => (
    <a href={href} target="_blank" rel="noopener noreferrer" style={{ color: T.teal, textDecoration: 'underline', textUnderlineOffset: '2px' }}>{children}</a>
  ),
  code: ({ children, className }: any) => {
    if (!className) {
      return (
        <code style={{
          fontFamily: T.mono,
          fontSize: '0.9em',
          background: T.bgSunken,
          padding: '1px 5px',
          borderRadius: 3,
          color: T.teal,
        }}>{children}</code>
      );
    }
    return <code className={className} style={{ fontFamily: T.mono, fontSize: 12 }}>{children}</code>;
  },
  pre: ({ children }: any) => (
    <pre style={{
      fontFamily: T.mono,
      fontSize: 12,
      background: T.bgSunken,
      border: `1px solid ${T.borderDim}`,
      borderRadius: 4,
      padding: '12px 14px',
      overflowX: 'auto',
      margin: '8px 0 12px',
      lineHeight: 1.5,
    }}>{children}</pre>
  ),
  ul: ({ children }: any) => (
    <ul style={{ margin: '4px 0 10px', paddingLeft: 20, listStyleType: 'disc', color: T.fgDim }}>{children}</ul>
  ),
  ol: ({ children }: any) => (
    <ol style={{ margin: '4px 0 10px', paddingLeft: 20, listStyleType: 'decimal', color: T.fgDim }}>{children}</ol>
  ),
  li: ({ children }: any) => (
    <li style={{ marginBottom: 4, fontSize: 13.5, lineHeight: 1.55, color: T.fg }}>{children}</li>
  ),
  table: ({ children }: any) => (
    <div style={{ overflowX: 'auto', margin: '8px 0' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>{children}</table>
    </div>
  ),
  thead: ({ children }: any) => (
    <thead style={{ background: T.bgSunken }}>{children}</thead>
  ),
  th: ({ children }: any) => (
    <th style={{
      fontFamily: T.mono,
      fontSize: 10.5,
      fontWeight: 600,
      color: T.fgDim,
      textAlign: 'left',
      padding: '6px 10px',
      border: `1px solid ${T.borderDim}`,
      textTransform: 'uppercase',
      letterSpacing: '0.5px',
    }}>{children}</th>
  ),
  td: ({ children }: any) => (
    <td style={{
      padding: '5px 10px',
      border: `1px solid ${T.borderDim}`,
      color: T.fg,
      fontSize: 12.5,
    }}>{children}</td>
  ),
  strong: ({ children }: any) => (
    <strong style={{ fontWeight: 600, color: T.fg }}>{children}</strong>
  ),
  em: ({ children }: any) => (
    <em style={{ color: T.fgDim }}>{children}</em>
  ),
  hr: () => (
    <hr style={{ border: 'none', borderTop: `1px solid ${T.borderDim}`, margin: '12px 0' }} />
  ),
};
/* eslint-enable @typescript-eslint/no-explicit-any */

export function MarkdownContent({ content, style }: MarkdownContentProps) {
  let text = content.replace(/\\n/g, '\n');
  text = text.replace(
    /(?<!\]\()(?<!\()(?<![<"'])(https?:\/\/[^\s)>\]"']+)/g,
    '[$1]($1)'
  );
  text = text.replace(
    /(?<!\]\()(?<!\()(?<![<"'])(?:^|(?<=\s))(\/(?:scientific-literature|tech-recon|jobhunt)\/[^\s)>\]"']+)/gm,
    '[$1]($1)'
  );
  return (
    <div style={style}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
        {text}
      </ReactMarkdown>
    </div>
  );
}
