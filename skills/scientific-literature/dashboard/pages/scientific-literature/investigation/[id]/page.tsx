import { InvestigationShell } from '@/components/scientific-literature/investigation-shell';

export default async function InvestigationPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <InvestigationShell id={id} />;
}
