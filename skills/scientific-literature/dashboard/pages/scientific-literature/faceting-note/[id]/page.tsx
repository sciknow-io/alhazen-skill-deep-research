import { FacetingNoteViewer } from '@/components/scientific-literature/faceting-note-viewer';

export default async function FacetingNotePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <FacetingNoteViewer id={id} />;
}
