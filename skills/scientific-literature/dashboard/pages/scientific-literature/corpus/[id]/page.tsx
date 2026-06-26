import { CorpusDetail } from '@/components/scientific-literature/corpus-detail';

export default async function CorpusPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <CorpusDetail id={id} />;
}
