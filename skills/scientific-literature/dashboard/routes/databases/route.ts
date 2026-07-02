import { NextResponse } from 'next/server';
import { listDatabases } from '@/lib/scientific-literature';

export async function GET() {
  try {
    const data = await listDatabases();
    return NextResponse.json(data);
  } catch (error) {
    console.error('listDatabases error:', error);
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}
