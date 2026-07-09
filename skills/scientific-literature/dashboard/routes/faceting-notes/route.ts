import { NextResponse } from 'next/server';
import { listFacetingNotes } from '@/lib/scientific-literature';

export async function GET(req: Request) {
  try {
    const db = new URL(req.url).searchParams.get('db') || undefined;
    const data = await listFacetingNotes(db);
    return NextResponse.json(data);
  } catch (error) {
    console.error('listFacetingNotes error:', error);
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}
