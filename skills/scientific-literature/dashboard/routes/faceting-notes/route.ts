import { NextResponse } from 'next/server';
import { listFacetingNotes } from '@/lib/scientific-literature';

export async function GET() {
  try {
    const data = await listFacetingNotes();
    return NextResponse.json(data);
  } catch (error) {
    console.error('listFacetingNotes error:', error);
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}
