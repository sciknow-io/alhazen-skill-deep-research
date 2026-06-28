import { NextResponse } from 'next/server';
import { getTemplate } from '@/lib/scientific-literature';

// GET /api/scientific-literature/template/<id> -> one reusable template (design graph + slots + variables)
export async function GET(req: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const data = await getTemplate(id);
    return NextResponse.json(data);
  } catch (error) {
    console.error('getTemplate error:', error);
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}
