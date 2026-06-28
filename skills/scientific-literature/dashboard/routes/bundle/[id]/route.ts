import { NextResponse } from 'next/server';
import { getBundle } from '@/lib/scientific-literature';

export async function GET(req: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const data = await getBundle(id);
    return NextResponse.json(data);
  } catch (error) {
    console.error('getBundle error:', error);
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}
