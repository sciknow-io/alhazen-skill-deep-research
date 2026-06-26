import { NextResponse } from 'next/server';
import { listCorpora, listPapers } from '@/lib/scientific-literature';

export async function GET(req: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const [corpora, papers] = await Promise.all([listCorpora(), listPapers(id)]);
    const corpus = corpora.collections?.find((c) => c.id === id) ?? null;
    return NextResponse.json({ corpus, papers: papers.papers ?? [], count: papers.count ?? 0 });
  } catch (error) {
    console.error('getCorpus error:', error);
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}
