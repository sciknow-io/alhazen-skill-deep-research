import { NextResponse } from 'next/server';
import { getSynthesis } from '@/lib/scientific-literature';

export async function GET(req: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const data = await getSynthesis(id);
    return NextResponse.json(data);
  } catch (error) {
    console.error('getSynthesis error:', error);
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}
