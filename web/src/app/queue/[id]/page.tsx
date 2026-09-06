import { DraftDetailView } from "@/components/draft/draft-detail-view";

export default async function DraftDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <DraftDetailView id={Number(id)} />;
}
