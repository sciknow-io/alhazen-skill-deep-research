import { NextRequest, NextResponse } from 'next/server';
import { listDiseases } from '@/lib/dismech-notebook';

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const category = searchParams.get('category') || undefined;
  const limit = searchParams.get('limit') ? Number(searchParams.get('limit')) : undefined;
  const offset = searchParams.get('offset') ? Number(searchParams.get('offset')) : undefined;

  try {
    const data = await listDiseases(category, limit, offset);
    return NextResponse.json(data);
  } catch (error) {
    console.error('dismech list-diseases error:', error);
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}
