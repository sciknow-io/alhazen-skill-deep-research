import { NextResponse } from 'next/server';
import { getMap } from '@/lib/scientific-literature';

export async function GET(req: Request) {
  try {
    const url = new URL(req.url);
    const all = url.searchParams.get('all') === 'true';
    const collectionIds = url.searchParams.getAll('collection');
    const mcsParam = url.searchParams.get('minClusterSize');
    const minClusterSize = mcsParam ? Number(mcsParam) : undefined;
    const data = await getMap({
      all: all || collectionIds.length === 0,
      collectionIds: collectionIds.length > 0 ? collectionIds : undefined,
      minClusterSize,
    });
    return NextResponse.json(data);
  } catch (error) {
    console.error('getMap error:', error);
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}
