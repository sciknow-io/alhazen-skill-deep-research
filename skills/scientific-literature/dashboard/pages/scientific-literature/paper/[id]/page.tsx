import { PaperDetail } from '@/components/scientific-literature/paper-detail';

export default async function PaperPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <PaperDetail id={id} />;
}
