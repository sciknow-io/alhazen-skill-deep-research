'use client';

import { useState, useEffect, use } from 'react';
import Link from 'next/link';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from '@/components/ui/tabs';
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '@/components/ui/table';
import { cn } from '@/lib/utils';
import {
  ArrowLeft,
  Brain,
  Dna,
  Heart,
  Pill,
  FlaskConical,
  ExternalLink,
  ChevronDown,
  ChevronRight,
  Loader2,
} from 'lucide-react';

// ─── Types ────────────────────────────────────────────────────

interface EvidenceItem {
  pmid?: string;
  support?: string;
  snippet?: string;
  title?: string;
}

interface Mechanism {
  name: string;
  description?: string;
  confidence?: number | string;
  genes?: string[];
  cell_types?: string[];
  processes?: string[];
  downstream?: string[];
  evidence?: EvidenceItem[];
}

interface Phenotype {
  name: string;
  hpo_id?: string;
  frequency?: string;
  severity?: string;
  onset?: string;
}

interface GeneticEntry {
  name: string;
  relationship_type?: string;
  association?: string;
  description?: string;
}

interface Treatment {
  name: string;
  description?: string;
}

interface DiseaseInfo {
  name: string;
  description?: string;
  category?: string;
  mondo_id?: string;
}

interface DiseaseDetail {
  disease: DiseaseInfo;
  mechanisms: Mechanism[];
  phenotypes: Phenotype[];
  genetic: GeneticEntry[];
  treatments: Treatment[];
}

// ─── Color Maps ───────────────────────────────────────────────

const supportColors: Record<string, string> = {
  SUPPORT: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  PARTIAL: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
  REFUTE: 'bg-red-500/20 text-red-400 border-red-500/30',
  NO_EVIDENCE: 'bg-zinc-500/20 text-zinc-400 border-zinc-500/30',
  WRONG_STATEMENT: 'bg-red-500/20 text-red-400 border-red-500/30',
};

const tagColors: Record<string, string> = {
  gene: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
  celltype: 'bg-pink-500/20 text-pink-300 border-pink-500/30',
  process: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
  downstream: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/30',
};

const categoryColors: Record<string, string> = {
  neurological: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
  metabolic: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
  immunological: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30',
  cardiovascular: 'bg-red-500/20 text-red-400 border-red-500/30',
  genetic: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  respiratory: 'bg-green-500/20 text-green-400 border-green-500/30',
  musculoskeletal: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  oncological: 'bg-rose-500/20 text-rose-400 border-rose-500/30',
};

function categoryBadgeClass(category?: string): string {
  if (!category) return 'bg-zinc-500/20 text-zinc-400 border-zinc-500/30';
  return categoryColors[category.toLowerCase()] || 'bg-zinc-500/20 text-zinc-400 border-zinc-500/30';
}

// ─── Evidence Section ─────────────────────────────────────────

function EvidenceSection({ evidence }: { evidence: EvidenceItem[] }) {
  const [open, setOpen] = useState(false);

  if (!evidence || evidence.length === 0) return null;

  return (
    <div className="mt-3 border-t border-border/40 pt-3">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer bg-transparent border-none p-0"
      >
        {open ? (
          <ChevronDown className="w-3.5 h-3.5" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5" />
        )}
        {evidence.length} evidence item{evidence.length !== 1 ? 's' : ''}
      </button>
      {open && (
        <div className="mt-2 space-y-2">
          {evidence.map((ev, i) => (
            <div
              key={i}
              className="bg-background/50 border border-border/30 rounded p-3 text-xs"
            >
              <div className="flex items-center gap-2 mb-1.5">
                {ev.pmid && (
                  <a
                    href={`https://pubmed.ncbi.nlm.nih.gov/${ev.pmid.replace(/^PMID:?/i, '')}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-cyan-400 hover:text-cyan-300 font-mono flex items-center gap-1 transition-colors"
                  >
                    PMID:{ev.pmid.replace(/^PMID:?/i, '')}
                    <ExternalLink className="w-2.5 h-2.5" />
                  </a>
                )}
                {ev.support && (
                  <Badge
                    variant="outline"
                    className={cn(
                      'text-[10px]',
                      supportColors[ev.support.toUpperCase()] || supportColors.NO_EVIDENCE
                    )}
                  >
                    {ev.support}
                  </Badge>
                )}
              </div>
              {ev.title && (
                <p className="text-muted-foreground font-medium mb-1">{ev.title}</p>
              )}
              {ev.snippet && (
                <p className="text-muted-foreground italic leading-relaxed">
                  {ev.snippet}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Mechanism Card ───────────────────────────────────────────

function MechanismCard({ mechanism }: { mechanism: Mechanism }) {
  const confidenceDisplay =
    mechanism.confidence != null
      ? typeof mechanism.confidence === 'number'
        ? `${Math.round(mechanism.confidence * 100)}%`
        : String(mechanism.confidence)
      : null;

  return (
    <Card className="bg-card/60 border-border/40">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-sm font-medium text-foreground">
            {mechanism.name}
          </CardTitle>
          {confidenceDisplay && (
            <Badge
              variant="outline"
              className="text-[10px] bg-cyan-500/10 text-cyan-400 border-cyan-500/30 shrink-0"
            >
              {confidenceDisplay} confidence
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        {mechanism.description && (
          <p className="text-xs text-muted-foreground leading-relaxed mb-3">
            {mechanism.description}
          </p>
        )}

        {/* Tags */}
        <div className="flex flex-wrap gap-1.5">
          {mechanism.genes?.map((gene: Record<string, string> | string, i: number) => {
            const label = typeof gene === 'string' ? gene : (gene.preferred_term || gene.gene || '');
            return (
              <Badge
                key={`gene-${i}-${label}`}
                variant="outline"
                className={cn('text-[10px]', tagColors.gene)}
              >
                <Dna className="w-2.5 h-2.5 mr-0.5" />
                {label}
              </Badge>
            );
          })}
          {mechanism.cell_types?.map((ct, i) => (
            <Badge
              key={`ct-${i}-${ct}`}
              variant="outline"
              className={cn('text-[10px]', tagColors.celltype)}
            >
              {ct}
            </Badge>
          ))}
          {mechanism.processes?.map((proc, i) => (
            <Badge
              key={`proc-${i}-${proc}`}
              variant="outline"
              className={cn('text-[10px]', tagColors.process)}
            >
              {proc}
            </Badge>
          ))}
          {mechanism.downstream?.map((ds, i) => (
            <Badge
              key={`ds-${i}-${ds}`}
              variant="outline"
              className={cn('text-[10px]', tagColors.downstream)}
            >
              {ds}
            </Badge>
          ))}
        </div>

        {/* Evidence */}
        {mechanism.evidence && mechanism.evidence.length > 0 && (
          <EvidenceSection evidence={mechanism.evidence} />
        )}
      </CardContent>
    </Card>
  );
}

// ─── Main Page ────────────────────────────────────────────────

export default function DiseasePage({
  params,
}: {
  params: Promise<{ name: string }>;
}) {
  const { name: rawName } = use(params);
  const name = decodeURIComponent(rawName);

  const [data, setData] = useState<DiseaseDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetch(`/api/dismech-notebook/disease/${encodeURIComponent(name)}`)
      .then(r => {
        if (!r.ok) throw new Error(`API error: ${r.status}`);
        return r.json();
      })
      .then(d => {
        setData(d);
        setLoading(false);
      })
      .catch(err => {
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      });
  }, [name]);

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="w-5 h-5 text-muted-foreground animate-spin" />
        <span className="ml-2 text-sm text-muted-foreground font-mono">Loading...</span>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-background text-foreground font-sans">
        <header className="border-b border-border bg-card px-6 py-4">
          <Link
            href="/dismech"
            className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors font-mono"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            DisMech
          </Link>
        </header>
        <main className="max-w-4xl mx-auto px-6 py-16 text-center">
          <p className="text-red-400">{error || 'Disease not found'}</p>
        </main>
      </div>
    );
  }

  const { disease, mechanisms, phenotypes, genetic, treatments } = data;
  const mondoUrl = disease.mondo_id
    ? `https://purl.obolibrary.org/obo/${disease.mondo_id.replace(':', '_')}`
    : null;

  return (
    <div className="min-h-screen bg-background text-foreground font-sans flex flex-col">
      {/* Header */}
      <header className="border-b border-border bg-card">
        <div className="max-w-6xl mx-auto px-6 py-5">
          <Link
            href="/dismech"
            className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors font-mono mb-4"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            DisMech
          </Link>

          <h1 className="text-2xl font-display tracking-tight text-foreground mb-2">
            {disease.name}
          </h1>

          <div className="flex items-center gap-2 flex-wrap mb-3">
            {disease.category && (
              <Badge
                variant="outline"
                className={cn('text-xs', categoryBadgeClass(disease.category))}
              >
                {disease.category}
              </Badge>
            )}
            {disease.mondo_id && (
              mondoUrl ? (
                <a href={mondoUrl} target="_blank" rel="noopener noreferrer">
                  <Badge
                    variant="outline"
                    className="text-xs bg-zinc-500/10 text-zinc-400 border-zinc-500/30 font-mono hover:text-cyan-400 hover:border-cyan-500/30 transition-colors cursor-pointer"
                  >
                    {disease.mondo_id}
                    <ExternalLink className="w-2.5 h-2.5 ml-1" />
                  </Badge>
                </a>
              ) : (
                <Badge
                  variant="outline"
                  className="text-xs bg-zinc-500/10 text-zinc-400 border-zinc-500/30 font-mono"
                >
                  {disease.mondo_id}
                </Badge>
              )
            )}
          </div>

          {disease.description && (
            <p className="text-sm text-muted-foreground leading-relaxed max-w-3xl">
              {disease.description}
            </p>
          )}

          {/* Summary counts */}
          <div className="flex items-center gap-4 mt-4 text-xs text-muted-foreground font-mono">
            {mechanisms.length > 0 && (
              <span className="flex items-center gap-1">
                <Brain className="w-3.5 h-3.5 text-blue-400" />
                {mechanisms.length} mechanism{mechanisms.length !== 1 ? 's' : ''}
              </span>
            )}
            {phenotypes.length > 0 && (
              <span className="flex items-center gap-1">
                <Dna className="w-3.5 h-3.5 text-pink-400" />
                {phenotypes.length} phenotype{phenotypes.length !== 1 ? 's' : ''}
              </span>
            )}
            {genetic.length > 0 && (
              <span className="flex items-center gap-1">
                <FlaskConical className="w-3.5 h-3.5 text-cyan-400" />
                {genetic.length} genetic
              </span>
            )}
            {treatments.length > 0 && (
              <span className="flex items-center gap-1">
                <Pill className="w-3.5 h-3.5 text-amber-400" />
                {treatments.length} treatment{treatments.length !== 1 ? 's' : ''}
              </span>
            )}
          </div>
        </div>
      </header>

      {/* Tabbed Content */}
      <main className="max-w-6xl mx-auto px-6 py-6 flex-1 w-full">
        <Tabs defaultValue="pathophysiology">
          <TabsList variant="line" className="mb-6">
            <TabsTrigger value="pathophysiology" className="gap-1.5">
              <Brain className="w-3.5 h-3.5" />
              Pathophysiology
              {mechanisms.length > 0 && (
                <span className="text-[10px] text-muted-foreground ml-1">
                  ({mechanisms.length})
                </span>
              )}
            </TabsTrigger>
            <TabsTrigger value="phenotypes" className="gap-1.5">
              <Dna className="w-3.5 h-3.5" />
              Phenotypes
              {phenotypes.length > 0 && (
                <span className="text-[10px] text-muted-foreground ml-1">
                  ({phenotypes.length})
                </span>
              )}
            </TabsTrigger>
            <TabsTrigger value="genetic" className="gap-1.5">
              <FlaskConical className="w-3.5 h-3.5" />
              Genetic
              {genetic.length > 0 && (
                <span className="text-[10px] text-muted-foreground ml-1">
                  ({genetic.length})
                </span>
              )}
            </TabsTrigger>
            <TabsTrigger value="treatments" className="gap-1.5">
              <Pill className="w-3.5 h-3.5" />
              Treatments
              {treatments.length > 0 && (
                <span className="text-[10px] text-muted-foreground ml-1">
                  ({treatments.length})
                </span>
              )}
            </TabsTrigger>
          </TabsList>

          {/* Pathophysiology Tab */}
          <TabsContent value="pathophysiology">
            {mechanisms.length === 0 ? (
              <EmptyState
                icon={<Brain className="w-10 h-10" />}
                message="No mechanisms curated yet for this disease."
              />
            ) : (
              <div className="space-y-3">
                {mechanisms.map((mech, i) => (
                  <MechanismCard key={`${mech.name}-${i}`} mechanism={mech} />
                ))}
              </div>
            )}
          </TabsContent>

          {/* Phenotypes Tab */}
          <TabsContent value="phenotypes">
            {phenotypes.length === 0 ? (
              <EmptyState
                icon={<Dna className="w-10 h-10" />}
                message="No phenotypes recorded for this disease."
              />
            ) : (
              <Card className="bg-card/60 border-border/40">
                <CardContent className="p-0">
                  <Table>
                    <TableHeader>
                      <TableRow className="border-border/40">
                        <TableHead className="text-xs">Name</TableHead>
                        <TableHead className="text-xs">HPO ID</TableHead>
                        <TableHead className="text-xs">Frequency</TableHead>
                        <TableHead className="text-xs">Severity</TableHead>
                        <TableHead className="text-xs">Onset</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {phenotypes.map((ph, i) => (
                        <TableRow key={i} className="border-border/30">
                          <TableCell className="text-sm text-foreground">
                            {ph.name}
                          </TableCell>
                          <TableCell>
                            {ph.hpo_id ? (
                              <a
                                href={`https://hpo.jax.org/browse/term/${ph.hpo_id}`}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-xs text-cyan-400 hover:text-cyan-300 font-mono flex items-center gap-1 transition-colors"
                              >
                                {ph.hpo_id}
                                <ExternalLink className="w-2.5 h-2.5" />
                              </a>
                            ) : (
                              <span className="text-xs text-muted-foreground">-</span>
                            )}
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            {ph.frequency || '-'}
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            {ph.severity || '-'}
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            {ph.onset || '-'}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            )}
          </TabsContent>

          {/* Genetic Tab */}
          <TabsContent value="genetic">
            {genetic.length === 0 ? (
              <EmptyState
                icon={<FlaskConical className="w-10 h-10" />}
                message="No genetic associations recorded for this disease."
              />
            ) : (
              <Card className="bg-card/60 border-border/40">
                <CardContent className="p-0">
                  <Table>
                    <TableHeader>
                      <TableRow className="border-border/40">
                        <TableHead className="text-xs">Gene / Entry</TableHead>
                        <TableHead className="text-xs">Relationship</TableHead>
                        <TableHead className="text-xs">Association</TableHead>
                        <TableHead className="text-xs">Description</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {genetic.map((g, i) => (
                        <TableRow key={i} className="border-border/30">
                          <TableCell className="text-sm text-foreground font-medium">
                            {g.name}
                          </TableCell>
                          <TableCell>
                            {g.relationship_type ? (
                              <Badge
                                variant="outline"
                                className="text-[10px] bg-blue-500/10 text-blue-400 border-blue-500/30"
                              >
                                {g.relationship_type}
                              </Badge>
                            ) : (
                              <span className="text-xs text-muted-foreground">-</span>
                            )}
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            {g.association || '-'}
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground max-w-xs truncate">
                            {g.description || '-'}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            )}
          </TabsContent>

          {/* Treatments Tab */}
          <TabsContent value="treatments">
            {treatments.length === 0 ? (
              <EmptyState
                icon={<Pill className="w-10 h-10" />}
                message="No treatments recorded for this disease."
              />
            ) : (
              <div className="space-y-3">
                {treatments.map((tx, i) => (
                  <Card
                    key={`${tx.name}-${i}`}
                    className="bg-card/60 border-border/40"
                  >
                    <CardHeader className="pb-1">
                      <CardTitle className="text-sm font-medium text-foreground flex items-center gap-2">
                        <Pill className="w-3.5 h-3.5 text-amber-400" />
                        {tx.name}
                      </CardTitle>
                    </CardHeader>
                    {tx.description && (
                      <CardContent className="pt-0">
                        <p className="text-xs text-muted-foreground leading-relaxed">
                          {tx.description}
                        </p>
                      </CardContent>
                    )}
                  </Card>
                ))}
              </div>
            )}
          </TabsContent>
        </Tabs>
      </main>

      {/* Footer */}
      <footer className="border-t border-border mt-auto py-4 px-6">
        <p className="text-center text-[10px] text-muted-foreground font-mono tracking-wider">
          dismech-notebook &middot; typedb + next.js
        </p>
      </footer>
    </div>
  );
}

// ─── Empty State ──────────────────────────────────────────────

function EmptyState({
  icon,
  message,
}: {
  icon: React.ReactNode;
  message: string;
}) {
  return (
    <div className="text-center py-16">
      <div className="text-muted-foreground/30 mx-auto mb-4 flex justify-center">
        {icon}
      </div>
      <p className="text-sm text-muted-foreground italic">{message}</p>
    </div>
  );
}
