import { NextResponse } from 'next/server';
import { getStage } from '@/lib/scientific-literature';

export async function GET(req: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const db = new URL(req.url).searchParams.get('db') || undefined;
    const data = await getStage(id, db);
    return NextResponse.json(data);
  } catch (error) {
    console.error('getStage error:', error);
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}
