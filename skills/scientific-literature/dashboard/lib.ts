import { execFile } from 'child_process';
import { promisify } from 'util';
import path from 'path';
import { runSkill, gatewayConfigured } from '@/lib/skill-gateway';

const execFileAsync = promisify(execFile);

// SCILIT_SKILL_ROOT: absolute path to the scientific-literature skill dir (standalone demo)
// PROJECT_ROOT: absolute path to skillful-alhazen root (used when installed)
// NOTEBOOK_SCRIPT_PATH: override for typedb_notebook.py location
const SKILL_ROOT = process.env.SCILIT_SKILL_ROOT;
const PROJECT_ROOT = process.env.PROJECT_ROOT || path.resolve(process.cwd());

const SCILIT_SCRIPT = SKILL_ROOT
  ? path.join(SKILL_ROOT, 'scientific_literature.py')
  : path.join(PROJECT_ROOT, '.claude/skills/scientific-literature/scientific_literature.py');

const NOTEBOOK_SCRIPT = process.env.NOTEBOOK_SCRIPT_PATH
  || path.join(PROJECT_ROOT, '.claude/skills/typedb-notebook/typedb_notebook.py');

// All scilit commands run from PROJECT_ROOT: the semantic commands (`map`, embed,
// cluster) import skillful_alhazen + umap/hdbscan/qdrant which live in the MAIN
// project venv, not the scilit sub-venv. Read commands use typedb-driver which the
// main venv also has, so PROJECT_ROOT is the correct cwd for every command.
const CWD = PROJECT_ROOT;

// Prefer the warm gateway (no per-request Python cold-start); fall back to
// spawning the CLI directly for host dev where no gateway is running.
async function runScilit(args: string[], db?: string): Promise<unknown> {
  // A `db` override is passed as a plain --database arg so it threads through BOTH the
  // warm gateway and the direct-spawn path (the dashboard DB switcher).
  const full = db ? ['--database', db, ...args] : args;
  if (gatewayConfigured()) return runSkill('scientific-literature', full);
  const { stdout } = await execFileAsync(
    'uv',
    ['run', 'python', SCILIT_SCRIPT, ...full],
    {
      cwd: CWD,
      maxBuffer: 10 * 1024 * 1024,
      env: { ...process.env, TYPEDB_DATABASE: db || process.env.TYPEDB_DATABASE || 'alh_deep_research' },
    }
  );
  return JSON.parse(stdout);
}

async function runNotebook(args: string[]): Promise<unknown> {
  if (gatewayConfigured()) return runSkill('typedb-notebook', args);
  const { stdout } = await execFileAsync(
    'uv',
    ['run', 'python', NOTEBOOK_SCRIPT, ...args],
    {
      cwd: CWD,
      maxBuffer: 10 * 1024 * 1024,
      env: { ...process.env, TYPEDB_DATABASE: process.env.TYPEDB_DATABASE || 'alh_deep_research' },
    }
  );
  return JSON.parse(stdout);
}

// --- Typed interfaces ---------------------------------------------------------

export interface Corpus {
  id: string;
  name: string;
  description?: string;
  'logical-query'?: string;
}

export interface Paper {
  id: string;
  name?: string;
  doi?: string;
  year?: number;
  'abstract-text'?: string;
  pmid?: string;
  journal?: string;
  'source-uri'?: string;
}

export interface PaperNote {
  id: string;
  name?: string;
  content?: string;
}

export interface PaperDetail {
  success: boolean;
  paper: Paper;
  keywords: string[];
  notes: PaperNote[];
  pdf_artifacts: Array<{ id: string; 'source-uri'?: string; 'cache-path'?: string; 'file-size'?: number }>;
}

export interface MapItem {
  paper_id: string;
  x: number;
  y: number;
  cluster: number;
  title?: string;
  year?: number;
  corpus_ids: string[];
  facets: Record<string, string>;
}

export interface MapData {
  success: boolean;
  count: number;
  num_clusters: number;
  collection_ids: string[];
  items: MapItem[];
}

export interface FacetingNoteSummary {
  id: string;
  name: string;
  has_content: boolean;
  content_preview?: string;
  collections: Array<{ id: string; name: string }>;
}

export interface FacetingNoteDetail {
  success: boolean;
  note_id: string;
  name: string;
  script?: string;
  config?: unknown;
  content?: string;
  plot_code?: string;   // Observable Plot expression (also inside config)
}

export interface InvestigationCorpusRef {
  id: string;
  name?: string;
}

export interface InvestigationPaperRef {
  id: string;
  name?: string;
  doi?: string;
  year?: number;
}

export interface InvestigationSummary {
  id: string;
  name?: string;
  purpose?: string;
  status?: string;
  type?: string;
  'created-at'?: string;
  corpus?: InvestigationCorpusRef | null;
  focal_paper?: InvestigationPaperRef | null;
  phase_count?: number;
  iteration_count?: number;
}

export interface BundleSummary {
  id: string;
  name?: string;
  paper?: InvestigationPaperRef | null;
  observation_count?: number;
  reported_claim_count?: number;
  reported_gap_count?: number;
}

export interface InvestigationPhase {
  id: string;
  name?: string;
  content?: string;
  phase: string;
  iteration?: number;
  'created-at'?: string;
  faceting_notes?: Array<{ id: string; name?: string }>;
  bundles?: BundleSummary[];        // sensemaking stage only
}

// An evidence WARRANT: reasoned argument + confidence, grounded in reported-claims
// and/or in the structured template INSTANCES (their data rows) it rests on.
export interface WarrantNode {
  id: string;
  argument?: string;
  confidence?: number;
  evidence_type?: string;
  grounds?: Array<{ id: string; statement?: string }>;
  grounding_instances?: Array<{ id: string; name?: string; bundle?: string; paper?: string }>;
}

export interface SynthesizedClaimNode {
  id: string;
  type?: string;
  statement?: string;
  evidence?: WarrantNode[];
}

export interface ImpactNode {
  id: string;
  impact_type?: string;
  impact_summary?: string;
  citing_paper?: InvestigationPaperRef | null;
}

export interface InvestigationDetail {
  success: boolean;
  id: string;
  name?: string;
  purpose?: string;
  status?: string;
  type?: string;
  iteration?: number;
  'created-at'?: string;
  grounding_policy?: unknown;
  corpus?: InvestigationCorpusRef | null;
  focal_paper?: InvestigationPaperRef | null;
  phases: InvestigationPhase[];
  synthesized_claims?: SynthesizedClaimNode[];
  citation_impacts?: ImpactNode[];
  papers?: InvestigationPaperRef[];
  collection?: { id: string; name?: string; count?: number };
}

// --- Per-paper sensemaking bundle detail ---
export interface KefedVariable { name?: string; role?: string; values?: string }
export interface KefedFrame { id: string; name?: string; variables?: KefedVariable[] }
export interface ObservationNode {
  id: string;
  name?: string;
  content?: string;
  knowledge_level?: string;
  bio_scale?: string;
  kefed_frame?: KefedFrame | null;
}
export interface ReportedClaimNode {
  id: string;
  type?: string;
  statement?: string;
  cites?: InvestigationPaperRef[];
}
export interface ReportedGapNode { id: string; name?: string; goal?: string }
// --- KEfED / OOEVV protocol graph ---
// Curation standard: elements carry a plain-English definition + (for abbreviations) a long_form.
export interface OoevvScale { id: string; type?: string; unit?: string; values?: string[] }
export interface OoevvQualityRef {
  quality?: string;
  definition?: string;
  long_form?: string;
  quality_id?: string;
  curie?: string;
  grounding_state?: string;
}
export interface OoevvEntityRef { id: string; name?: string; definition?: string; long_form?: string }
export interface OoevvVarBrief {
  id: string;
  name?: string;
  role?: string;
  definition?: string;
  long_form?: string;
  quality?: OoevvQualityRef;
  scale?: OoevvScale;
  target_entity?: OoevvEntityRef | null;
}
export interface OoevvProcess {
  id: string;
  name?: string;
  type?: string;            // assay | material-processing | data-transformation
  parent?: string | null;
  definition?: string;
  long_form?: string;
  inputs?: string[];
  outputs?: string[];
  parameters?: OoevvVarBrief[];
  measurements?: OoevvVarBrief[];
}
export interface ExperimentGraph { id: string; name?: string; experiment?: { id: string; processes?: OoevvProcess[] } }

// --- KEfED templates / instances / data spreadsheet ---
export interface OoevvSlot { id: string; role?: string; kind?: string; definition?: string; long_form?: string }
export interface TemplateDetail {
  id: string;
  name?: string;
  definition?: string;
  long_form?: string;
  slots?: OoevvSlot[];
  variables?: OoevvVarBrief[];
  graph?: { id: string; processes?: OoevvProcess[] };
}
export interface SlotBinding {
  slot: string; role?: string; kind?: string;
  entity_id: string; entity?: string;
  entity_long_form?: string; entity_definition?: string;
}
export interface DatumCell { variable: string; name?: string; role?: string; value?: string; number?: number }
export interface DatumRow {
  id: string;
  cells: DatumCell[];
  observation?: { id: string; name?: string; content?: string };
}
export interface InstanceDetail {
  id: string;
  name?: string;
  template?: { id: string; name?: string } | null;
  template_detail?: TemplateDetail | null;
  bindings?: SlotBinding[];
  data?: DatumRow[];
}

export interface BundleDetail {
  success: boolean;
  id: string;
  name?: string;
  paper?: InvestigationPaperRef | null;
  observations?: ObservationNode[];
  reported_claims?: ReportedClaimNode[];
  reported_gaps?: ReportedGapNode[];
  mechanisms?: Array<{ source?: string; target?: string; type?: string }>;
  experiments?: ExperimentGraph[];
  instances?: InstanceDetail[];
}

// --- Read endpoints (scilit CLI) ----------------------------------------------

export async function listCorpora(): Promise<{ collections: Corpus[]; count: number }> {
  return runScilit(['list-collections']) as Promise<{ collections: Corpus[]; count: number }>;
}

export async function listPapers(collectionId: string): Promise<{ papers: Paper[]; count: number; collection: string }> {
  return runScilit(['list', '--collection', collectionId]) as Promise<{
    papers: Paper[];
    count: number;
    collection: string;
  }>;
}

export async function getPaper(id: string, db?: string): Promise<PaperDetail> {
  return runScilit(['show', '--id', id], db) as Promise<PaperDetail>;
}

// --- Database switcher ---------------------------------------------------------
export interface DatabaseInfo { name: string; hasScilit: boolean; investigations: number; papers: number }
export interface DatabaseList { success: boolean; databases: string[]; info?: DatabaseInfo[] }
export async function listDatabases(): Promise<DatabaseList> {
  return runScilit(['list-databases']) as Promise<DatabaseList>;
}

export async function getMap(opts?: { collectionIds?: string[]; all?: boolean; minClusterSize?: number }): Promise<MapData> {
  const args = ['map'];
  if (opts?.all) {
    args.push('--all');
  } else if (opts?.collectionIds) {
    for (const cid of opts.collectionIds) args.push('--collection', cid);
  }
  if (opts?.minClusterSize !== undefined) args.push('--min-cluster-size', String(opts.minClusterSize));
  return runScilit(args) as Promise<MapData>;
}

// --- Faceting-note endpoints (core typedb-notebook CLI) -----------------------

export async function listFacetingNotes(): Promise<{ notes: FacetingNoteSummary[]; count: number }> {
  return runNotebook(['list-pipeline-notes']) as Promise<{ notes: FacetingNoteSummary[]; count: number }>;
}

export async function getFacetingNote(id: string): Promise<FacetingNoteDetail> {
  return runNotebook(['show-pipeline-note', '--id', id]) as Promise<FacetingNoteDetail>;
}

export interface RunResult {
  success: boolean;
  note_id: string;
  // keyed by output name -> { attr, chars }
  outputs_written: Record<string, { attr: string; chars: number }>;
  outputs_not_persisted: Record<string, unknown>;
  plot_code?: string;      // Observable Plot expression to render against `data`
  data?: unknown[];        // terminal output rows for the plot
}

export async function runFacetingNote(id: string): Promise<RunResult> {
  return runNotebook(['run-pipeline-note', '--id', id]) as Promise<RunResult>;
}

// --- Investigation endpoints (scilit CLI) -------------------------------------

export async function listInvestigations(collectionId?: string, db?: string): Promise<{ investigations: InvestigationSummary[]; count: number }> {
  const args = ['list-investigations'];
  if (collectionId) args.push('--collection', collectionId);
  return runScilit(args, db) as Promise<{ investigations: InvestigationSummary[]; count: number }>;
}

export async function getInvestigation(id: string, db?: string): Promise<InvestigationDetail> {
  return runScilit(['show-investigation', '--id', id], db) as Promise<InvestigationDetail>;
}

export async function getBundle(id: string): Promise<BundleDetail> {
  return runScilit(['show-bundle', '--id', id]) as Promise<BundleDetail>;
}

export async function getTemplate(id: string): Promise<TemplateDetail & { success: boolean }> {
  return runScilit(['show-template', '--id', id]) as Promise<TemplateDetail & { success: boolean }>;
}

export async function getInstance(id: string): Promise<InstanceDetail & { success: boolean }> {
  return runScilit(['show-instance', '--id', id]) as Promise<InstanceDetail & { success: boolean }>;
}

export type TemplateListItem = TemplateDetail & { process_count?: number; variable_count?: number; instance_count?: number };
export async function listTemplates(match?: string): Promise<{ success: boolean; count: number; templates: TemplateListItem[] }> {
  const args = ['list-templates'];
  if (match) args.push('--match', match);
  return runScilit(args) as Promise<{ success: boolean; count: number; templates: TemplateListItem[] }>;
}

// --- Ontology browse/search (curated OOEVV vocabulary) ---
export interface OntologyQuality { id: string; name?: string; definition?: string; long_form?: string }
export interface OntologyEntity { id: string; name?: string; kind?: string; definition?: string; long_form?: string }

export async function listQualities(match?: string): Promise<{ success: boolean; count: number; qualities: OntologyQuality[] }> {
  const args = ['list-qualities'];
  if (match) args.push('--match', match);
  return runScilit(args) as Promise<{ success: boolean; count: number; qualities: OntologyQuality[] }>;
}

export async function listEntities(match?: string): Promise<{ success: boolean; count: number; entities: OntologyEntity[] }> {
  const args = ['list-entities'];
  if (match) args.push('--match', match);
  return runScilit(args) as Promise<{ success: boolean; count: number; entities: OntologyEntity[] }>;
}

// Combined ontology keyword search across templates (methods), qualities (measurands), entities (things).
export interface OntologySearch {
  query: string;
  templates: TemplateListItem[];
  qualities: OntologyQuality[];
  entities: OntologyEntity[];
}
export async function searchOntology(q?: string): Promise<OntologySearch> {
  const [t, ql, e] = await Promise.all([listTemplates(q), listQualities(q), listEntities(q)]);
  return { query: q || '', templates: t.templates || [], qualities: ql.qualities || [], entities: e.entities || [] };
}

// --- KQED synthesis (read-only) ---
export interface SynthesisConcept { curie: string; name: string }
export interface SynthesisNote { id: string; statement: string; stance: 'consensus' | 'contested' | 'emerging'; concepts: SynthesisConcept[] }
export interface MechEdge { s_name: string; s_curie: string; o_name: string; o_curie: string; predicate: string; mech_type: string }
export interface SynthesisView {
  success: boolean;
  investigation: string;
  question: string | null;
  synthesis: SynthesisNote[];
  edges: MechEdge[];
}

export async function getSynthesis(id: string): Promise<SynthesisView> {
  return runScilit(['show-synthesis', '--id', id]) as Promise<SynthesisView>;
}

export interface WorklistItem {
  id: string;
  name: string;
  doi: string | null;
  doi_url: string | null;
  status: 'needed' | 'held' | 'ingested' | 'rhetorical-done' | 'sensemade';
  genre: 'primary' | 'review' | 'unknown' | null;
  load: number;
  journal: string | null;
  year: number | null;
  ref_numbers: number[];
}

export interface AcquisitionWorklist {
  success: boolean;
  citing_paper: string;
  summary: Record<string, number>;
  total: number;
  items: WorklistItem[];
}

export async function getAcquisitionWorklist(citing?: string): Promise<AcquisitionWorklist> {
  const args = ['acquisition-worklist'];
  if (citing) args.push('--citing', citing);
  return runScilit(args) as Promise<AcquisitionWorklist>;
}

// --- Stage view (investigation-centric IA) ------------------------------------

export interface IngestPaper {
  id: string;
  name?: string;
  doi?: string;
  year?: number;
  acquisition_status?: string;
  fulltextPresent?: boolean;
  corpus?: string;
  pdfFilename?: string;
}

// One investigation stage (scilit-investigation-phase), kind-dispatched payload.
export interface StageDetail {
  success: boolean;
  id: string;
  name?: string;
  content?: string;
  kind: string;                       // discovery | ingest | sensemaking | analysis | report
  investigation?: { id: string; name?: string; iteration?: number } | null;
  corpora?: Corpus[];                 // discovery + ingest
  papers?: IngestPaper[];             // ingest
  bundles?: BundleSummary[];          // sensemaking
  pipeline_notes?: Array<{ id: string; name?: string }>; // analysis
  synthesized_claims?: SynthesizedClaimNode[]; // report
  citation_impacts?: ImpactNode[];             // report
}

export async function getStage(phaseId: string, db?: string): Promise<StageDetail> {
  return runScilit(['show-stage', '--id', phaseId], db) as Promise<StageDetail>;
}

// --- Single-paper curation walkthrough payload --------------------------------

export interface Fragment { id: string; content?: string; offset?: number; length?: number; kind?: string }
export interface Derivation { note: string; frag: string; offset?: number; quote?: string }
export interface CurationSpine { id: string; name?: string; iteration?: number; phase?: string }
export interface SignatureIndexRef { id: string; name?: string; role?: string }
export type DataSignature = Record<string, { name?: string; index?: SignatureIndexRef[] }>;

export interface PaperCurationDetail {
  success: boolean;
  hasCuration: boolean;
  paper: Paper & { acquisition_status?: string };
  fulltext?: { id: string; 'cache-path'?: string; 'file-size'?: number; format?: string; 'source-uri'?: string } | null;
  bundle_id?: string;
  spine?: CurationSpine | null;
  fragments?: Fragment[];
  derivations?: Derivation[];
  claim_observations?: Array<{ claim: string; observation: string }>;
  bundle?: BundleDetail;
  signatures?: Record<string, DataSignature>;   // keyed by kefed-model id
}

export async function getPaperCuration(paperId: string, db?: string): Promise<PaperCurationDetail> {
  return runScilit(['show-paper-curation', '--id', paperId], db) as Promise<PaperCurationDetail>;
}

// --- Sensemaking linter (curation checks) -------------------------------------
export interface SensemakingCheck {
  id: string;
  name: string;
  category: string;      // rhetoric | kefed | ooevv | fulltext
  severity: string;      // high | medium | low
  status: 'pass' | 'warn' | 'fail';
  detail: string;
  offenders: string[];
}
export interface SensemakingChecks {
  success: boolean;
  hasCuration: boolean;
  paper: string;
  bundle_id?: string;
  checks: SensemakingCheck[];
  summary: { passed: number; warned: number; failed: number };
}
export async function getSensemakingChecks(paperId: string, db?: string): Promise<SensemakingChecks> {
  return runScilit(['lint-sensemaking', '--id', paperId], db) as Promise<SensemakingChecks>;
}
