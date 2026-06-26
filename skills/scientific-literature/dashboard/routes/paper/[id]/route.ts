import { NextResponse } from 'next/server';
import { getPaper } from '@/lib/scientific-literature';

export async function GET(req: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const data = await getPaper(id);
    return NextResponse.json(data);
  } catch (error) {
    console.error('getPaper error:', error);
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}
