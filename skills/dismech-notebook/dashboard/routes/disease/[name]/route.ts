import { NextRequest, NextResponse } from 'next/server';
import { getDisease } from '@/lib/dismech-notebook';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ name: string }> }
) {
  const { name } = await params;
  const decodedName = decodeURIComponent(name);

  try {
    const data = await getDisease(decodedName);
    if (!data || !data.success) {
      return NextResponse.json({ error: `Disease not found: ${decodedName}` }, { status: 404 });
    }
    return NextResponse.json(data);
  } catch (error) {
    console.error('dismech show-disease error:', error);
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}
