import { NextRequest, NextResponse } from 'next/server';
import { searchDiseases } from '@/lib/dismech-notebook';

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const q = searchParams.get('q');
  const limit = searchParams.get('limit') ? Number(searchParams.get('limit')) : undefined;

  if (!q) {
    return NextResponse.json({ error: 'Missing required parameter: q' }, { status: 400 });
  }

  try {
    const data = await searchDiseases(q, limit);
    return NextResponse.json(data);
  } catch (error) {
    console.error('dismech search error:', error);
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}
