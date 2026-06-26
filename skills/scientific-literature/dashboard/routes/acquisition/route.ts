import { NextResponse } from 'next/server';
import { getAcquisitionWorklist } from '@/lib/scientific-literature';

export async function GET(req: Request) {
  try {
    const { searchParams } = new URL(req.url);
    const citing = searchParams.get('citing') || undefined;
    const data = await getAcquisitionWorklist(citing);
    return NextResponse.json(data);
  } catch (error) {
    console.error('getAcquisitionWorklist error:', error);
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}
