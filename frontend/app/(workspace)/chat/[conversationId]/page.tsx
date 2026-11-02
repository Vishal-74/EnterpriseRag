import { Chat } from "@/components/chat";

export default async function ConversationPage({ params }: { params: Promise<{ conversationId: string }> }) {
  const { conversationId } = await params;
  return <Chat conversationId={conversationId} />;
}
