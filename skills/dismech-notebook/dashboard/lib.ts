import { execFile } from 'child_process';
import { promisify } from 'util';
import path from 'path';
import { runSkill, gatewayConfigured } from '@/lib/skill-gateway';

const execFileAsync = promisify(execFile);

// DISMECH_NOTEBOOK_SKILL_ROOT: absolute path to the dismech-notebook skill directory
// PROJECT_ROOT: absolute path to skillful-alhazen root (used when installed)
const SKILL_ROOT = process.env.DISMECH_NOTEBOOK_SKILL_ROOT;
const PROJECT_ROOT = process.env.PROJECT_ROOT || path.resolve(process.cwd());

const DISMECH_SCRIPT = SKILL_ROOT
  ? path.join(SKILL_ROOT, 'dismech_notebook.py')
  : path.join(PROJECT_ROOT, '.claude/skills/dismech-notebook/dismech_notebook.py');

const CWD = SKILL_ROOT || PROJECT_ROOT;

// Prefer the warm gateway (no per-request Python cold-start); fall back to
// spawning the CLI directly for host dev where no gateway is running.
async function runDismech(args: string[]): Promise<unknown> {
  if (gatewayConfigured()) return runSkill('dismech-notebook', args);
  const { stdout } = await execFileAsync(
    'uv',
    ['run', 'python', DISMECH_SCRIPT, ...args],
    {
      cwd: CWD,
      maxBuffer: 10 * 1024 * 1024,
      env: { ...process.env, TYPEDB_DATABASE: 'alh_deep_research' },
    }
  );
  return JSON.parse(stdout);
}

// Typed interfaces for all API responses

export interface DismechStats {
  success: boolean;
  diseases: number;
  mechanisms: number;
  phenotypes: number;
  genetic: number;
  treatments: number;
  causal_edges: number;
  evidence_notes: number;
  papers: number;
  gene_descriptors: number;
  phenotype_descriptors: number;
  celltype_descriptors: number;
  process_descriptors: number;
}

export interface DiseaseListItem {
  name: string;
  id: string;
  category: string | null;
  mondo_id: string | null;
}

export interface DiseaseListResponse {
  success: boolean;
  total: number;
  offset: number;
  limit: number;
  diseases: DiseaseListItem[];
}

export interface EvidenceItem {
  pmid: string;
  support: string;
  snippet: string | null;
}

export interface MechanismDetail {
  name: string;
  id: string;
  description: string | null;
  confidence: string | null;
  genes: Array<{ gene: string; preferred_term: string }>;
  cell_types: string[];
  processes: string[];
  downstream: string[];
  evidence: EvidenceItem[];
}

export interface PhenotypeItem {
  name: string;
  id: string;
  description: string | null;
  hpo_id: string | null;
  frequency: string | null;
  severity: string | null;
  onset: string | null;
}

export interface GeneticItem {
  name: string;
  id: string;
  description: string | null;
  relationship_type: string | null;
  association: string | null;
}

export interface TreatmentItem {
  name: string;
  id: string;
  description: string | null;
}

export interface DiseaseDetail {
  success: boolean;
  disease: {
    name: string;
    id: string;
    description: string | null;
    category: string | null;
    mondo_id: string | null;
  };
  mechanisms: MechanismDetail[];
  phenotypes: PhenotypeItem[];
  genetic: GeneticItem[];
  treatments: TreatmentItem[];
}

export interface SearchResult {
  disease: string;
  match_type: string;
  mechanism?: string;
  category?: string;
}

export interface SearchResponse {
  success: boolean;
  query: string;
  count: number;
  results: SearchResult[];
}

// Exported functions

export async function getStats(): Promise<DismechStats> {
  return runDismech(['stats']) as Promise<DismechStats>;
}

export async function listDiseases(
  category?: string,
  limit?: number,
  offset?: number
): Promise<DiseaseListResponse> {
  const args = ['list-diseases'];
  if (category) args.push('--category', category);
  if (limit !== undefined) args.push('--limit', String(limit));
  if (offset !== undefined) args.push('--offset', String(offset));
  return runDismech(args) as Promise<DiseaseListResponse>;
}

export async function getDisease(name: string): Promise<DiseaseDetail> {
  return runDismech(['show-disease', '--name', name]) as Promise<DiseaseDetail>;
}

export async function searchDiseases(
  query: string,
  limit?: number
): Promise<SearchResponse> {
  const args = ['search', '--query', query];
  if (limit !== undefined) args.push('--limit', String(limit));
  return runDismech(args) as Promise<SearchResponse>;
}
