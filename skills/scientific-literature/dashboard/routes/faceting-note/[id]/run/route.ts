import { NextResponse } from 'next/server';
import { runFacetingNote } from '@/lib/scientific-literature';

export async function POST(req: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const db = new URL(req.url).searchParams.get('db') || undefined;
    const data = await runFacetingNote(id, db);
    return NextResponse.json(data);
  } catch (error) {
    console.error('runFacetingNote error:', error);
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}
