import { NextResponse } from 'next/server';
import { searchOntology } from '@/lib/scientific-literature';

// GET /api/scientific-literature/ontology?q=<keyword>
// Keyword search across the curated OOEVV vocabulary: methods (templates), measurands
// (qualities), and things (entities). Empty q returns the full ontology.
export async function GET(req: Request) {
  try {
    const { searchParams } = new URL(req.url);
    const q = searchParams.get('q') || undefined;
    const data = await searchOntology(q);
    return NextResponse.json(data);
  } catch (error) {
    console.error('searchOntology error:', error);
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}
