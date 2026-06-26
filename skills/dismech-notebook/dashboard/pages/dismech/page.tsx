'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import Link from 'next/link';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import {
  Search,
  ArrowLeft,
  Dna,
  Brain,
  Heart,
  FlaskConical,
  FileText,
  ChevronLeft,
  ChevronRight,
  Loader2,
} from 'lucide-react';

// ─── Types ────────────────────────────────────────────────────

interface Stats {
  diseases: number;
  mechanisms: number;
  phenotypes: number;
  genetic: number;
  treatments: number;
  evidence_notes: number;
  papers: number;
}

interface Disease {
  name: string;
  id: string;
  category?: string;
  mondo_id?: string;
  mechanism_count?: number;
  phenotype_count?: number;
  treatment_count?: number;
  description?: string;
}

interface SearchResult {
  disease: string;
  match_type: string;
  mechanism?: string;
  category?: string;
}

// ─── Stat Cards ───────────────────────────────────────────────

const statCards = [
  { key: 'diseases', label: 'Diseases', icon: Heart, accent: 'text-cyan-400' },
  { key: 'mechanisms', label: 'Mechanisms', icon: Brain, accent: 'text-blue-400' },
  { key: 'phenotypes', label: 'Phenotypes', icon: Dna, accent: 'text-pink-400' },
  { key: 'evidence_notes', label: 'Evidence', icon: FileText, accent: 'text-amber-400' },
] as const;

// ─── Category Colors ──────────────────────────────────────────

const categoryColors: Record<string, string> = {
  neurological: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
  metabolic: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
  immunological: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30',
  cardiovascular: 'bg-red-500/20 text-red-400 border-red-500/30',
  genetic: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  respiratory: 'bg-green-500/20 text-green-400 border-green-500/30',
  musculoskeletal: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  oncological: 'bg-rose-500/20 text-rose-400 border-rose-500/30',
  dermatological: 'bg-pink-500/20 text-pink-400 border-pink-500/30',
  hematological: 'bg-red-500/20 text-red-300 border-red-500/30',
};

function categoryBadgeClass(category?: string): string {
  if (!category) return 'bg-zinc-500/20 text-zinc-400 border-zinc-500/30';
  return categoryColors[category.toLowerCase()] || 'bg-zinc-500/20 text-zinc-400 border-zinc-500/30';
}

// ─── Page Size ────────────────────────────────────────────────

const PAGE_SIZE = 20;

// ─── Component ────────────────────────────────────────────────

export default function DisMechBrowsePage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [diseases, setDiseases] = useState<Disease[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResult[] | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Fetch stats on mount
  useEffect(() => {
    fetch('/api/dismech-notebook/stats')
      .then(r => r.json())
      .then(setStats)
      .catch(() => {});
  }, []);

  // Fetch disease list
  const fetchDiseases = useCallback((newOffset: number) => {
    setLoading(true);
    fetch(`/api/dismech-notebook/diseases?limit=${PAGE_SIZE}&offset=${newOffset}`)
      .then(r => r.json())
      .then(data => {
        setDiseases(data.diseases || []);
        setTotal(data.total || 0);
        setOffset(newOffset);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchDiseases(0);
  }, [fetchDiseases]);

  // Debounced search
  const handleSearchChange = (value: string) => {
    setSearchQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);

    if (!value.trim()) {
      setSearchResults(null);
      setSearchLoading(false);
      return;
    }

    setSearchLoading(true);
    debounceRef.current = setTimeout(() => {
      fetch(`/api/dismech-notebook/search?q=${encodeURIComponent(value)}&limit=25`)
        .then(r => r.json())
        .then(data => {
          setSearchResults(data.results || []);
          setSearchLoading(false);
        })
        .catch(() => {
          setSearchResults([]);
          setSearchLoading(false);
        });
    }, 300);
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <div className="min-h-screen bg-background text-foreground font-sans">
      {/* Header */}
      <header className="border-b border-border bg-card">
        <div className="max-w-6xl mx-auto px-6 py-5">
          <div className="flex items-center gap-4 mb-4">
            <Link
              href="/"
              className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors font-mono"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              Hub
            </Link>
          </div>
          <div className="mb-1">
            <h1 className="text-2xl font-display tracking-tight text-foreground">
              DisMech Notebook
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Disease Mechanism Knowledge Graph
            </p>
          </div>

          {/* Stats */}
          {stats && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-5">
              {statCards.map(({ key, label, icon: Icon, accent }) => (
                <Card key={key} className="bg-card/60 border-border/60">
                  <CardContent className="flex items-center gap-3 p-3">
                    <Icon className={cn('w-5 h-5 shrink-0', accent)} />
                    <div>
                      <p className="text-lg font-mono font-semibold text-foreground leading-none">
                        {(stats[key as keyof Stats] ?? 0).toLocaleString()}
                      </p>
                      <p className="text-[10px] text-muted-foreground uppercase tracking-wider mt-0.5">
                        {label}
                      </p>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-6 py-6">
        {/* Search Bar */}
        <div className="relative mb-6">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search diseases, mechanisms, genes..."
            value={searchQuery}
            onChange={e => handleSearchChange(e.target.value)}
            className="pl-10 bg-card border-border/60 text-foreground placeholder:text-muted-foreground/60"
          />
          {searchLoading && (
            <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground animate-spin" />
          )}
        </div>

        {/* Search Results */}
        {searchResults !== null ? (
          <div className="space-y-2">
            <p className="text-xs text-muted-foreground font-mono mb-3">
              {searchResults.length} result{searchResults.length !== 1 ? 's' : ''} for &ldquo;{searchQuery}&rdquo;
            </p>
            {searchResults.length === 0 && (
              <p className="text-sm text-muted-foreground italic py-8 text-center">
                No matches found. Try a different search term.
              </p>
            )}
            {searchResults.map((result, i) => (
              <Link
                key={`${result.disease}-${i}`}
                href={`/dismech/disease/${encodeURIComponent(result.disease)}`}
                className="block"
              >
                <Card className="bg-card/60 border-border/40 hover:border-cyan-500/40 transition-colors cursor-pointer">
                  <CardContent className="p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-foreground truncate">
                          {result.disease}
                        </p>
                        {result.mechanism && (
                          <p className="text-xs text-muted-foreground mt-1 truncate">
                            Mechanism: {result.mechanism}
                          </p>
                        )}
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <Badge
                          variant="outline"
                          className="text-[10px] bg-cyan-500/10 text-cyan-400 border-cyan-500/30"
                        >
                          {result.match_type}
                        </Badge>
                        {result.category && (
                          <Badge
                            variant="outline"
                            className={cn('text-[10px]', categoryBadgeClass(result.category))}
                          >
                            {result.category}
                          </Badge>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        ) : (
          /* Disease List */
          <>
            {loading ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 className="w-5 h-5 text-muted-foreground animate-spin" />
                <span className="ml-2 text-sm text-muted-foreground font-mono">Loading...</span>
              </div>
            ) : diseases.length === 0 ? (
              <div className="text-center py-16">
                <FlaskConical className="w-12 h-12 text-muted-foreground/30 mx-auto mb-4" />
                <h2 className="text-lg font-display text-foreground mb-2">No diseases found</h2>
                <p className="text-sm text-muted-foreground max-w-md mx-auto">
                  Use the DisMech skill to curate disease mechanisms, then come back here to browse.
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {diseases.map(disease => (
                  <Link
                    key={disease.id}
                    href={`/dismech/disease/${encodeURIComponent(disease.name)}`}
                    className="block"
                  >
                    <Card className="bg-card/60 border-border/40 hover:border-cyan-500/40 transition-colors cursor-pointer">
                      <CardContent className="p-4">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <p className="text-sm font-medium text-foreground">
                              {disease.name}
                            </p>
                            {disease.description && (
                              <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                                {disease.description.slice(0, 200)}
                                {(disease.description?.length ?? 0) > 200 ? '...' : ''}
                              </p>
                            )}
                            <div className="flex items-center gap-2 mt-2">
                              {disease.mechanism_count != null && disease.mechanism_count > 0 && (
                                <Badge variant="outline" className="text-[10px] bg-blue-500/10 text-blue-400 border-blue-500/30">
                                  <Brain className="w-2.5 h-2.5 mr-0.5" />
                                  {disease.mechanism_count} mechanism{disease.mechanism_count !== 1 ? 's' : ''}
                                </Badge>
                              )}
                              {disease.phenotype_count != null && disease.phenotype_count > 0 && (
                                <Badge variant="outline" className="text-[10px] bg-pink-500/10 text-pink-400 border-pink-500/30">
                                  <Dna className="w-2.5 h-2.5 mr-0.5" />
                                  {disease.phenotype_count} phenotype{disease.phenotype_count !== 1 ? 's' : ''}
                                </Badge>
                              )}
                              {disease.treatment_count != null && disease.treatment_count > 0 && (
                                <Badge variant="outline" className="text-[10px] bg-amber-500/10 text-amber-400 border-amber-500/30">
                                  {disease.treatment_count} treatment{disease.treatment_count !== 1 ? 's' : ''}
                                </Badge>
                              )}
                            </div>
                          </div>
                          <div className="flex items-center gap-2 shrink-0">
                            {disease.category && (
                              <Badge
                                variant="outline"
                                className={cn('text-[10px]', categoryBadgeClass(disease.category))}
                              >
                                {disease.category}
                              </Badge>
                            )}
                            {disease.mondo_id && (
                              <Badge variant="outline" className="text-[10px] bg-zinc-500/10 text-zinc-400 border-zinc-500/30 font-mono">
                                {disease.mondo_id}
                              </Badge>
                            )}
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  </Link>
                ))}

                {/* Pagination */}
                {totalPages > 1 && (
                  <div className="flex items-center justify-between pt-4">
                    <p className="text-xs text-muted-foreground font-mono">
                      {offset + 1}&ndash;{Math.min(offset + PAGE_SIZE, total)} of {total}
                    </p>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={offset === 0}
                        onClick={() => fetchDiseases(Math.max(0, offset - PAGE_SIZE))}
                        className="h-7 px-2 text-xs"
                      >
                        <ChevronLeft className="w-3.5 h-3.5 mr-1" />
                        Previous
                      </Button>
                      <span className="text-xs text-muted-foreground font-mono">
                        {currentPage} / {totalPages}
                      </span>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={offset + PAGE_SIZE >= total}
                        onClick={() => fetchDiseases(offset + PAGE_SIZE)}
                        className="h-7 px-2 text-xs"
                      >
                        Next
                        <ChevronRight className="w-3.5 h-3.5 ml-1" />
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        )}
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
