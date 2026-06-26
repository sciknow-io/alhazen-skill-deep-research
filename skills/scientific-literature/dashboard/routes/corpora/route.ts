import { NextResponse } from 'next/server';
import { listCorpora } from '@/lib/scientific-literature';

export async function GET() {
  try {
    const data = await listCorpora();
    return NextResponse.json(data);
  } catch (error) {
    console.error('listCorpora error:', error);
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}
