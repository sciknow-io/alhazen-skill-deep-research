import { NextResponse } from 'next/server';
import { getSensemakingChecks } from '@/lib/scientific-literature';

export async function GET(req: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const db = new URL(req.url).searchParams.get('db') || undefined;
    const data = await getSensemakingChecks(id, db);
    return NextResponse.json(data);
  } catch (error) {
    console.error('getSensemakingChecks error:', error);
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}
