import { NextResponse } from 'next/server';
import { listInvestigations } from '@/lib/scientific-literature';

export async function GET(req: Request) {
  try {
    const { searchParams } = new URL(req.url);
    const collection = searchParams.get('collection') || undefined;
    const data = await listInvestigations(collection);
    return NextResponse.json(data);
  } catch (error) {
    console.error('listInvestigations error:', error);
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}
