// Starry Night design tokens for the scientific-literature dashboard.
// Base palette mirrors tech-recon; adds facet / cluster / corpus color scales
// for the embedding map.

export const T = {
  // Backgrounds
  bg: '#070d1c',
  bgRaised: '#0c1628',
  bgSunken: '#050a16',
  panel: 'rgba(12, 22, 40, 0.72)',
  panelHi: 'rgba(20, 34, 58, 0.85)',

  // Borders
  border: 'rgba(90, 173, 175, 0.18)',
  borderHi: 'rgba(90, 173, 175, 0.42)',
  borderDim: 'rgba(200, 221, 232, 0.08)',

  // Foreground
  fg: '#c8dde8',
  fgDim: '#8ba4b8',
  fgFaint: '#5e7387',

  // Accent palette
  teal: '#5aadaf',
  tealDim: 'rgba(90, 173, 175, 0.18)',
  blue: '#5b8ab8',
  blueDim: 'rgba(91, 138, 184, 0.18)',
  olive: '#b8c84a',
  oliveDim: 'rgba(184, 200, 74, 0.18)',
  mint: '#62c4bc',
  rust: '#c87a4a',
  rustDim: 'rgba(200, 122, 74, 0.18)',

  // Font stacks
  mono: "var(--font-jetbrains-mono, 'JetBrains Mono'), ui-monospace, 'SF Mono', Menlo, monospace",
  serif: "var(--font-dm-serif, 'DM Serif Display'), 'Iowan Old Style', Georgia, serif",
  sans: "var(--font-dm-sans, 'DM Sans'), -apple-system, system-ui, sans-serif",

  tintBg: (color: string) => `${color}18`,
} as const;

// The 8 facets carried on each paper as scilit-keyword "<facet>:<value>" tags.
export const FACETS = [
  'topology',
  'stage',
  'concern',
  'contribution',
  'domain',
  'autonomy',
  'memory',
  'se-agent',
] as const;

export type FacetName = (typeof FACETS)[number];

// Categorical palette used for cluster, corpus and any facet whose values aren't
// in an explicit map below. Deterministic by hashing the value to an index.
const CATEGORICAL = [
  '#5aadaf', '#5b8ab8', '#b8c84a', '#62c4bc', '#c87a4a',
  '#8ba4b8', '#9b7fd4', '#d4889b', '#7fd49b', '#d4c47f',
  '#7f9bd4', '#d47f7f', '#7fd4cf', '#bcd47f', '#d49b7f',
];

function hashIndex(s: string, mod: number): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h % mod;
}

// Explicit per-facet value palettes for the most-used facets; others fall back
// to the categorical hash.
const FACET_VALUE_COLORS: Record<string, Record<string, string>> = {
  topology: {
    'single-agent': '#5aadaf',
    'multi-agent': '#5b8ab8',
    'compound-non-agentic': '#c87a4a',
  },
  autonomy: {
    autonomous: '#5aadaf',
    'oversight-hitl': '#b8c84a',
    'human-collaborative': '#5b8ab8',
  },
  memory: {
    stateless: '#8ba4b8',
    'context-engineering': '#5b8ab8',
    'persistent-memory': '#62c4bc',
  },
};

/** Color for a facet value (used when coloring the map by a facet). */
export function facetColor(facet: string, value: string | undefined | null): string {
  if (!value || value === '?') return '#3a4656';
  const explicit = FACET_VALUE_COLORS[facet]?.[value];
  if (explicit) return explicit;
  return CATEGORICAL[hashIndex(`${facet}:${value}`, CATEGORICAL.length)];
}

/** Color for an HDBSCAN cluster id; -1 (noise) is muted grey. */
export function clusterColor(cluster: number): string {
  if (cluster < 0) return '#3a4656';
  return CATEGORICAL[cluster % CATEGORICAL.length];
}

/** Color for a corpus id. */
export function corpusColor(corpusId: string | undefined | null): string {
  if (!corpusId) return '#3a4656';
  return CATEGORICAL[hashIndex(corpusId, CATEGORICAL.length)];
}
