// Pure builders: turn a PaperCurationDetail payload into Mermaid flowchart definitions
// mirroring the SIRT3 walkthrough template (five-layer overview, raw layer, investigation
// spine, claim→observation grounding, mechanism graph, per-experiment KEfED node-graph,
// and the end-to-end vertical slice). No React here — just strings.

import type {
  PaperCurationDetail, ExperimentGraph, DataSignature, BundleDetail, CurationSpine,
} from '@/lib/scientific-literature';

const CLASSDEFS = [
  '  classDef raw fill:#efe7db,stroke:#8b6f47,color:#3a2e1c;',
  '  classDef inv fill:#e4eef6,stroke:#2c6e9b,color:#123;',
  '  classDef rhet fill:#f7e6f0,stroke:#9b2c6e,color:#3a1228;',
  '  classDef kef fill:#e2f2e8,stroke:#2c8b57,color:#123521;',
  '  classDef dat fill:#fbf0d4,stroke:#b8860b,color:#3a2c05;',
].join('\n');

const mid = (s: string) => 'n' + (s || '').replace(/[^a-zA-Z0-9]/g, '_');
const esc = (s?: string) => (s || '').replace(/["[\]{}|<>]/g, ' ').replace(/\s+/g, ' ').trim();
// Overview-diagram labels clip for compactness; the authoritative full-text view is the HTML
// KefedProtocolGraph (kefed-graph.tsx), whose nodes/params carry title= hover tooltips, and the
// claim/gap/observation text blocks (paper-curation.tsx) show full statements.
const trunc = (s: string, n = 60) => (s.length > n ? s.slice(0, n - 1) + '…' : s);

export function layerOverviewMermaid(d: PaperCurationDetail): string {
  const b = d.bundle || ({} as BundleDetail);
  const nf = (d.fragments || []).length;
  const no = (b.observations || []).length;
  const nc = (b.reported_claims || []).length;
  const ng = (b.reported_gaps || []).length;
  const ne = (b.experiments || []).length;
  const ni = (b.instances || []).length;
  return [
    'flowchart TB',
    '  subgraph RAW["① RAW + FULL TEXT"]',
    '    P["scilit-paper"]',
    '    AR["scilit-pdf-fulltext"]',
    `    FR["${nf} fragments"]`,
    '  end',
    '  subgraph INV["② INVESTIGATION"]',
    '    I["scilit-investigation"]',
    '    B["paper-sensemaking bundle"]',
    '  end',
    '  subgraph RHET["③ RHETORICAL"]',
    `    CL["${nc} claims"]`,
    `    GP["${ng} gaps"]`,
    `    OB["${no} observations"]`,
    '  end',
    '  subgraph KEF["④ KEfED / OOEVV"]',
    `    KM["${ne} kefed-model"]`,
    '  end',
    '  subgraph DAT["⑤ DATA"]',
    `    KI["${ni} data instance"]`,
    '  end',
    '  P --> AR --> FR',
    '  P --> I --> B',
    '  B --> CL & GP & OB & KM',
    '  KM --> KI',
    '  class P,AR,FR raw',
    '  class I,B inv',
    '  class CL,GP,OB rhet',
    '  class KM kef',
    '  class KI dat',
    CLASSDEFS,
  ].join('\n');
}

export function rawLayerMermaid(d: PaperCurationDetail): string {
  const nf = (d.fragments || []).length;
  const title = esc(trunc(d.paper?.name || 'paper', 28));
  return [
    'flowchart LR',
    `  P["scilit-paper<br/>${title}"]`,
    '  A(["scilit-pdf-fulltext"])',
    `  F["${nf} fragments<br/>verbatim anchors"]`,
    '  P -->|representation| A -->|fragmentation| F',
    '  class P,A,F raw',
    CLASSDEFS,
  ].join('\n');
}

export function investigationSpineMermaid(d: PaperCurationDetail): string {
  const s = d.spine || ({} as CurationSpine);
  const inv = esc(trunc(s.name || 'investigation', 34));
  const it = s.iteration != null ? `iteration ${s.iteration}` : 'iteration';
  return [
    'flowchart LR',
    '  P["scilit-paper"]:::raw',
    `  I["scilit-investigation<br/>${inv}"]:::inv`,
    `  IT["${it}"]:::inv`,
    '  B["paper-sensemaking<br/>bundle"]:::inv',
    '  P -->|investigation-focus| I -->|iteration| IT -->|sensemaking stage| B',
    CLASSDEFS,
  ].join('\n');
}

export function claimObservationMermaid(d: PaperCurationDetail): string {
  const edges = d.claim_observations || [];
  const b = d.bundle || ({} as BundleDetail);
  if (!edges.length) return '';
  const claimName = new Map<string, string>();
  for (const c of b.reported_claims || []) claimName.set(c.id, esc(trunc(c.statement || c.id, 34)));
  const obsName = new Map<string, string>();
  for (const o of b.observations || []) obsName.set(o.id, esc(trunc(o.name || o.content || o.id, 30)));
  const lines: string[] = ['flowchart LR'];
  const seen = new Set<string>();
  const cIds: string[] = [];
  const oIds: string[] = [];
  for (const e of edges) {
    const c = mid(e.claim), o = mid(e.observation);
    if (!seen.has(c)) { lines.push(`  ${c}["claim: ${claimName.get(e.claim) || e.claim}"]`); seen.add(c); cIds.push(c); }
    if (!seen.has(o)) { lines.push(`  ${o}(["obs: ${obsName.get(e.observation) || e.observation}"])`); seen.add(o); oIds.push(o); }
    lines.push(`  ${c} -->|grounds| ${o}`);
  }
  if (cIds.length) lines.push(`  class ${cIds.join(',')} rhet`);
  if (oIds.length) lines.push(`  class ${oIds.join(',')} rhet`);
  lines.push(CLASSDEFS);
  return lines.join('\n');
}

export function kefedModelMermaid(exp: ExperimentGraph): string {
  const procs = exp.experiment?.processes || [];
  if (!procs.length) return '';
  const lines: string[] = ['flowchart TB'];
  const ids: string[] = [];
  // subject inference: a material-entity node with no upstream input
  const subj = procs.find((p) => p.type === 'material-entity' && !(p.inputs && p.inputs.length))?.id;
  for (const p of procs) {
    const id = mid(p.id);
    ids.push(id);
    const star = p.id === subj ? '★ ' : '';
    const label = `${star}${esc(trunc(p.name || '', 30))}`;
    if (p.type === 'material-entity') lines.push(`  ${id}["${label}"]`);
    else lines.push(`  ${id}(["${label}"])`);
    for (const pm of p.parameters || []) {
      const vid = mid(pm.id);
      const vals = pm.scale?.values?.length
        ? ` (${esc(pm.scale.values.slice(0, 4).join('/'))})`
        : (pm.scale?.type ? ` (${esc(pm.scale.type)})` : '');
      lines.push(`  ${vid}[/"${esc(pm.role || 'param')}: ${esc(pm.name || '')}${vals}"/]`);
      lines.push(`  ${id} --> ${vid}`);
      ids.push(vid);
    }
    for (const m of p.measurements || []) {
      const vid = mid(m.id);
      const unit = m.scale?.unit ? ` (${esc(m.scale.unit)})` : (m.scale?.type ? ` (${esc(m.scale.type)})` : '');
      lines.push(`  ${vid}{{"measure: ${esc(m.name || '')}${unit}"}}`);
      lines.push(`  ${id} --> ${vid}`);
      ids.push(vid);
    }
  }
  // flow edges (bold): process-input (src ==> node) and process-output (node ==> tgt)
  for (const p of procs) {
    const id = mid(p.id);
    for (const src of p.inputs || []) lines.push(`  ${mid(src)} ==> ${id}`);
    for (const tgt of p.outputs || []) lines.push(`  ${id} ==> ${mid(tgt)}`);
  }
  if (ids.length) lines.push(`  class ${ids.join(',')} kef`);
  lines.push(CLASSDEFS);
  return lines.join('\n');
}

// A one-sentence caption of a model's data signature, e.g.
// "expression-level indexed by [genotype, age, cell-population]".
export function signatureCaption(sig?: DataSignature): string {
  if (!sig) return '';
  const parts: string[] = [];
  for (const v of Object.values(sig)) {
    const idx = (v.index || []).map((i) => i.name).filter(Boolean);
    if (v.name) parts.push(`${v.name} indexed by [${Array.from(new Set(idx)).join(', ')}]`);
  }
  return parts.length ? `Data signature: ${parts.join('; ')}` : '';
}

export function verticalSliceMermaid(d: PaperCurationDetail): string {
  const b = d.bundle || ({} as BundleDetail);
  const claim = (b.reported_claims || [])[0];
  const obs = (b.observations || [])[0];
  const exp = (b.experiments || [])[0];
  const inst = (b.instances || [])[0];
  const lines: string[] = ['flowchart TB'];
  lines.push('  P["scilit-paper"]:::raw');
  lines.push('  FR["fragment (verbatim quote)"]:::raw');
  lines.push('  B["paper-sensemaking bundle"]:::inv');
  if (claim) lines.push(`  C["claim: ${esc(trunc(claim.statement || 'claim', 30))}"]:::rhet`);
  if (obs) lines.push(`  O["obs: ${esc(trunc(obs.name || obs.content || 'observation', 26))}"]:::rhet`);
  if (exp) lines.push(`  M["kefed-model: ${esc(trunc(exp.name || 'experiment', 26))}"]:::kef`);
  if (inst) lines.push('  I["data instance (rows/cells)"]:::dat');
  lines.push('  P -->|representation| FR');
  lines.push('  P -->|sensemaking-paper| B');
  if (claim) lines.push('  B -->|reported-claim| C');
  if (obs) lines.push('  B -->|observation| O');
  if (exp) lines.push('  B -->|experiment| M');
  if (claim && obs) lines.push('  C -.->|grounds| O');
  if (obs) lines.push('  O -.->|derivation| FR');
  if (exp && inst) lines.push('  M -->|instance-of| I');
  if (inst && obs) lines.push('  I -.->|datum-observation| O');
  lines.push(CLASSDEFS);
  return lines.join('\n');
}
