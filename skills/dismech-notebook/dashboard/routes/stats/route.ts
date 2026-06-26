import { NextResponse } from 'next/server';
import { getStats } from '@/lib/dismech-notebook';

export async function GET() {
  try {
    const data = await getStats();
    return NextResponse.json(data);
  } catch (error) {
    console.error('dismech stats error:', error);
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}
