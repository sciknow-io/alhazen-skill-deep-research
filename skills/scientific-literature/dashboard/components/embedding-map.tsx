'use client';

import { useRef, useEffect, useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { T, FACETS, type FacetName, facetColor, clusterColor, corpusColor } from './tokens';
import type { MapItem } from '@/lib/scientific-literature';

type ColorBy = 'facet' | 'cluster' | 'corpus';

interface EmbeddingMapProps {
  items: MapItem[];
}

const MARGIN = 28;

export function EmbeddingMap({ items }: EmbeddingMapProps) {
  const router = useRouter();
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 800, h: 600 });
  const [colorBy, setColorBy] = useState<ColorBy>('cluster');
  const [facet, setFacet] = useState<FacetName>('topology');
  const [hoverId, setHoverId] = useState<string | null>(null);

  // Responsive sizing
  useEffect(() => {
    if (!containerRef.current) return;
    const el = containerRef.current;
    const ro = new ResizeObserver(() => {
      setSize({ w: el.clientWidth, h: el.clientHeight });
    });
    ro.observe(el);
    setSize({ w: el.clientWidth, h: el.clientHeight });
    return () => ro.disconnect();
  }, []);

  // Data domain with padding
  const { toX, toY } = useMemo(() => {
    const xs = items.map((d) => d.x);
    const ys = items.map((d) => d.y);
    const xMin = Math.min(...xs), xMax = Math.max(...xs);
    const yMin = Math.min(...ys), yMax = Math.max(...ys);
    const xPad = (xMax - xMin) * 0.06 || 1;
    const yPad = (yMax - yMin) * 0.06 || 1;
    const dxMin = xMin - xPad, dxMax = xMax + xPad;
    const dyMin = yMin - yPad, dyMax = yMax + yPad;
    const innerW = Math.max(size.w - MARGIN * 2, 1);
    const innerH = Math.max(size.h - MARGIN * 2, 1);
    return {
      toX: (x: number) => MARGIN + ((x - dxMin) / (dxMax - dxMin)) * innerW,
      // invert y so larger y is higher on screen
      toY: (y: number) => MARGIN + (1 - (y - dyMin) / (dyMax - dyMin)) * innerH,
    };
  }, [items, size]);

  const colorOf = useMemo(() => {
    return (d: MapItem): string => {
      if (colorBy === 'cluster') return clusterColor(d.cluster);
      if (colorBy === 'corpus') return corpusColor(d.corpus_ids[0]);
      return facetColor(facet, d.facets[facet]);
    };
  }, [colorBy, facet]);

  // Legend entries for the current coloring
  const legend = useMemo(() => {
    const map = new Map<string, string>(); // label -> color
    for (const d of items) {
      if (colorBy === 'cluster') {
        const label = d.cluster < 0 ? 'noise' : `cluster ${d.cluster}`;
        map.set(label, clusterColor(d.cluster));
      } else if (colorBy === 'corpus') {
        const cid = d.corpus_ids[0] || '—';
        map.set(cid, corpusColor(cid));
      } else {
        const v = d.facets[facet] || '?';
        map.set(v, facetColor(facet, v));
      }
    }
    return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }, [items, colorBy, facet]);

  const hovered = hoverId ? items.find((d) => d.paper_id === hoverId) : null;

  const segBtn = (key: ColorBy, label: string) => (
    <button
      key={key}
      onClick={() => setColorBy(key)}
      style={{
        fontFamily: T.mono,
        fontSize: 10.5,
        letterSpacing: '0.6px',
        padding: '3px 10px',
        cursor: 'pointer',
        background: colorBy === key ? T.teal : 'transparent',
        color: colorBy === key ? T.bg : T.fgDim,
        border: `1px solid ${colorBy === key ? T.teal : T.borderDim}`,
        textTransform: 'lowercase',
      }}
    >{label}</button>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, height: '100%' }}>
      {/* Controls */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <span style={{ fontFamily: T.mono, fontSize: 9.5, letterSpacing: '1.2px', textTransform: 'uppercase', color: T.fgFaint }}>color by</span>
        <div style={{ display: 'inline-flex' }}>
          {segBtn('cluster', 'cluster')}
          {segBtn('facet', 'facet')}
          {segBtn('corpus', 'corpus')}
        </div>
        {colorBy === 'facet' && (
          <select
            value={facet}
            onChange={(e) => setFacet(e.target.value as FacetName)}
            style={{
              fontFamily: T.mono,
              fontSize: 11,
              background: T.bgSunken,
              color: T.fg,
              border: `1px solid ${T.border}`,
              borderRadius: 3,
              padding: '3px 8px',
            }}
          >
            {FACETS.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
        )}
        <span style={{ flex: 1 }} />
        <span style={{ fontFamily: T.mono, fontSize: 10.5, color: T.fgFaint }}>{items.length} papers</span>
      </div>

      {/* Plot + legend */}
      <div style={{ display: 'flex', gap: 12, flex: 1, minHeight: 0 }}>
        <div
          ref={containerRef}
          style={{
            flex: 1,
            minWidth: 0,
            position: 'relative',
            background: T.bgSunken,
            border: `1px solid ${T.borderDim}`,
            borderRadius: 4,
            overflow: 'hidden',
          }}
        >
          {size.w > 0 && (
            <svg width={size.w} height={size.h} style={{ display: 'block' }}>
              {items.map((d) => {
                const isHover = d.paper_id === hoverId;
                return (
                  <circle
                    key={d.paper_id}
                    cx={toX(d.x)}
                    cy={toY(d.y)}
                    r={isHover ? 7 : 4.5}
                    fill={colorOf(d)}
                    fillOpacity={0.85}
                    stroke={isHover ? T.fg : 'none'}
                    strokeWidth={isHover ? 1.5 : 0}
                    style={{ cursor: 'pointer' }}
                    onMouseEnter={() => setHoverId(d.paper_id)}
                    onMouseLeave={() => setHoverId((cur) => (cur === d.paper_id ? null : cur))}
                    onClick={() => router.push(`/scientific-literature/paper/${d.paper_id}`)}
                  >
                    <title>{`${d.title || d.paper_id}${d.year ? ` (${d.year})` : ''}`}</title>
                  </circle>
                );
              })}
            </svg>
          )}

          {/* Hover card */}
          {hovered && (
            <div style={{
              position: 'absolute',
              left: 12,
              bottom: 12,
              maxWidth: 380,
              background: T.panelHi,
              border: `1px solid ${T.borderHi}`,
              borderRadius: 4,
              padding: '10px 12px',
              pointerEvents: 'none',
            }}>
              <div style={{ fontSize: 12.5, color: T.fg, lineHeight: 1.4, marginBottom: 6 }}>
                {hovered.title || hovered.paper_id}
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {hovered.year != null && (
                  <span style={{ fontFamily: T.mono, fontSize: 10, color: T.fgFaint }}>{hovered.year}</span>
                )}
                {FACETS.filter((f) => hovered.facets[f]).map((f) => (
                  <span key={f} style={{
                    fontFamily: T.mono,
                    fontSize: 9.5,
                    color: facetColor(f, hovered.facets[f]),
                    border: `1px solid ${facetColor(f, hovered.facets[f])}44`,
                    borderRadius: 2,
                    padding: '0 4px',
                  }}>{hovered.facets[f]}</span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Legend */}
        <div style={{
          width: 180,
          flexShrink: 0,
          overflowY: 'auto',
          background: T.panel,
          border: `1px solid ${T.borderDim}`,
          borderRadius: 4,
          padding: '10px 12px',
        }}>
          <div style={{ fontFamily: T.mono, fontSize: 9.5, letterSpacing: '1.2px', textTransform: 'uppercase', color: T.fgFaint, marginBottom: 8 }}>
            {colorBy === 'facet' ? facet : colorBy}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            {legend.map(([label, color]) => (
              <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                <span style={{ width: 9, height: 9, borderRadius: 5, background: color, flexShrink: 0 }} />
                <span style={{ fontFamily: T.mono, fontSize: 10.5, color: T.fgDim, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
