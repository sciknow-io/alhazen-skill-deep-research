import { KqedView } from '@/components/scientific-literature/kqed-view';

export default async function KqedPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <KqedView id={id} />;
}
