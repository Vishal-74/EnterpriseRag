"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { api } from "@/lib/api";
import type { Citation, Conversation, DocumentItem, Message } from "@/lib/types";

export function Chat({ conversationId }: { conversationId?: string }) {
  const router = useRouter();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [selectedDocs, setSelectedDocs] = useState<string[]>([]);
  const [provider, setProvider] = useState("gemini");
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeCitation, setActiveCitation] = useState<Citation | null>(null);

  useEffect(() => {
    const stored = window.localStorage.getItem("meridian-provider");
    if (stored && ["gemini", "openai", "anthropic", "huggingface"].includes(stored)) setProvider(stored);
  }, []);

  const load = useCallback(() => {
    setLoading(true);
    const conversation = conversationId ? api.conversation(conversationId) : Promise.resolve(null);
    Promise.all([api.conversations(), api.documents(), conversation])
      .then(([nextConversations, nextDocuments, detail]) => {
        setConversations(nextConversations);
        setDocuments(nextDocuments.items.filter((item) => item.status === "ready"));
        setMessages(detail?.messages || []);
        setError(null);
      })
      .catch((caught: Error) => setError(caught.message))
      .finally(() => setLoading(false));
  }, [conversationId]);

  useEffect(() => {
    load();
  }, [load]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const message = draft.trim();
    if (!message) return;
    setSending(true);
    setError(null);
    window.localStorage.setItem("meridian-provider", provider);
    try {
      const response = await api.ask({
        message,
        conversation_id: conversationId,
        document_ids: selectedDocs,
        provider,
      });
      setDraft("");
      if (!conversationId) {
        router.push(`/chat/${response.conversation_id}`);
      } else {
        load();
      }
      setActiveCitation(response.citations[0] || null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The question failed.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[240px_1fr_280px]">
      <aside>
        <h1 className="font-display text-3xl">Ask</h1>
        <Link className="mt-4 inline-block text-sm underline" href="/chat">
          New conversation
        </Link>
        <div className="mt-4 space-y-2">
          {conversations.length === 0 && !loading ? <p className="text-sm text-mist">No conversations yet.</p> : null}
          {conversations.map((conversation) => (
            <Link
              key={conversation.id}
              href={`/chat/${conversation.id}`}
              className={`block rounded-xl px-3 py-2 text-sm ${
                conversation.id === conversationId ? "bg-ink text-paper" : "bg-white"
              }`}
            >
              {conversation.title}
            </Link>
          ))}
        </div>
      </aside>
      <section className="space-y-4">
        {loading ? <LoadingState label="Loading conversation" /> : null}
        {error ? <ErrorState message={error} onRetry={load} /> : null}
        {!loading && messages.length === 0 ? (
          <EmptyState title="Ask the library" body="Answers cite the document, page or section, and chunk. Missing evidence stays missing." />
        ) : null}
        <div className="space-y-4">
          {messages.map((message) => (
            <article key={message.id} className="rounded-2xl border border-line bg-white px-4 py-3">
              <p className="text-xs uppercase tracking-wide text-mist">{message.role}</p>
              <p className="mt-2 whitespace-pre-wrap">{message.content}</p>
              <MessageFlags metadata={message.metadata} />
              {message.citations?.length ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  {message.citations.map((citation) => (
                    <button
                      key={citation.chunk_id}
                      className="rounded-full bg-paper px-3 py-1 text-xs"
                      type="button"
                      onClick={() => setActiveCitation(citation)}
                    >
                      {citation.document_name}
                      {citation.page_start ? ` p.${citation.page_start}` : ""}
                    </button>
                  ))}
                </div>
              ) : null}
            </article>
          ))}
        </div>
        <form className="space-y-3" onSubmit={onSubmit}>
          <div className="flex flex-wrap gap-3 text-sm">
            <label>
              Model
              <select
                className="ml-2 rounded-lg border border-line bg-white px-2 py-1"
                value={provider}
                onChange={(event) => setProvider(event.target.value)}
              >
                <option value="gemini">Gemini</option>
                <option value="openai">OpenAI</option>
                <option value="anthropic">Claude</option>
                <option value="huggingface">Hugging Face</option>
              </select>
            </label>
            <fieldset className="flex flex-wrap gap-2">
              {documents.map((document) => (
                <label key={document.id} className="rounded-full bg-white px-2 py-1">
                  <input
                    className="mr-1"
                    type="checkbox"
                    checked={selectedDocs.includes(document.id)}
                    onChange={(event) =>
                      setSelectedDocs((current) =>
                        event.target.checked
                          ? [...current, document.id]
                          : current.filter((id) => id !== document.id),
                      )
                    }
                  />
                  {document.original_filename}
                </label>
              ))}
            </fieldset>
          </div>
          <textarea
            className="min-h-24 w-full rounded-2xl border border-line bg-white px-3 py-2"
            placeholder="Ask about the documents you uploaded"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
          />
          <button className="rounded-full bg-ink px-4 py-2 text-paper disabled:opacity-60" disabled={sending} type="submit">
            {sending ? "Thinking…" : "Ask"}
          </button>
        </form>
      </section>
      <aside className="rounded-2xl border border-line bg-white p-4">
        <h2 className="font-display text-xl">Source</h2>
        {activeCitation ? <CitationCard citation={activeCitation} /> : <p className="mt-3 text-sm text-mist">Select a citation to read the snippet.</p>}
      </aside>
    </div>
  );
}

function MessageFlags({ metadata }: { metadata: Record<string, unknown> }) {
  if (!metadata || Object.keys(metadata).length === 0) return null;
  const insufficient = metadata.insufficient_evidence === true;
  const conflict = metadata.conflict === true;
  const ungrounded = metadata.ungrounded === true;
  return (
    <div className="mt-2 space-y-1 text-xs">
      {insufficient ? <p className="text-amber-900">Not enough information in the selected documents.</p> : null}
      {conflict ? <p className="text-clay">Conflict found. {String(metadata.conflict_summary || "")}</p> : null}
      {ungrounded ? <p className="text-red-800">The verifier did not support the claims.</p> : null}
      <p className="text-mist">
        {String(metadata.model || "no model")} · {String(metadata.latency_ms || 0)} ms · history{" "}
        {String(metadata.history_tokens || 0)} tokens
      </p>
    </div>
  );
}

function CitationCard({ citation }: { citation: Citation }) {
  return (
    <div className="mt-3 text-sm">
      <p className="font-medium">{citation.document_name}</p>
      <p className="text-mist">
        {citation.page_start ? `Pages ${citation.page_start}–${citation.page_end || citation.page_start}` : null}
        {citation.section ? ` ${citation.section}` : null}
        {citation.row_start ? ` Rows ${citation.row_start}–${citation.row_end}` : null}
      </p>
      <p className="mt-3 whitespace-pre-wrap">{citation.snippet}</p>
    </div>
  );
}
