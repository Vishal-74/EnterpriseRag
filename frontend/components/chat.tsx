"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

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
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const stored = window.localStorage.getItem("meridian-provider");
    if (stored && ["gemini", "huggingface"].includes(stored)) setProvider(stored);
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

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const message = draft.trim();
    if (!message || sending) return;
    const tempUserMsg: Message = {
      id: `temp-${Date.now()}`,
      role: "user",
      content: message,
      created_at: new Date().toISOString(),
      citations: [],
      metadata: {},
    };
    setMessages((current) => [...current, tempUserMsg]);
    setDraft("");
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
      if (!conversationId) {
        router.push(`/chat/${response.conversation_id}`);
      } else {
        load();
      }
      if (response.citations?.length) {
        setActiveCitation(response.citations[0]);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The question failed.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="grid h-[calc(100vh-6.5rem)] gap-4 overflow-hidden lg:grid-cols-[250px_1fr_320px]">
      {/* 1. Left Sidebar: History */}
      <aside className="flex h-full flex-col overflow-hidden rounded-2xl border border-line bg-white p-4 shadow-sm">
        <div className="border-b border-line/60 pb-3">
          <div className="flex items-center justify-between">
            <h1 className="font-display text-2xl text-ink">Ask</h1>
            <span className="rounded-full bg-paper px-2 py-0.5 text-[11px] font-medium text-mist">Chat</span>
          </div>
          <Link
            className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-xl bg-ink px-3 py-2 text-xs font-medium text-paper transition-opacity hover:opacity-90"
            href="/chat"
          >
            <span>+ New conversation</span>
          </Link>
        </div>
        <div className="mt-3 flex items-center justify-between px-1 text-[11px] font-semibold uppercase tracking-wider text-mist">
          <span>Recent chats</span>
          <span className="text-[10px]">{conversations.length}</span>
        </div>
        <div className="mt-2 flex-1 space-y-1 overflow-y-auto pr-1">
          {conversations.length === 0 && !loading ? (
            <p className="px-2 py-4 text-center text-xs text-mist">No conversations yet.</p>
          ) : null}
          {conversations.map((conversation) => (
            <Link
              key={conversation.id}
              href={`/chat/${conversation.id}`}
              className={`block truncate rounded-xl px-3 py-2 text-xs transition-colors ${
                conversation.id === conversationId
                  ? "bg-ink font-medium text-paper shadow-sm"
                  : "text-ink hover:bg-paper"
              }`}
              title={conversation.title}
            >
              {conversation.title}
            </Link>
          ))}
        </div>
      </aside>

      {/* 2. Middle Pane: Chatbot conversation thread & input */}
      <section className="flex h-full min-w-0 flex-col overflow-hidden rounded-2xl border border-line bg-white shadow-sm">
        {/* Model & Scope header bar */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line/60 bg-[#faf8f5] px-4 py-2.5 text-xs">
          <div className="flex items-center gap-2">
            <label className="font-medium text-ink">
              Model:
              <select
                className="ml-1.5 rounded-lg border border-line bg-white px-2 py-1 text-xs font-medium"
                value={provider}
                onChange={(event) => setProvider(event.target.value)}
              >
                <option value="gemini">Gemini</option>
                <option value="huggingface">Hugging Face</option>
              </select>
            </label>
          </div>
          <div className="flex max-w-full flex-wrap items-center gap-1.5 overflow-x-auto">
            <span className="text-[11px] text-mist">Scope:</span>
            {documents.length === 0 ? (
              <span className="text-[11px] text-mist">All library documents</span>
            ) : (
              documents.map((document) => {
                const isChecked = selectedDocs.includes(document.id);
                return (
                  <label
                    key={document.id}
                    className={`cursor-pointer rounded-full border px-2 py-0.5 text-[11px] transition-colors ${
                      isChecked
                        ? "border-ink bg-ink text-paper"
                        : "border-line bg-white text-ink hover:bg-paper"
                    }`}
                  >
                    <input
                      className="sr-only"
                      type="checkbox"
                      checked={isChecked}
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
                );
              })
            )}
          </div>
        </div>

        {/* Scrollable messages thread */}
        <div className="flex-1 space-y-4 overflow-y-auto p-4 md:p-6">
          {loading ? <LoadingState label="Loading conversation" /> : null}
          {error ? <ErrorState message={error} onRetry={load} /> : null}
          {!loading && messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center text-center">
              <div className="max-w-md space-y-2 rounded-2xl border border-line/70 bg-[#faf8f5] p-6">
                <p className="font-display text-xl text-ink">Ask the Enterprise Library</p>
                <p className="text-xs text-mist">
                  Answers cite verified document chunks, page numbers, and exact excerpts.
                </p>
                <div className="mt-4 flex flex-col gap-1.5 text-left text-xs">
                  <span className="font-medium text-ink">Try asking:</span>
                  <button
                    type="button"
                    onClick={() => setDraft("What model of backup generator is installed in the facility and what is its rating?")}
                    className="rounded-lg border border-line/60 bg-white px-3 py-1.5 text-mist transition-colors hover:border-ink hover:text-ink"
                  >
                    "What model of backup generator is installed in the facility and what is its rating?"
                  </button>
                  <button
                    type="button"
                    onClick={() => setDraft("What is the required fuel reserve percentage for the generators?")}
                    className="rounded-lg border border-line/60 bg-white px-3 py-1.5 text-mist transition-colors hover:border-ink hover:text-ink"
                  >
                    "What is the required fuel reserve percentage for the generators?"
                  </button>
                </div>
              </div>
            </div>
          ) : null}

          {messages.map((message) => {
            const isUser = message.role === "user";
            return (
              <div key={message.id} className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
                <article
                  className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                    isUser
                      ? "max-w-[80%] rounded-br-sm bg-ink text-paper"
                      : "max-w-[88%] rounded-bl-sm border border-line/70 bg-[#faf8f5] text-ink"
                  }`}
                >
                  <p className="whitespace-pre-wrap">{message.content}</p>

                  {!isUser && message.metadata ? <MessageFlags metadata={message.metadata} /> : null}

                  {!isUser && message.citations?.length ? (
                    <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-line/50 pt-2 text-xs">
                      <span className="text-[11px] font-medium text-mist">Citations:</span>
                      {message.citations.map((citation) => (
                        <button
                          key={citation.chunk_id}
                          className="rounded-full border border-line bg-white px-2.5 py-0.5 text-xs text-ink transition-colors hover:border-ink hover:bg-paper"
                          type="button"
                          onClick={() => setActiveCitation(citation)}
                        >
                          📎 {citation.document_name}
                          {citation.page_start ? ` p.${citation.page_start}` : ""}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </article>
              </div>
            );
          })}
          {sending ? (
            <div className="flex justify-start">
              <div className="flex items-center gap-2.5 rounded-2xl rounded-bl-sm border border-line/70 bg-[#faf8f5] px-4 py-3 text-xs text-ink shadow-sm">
                <span className="relative flex h-2.5 w-2.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-moss opacity-75" />
                  <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-moss" />
                </span>
                <span className="font-medium text-mist animate-pulse">
                  Searching library excerpts and reasoning over verified facts…
                </span>
              </div>
            </div>
          ) : null}
          <div ref={messagesEndRef} />
        </div>

        {/* Fixed Prompt Input Bar at Bottom with Ask button cleanly aligned on right */}
        <form className="border-t border-line/70 bg-white p-3 md:p-4" onSubmit={onSubmit}>
          <div className="relative flex items-center rounded-2xl border border-line bg-paper/40 p-1.5 transition-colors focus-within:border-ink focus-within:bg-white focus-within:ring-1 focus-within:ring-ink">
            <textarea
              rows={1}
              className="max-h-32 min-h-[44px] flex-1 resize-none bg-transparent px-3.5 py-2.5 text-sm text-ink placeholder:text-mist focus:outline-none"
              placeholder="Ask a question about your uploaded documents (Enter to send, Shift+Enter for new line)..."
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void onSubmit(event);
                }
              }}
            />
            <button
              className="flex h-10 shrink-0 items-center justify-center gap-1.5 rounded-xl bg-ink px-5 text-xs font-semibold text-paper transition-opacity hover:opacity-90 disabled:opacity-40"
              disabled={sending || !draft.trim()}
              type="submit"
            >
              <span>{sending ? "Thinking…" : "Ask"}</span>
              {!sending ? <span className="text-sm">➔</span> : null}
            </button>
          </div>
        </form>
      </section>

      {/* 3. Right Sidebar: Sources & Evidence Panel */}
      <aside className="flex h-full flex-col overflow-hidden rounded-2xl border border-line bg-white p-4 shadow-sm">
        <div className="flex items-center justify-between border-b border-line/60 pb-3">
          <div>
            <h2 className="font-display text-lg text-ink">Source Evidence</h2>
            <p className="text-[11px] text-mist">Verified chunk citations</p>
          </div>
          {activeCitation ? (
            <button
              onClick={() => setActiveCitation(null)}
              className="rounded-md border border-line px-2 py-0.5 text-xs text-mist hover:text-ink"
              type="button"
            >
              Clear
            </button>
          ) : null}
        </div>
        <div className="mt-3 flex-1 overflow-y-auto pr-1">
          {activeCitation ? (
            <CitationCard citation={activeCitation} />
          ) : (
            <div className="flex h-full flex-col items-center justify-center text-center text-xs text-mist">
              <span className="text-2xl">📄</span>
              <p className="mt-2 font-medium text-ink">No Source Selected</p>
              <p className="mt-1 text-[11px]">
                Click on any citation pill in an answer to inspect its verified excerpt and chunk location.
              </p>
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}

function MessageFlags({ metadata }: { metadata: Record<string, unknown> }) {
  if (!metadata || Object.keys(metadata).length === 0) return null;
  const insufficient = metadata.insufficient_evidence === true;
  const conflict = metadata.conflict === true;
  const ungrounded = metadata.ungrounded === true;
  const totalTokens = Number(metadata.total_tokens || 0);
  const historyTokens = Number(metadata.history_tokens || 0);
  return (
    <div className="mt-2 space-y-1 text-xs">
      {insufficient ? <p className="text-amber-900 font-medium">Not enough information in the selected documents.</p> : null}
      {conflict ? <p className="text-clay font-medium">Conflict found: {String(metadata.conflict_summary || "")}</p> : null}
      {ungrounded ? <p className="text-red-800 font-medium">The verifier did not support the claims.</p> : null}
      <p className="text-[11px] text-mist">
        {String(metadata.model || "no model")} · {String(metadata.latency_ms || 0)} ms
        {totalTokens > 0 ? ` · ${totalTokens} tokens` : ""}
        {` · ${historyTokens} history tokens`}
      </p>
    </div>
  );
}

function CitationCard({ citation }: { citation: Citation }) {
  return (
    <div className="space-y-3 text-xs">
      <div className="rounded-xl border border-line/60 bg-paper/50 p-3">
        <p className="font-semibold text-ink text-sm break-all">{citation.document_name}</p>
        <p className="mt-1 text-mist text-[11px]">
          {citation.page_start ? `Pages ${citation.page_start}–${citation.page_end || citation.page_start}` : null}
          {citation.section ? ` · ${citation.section}` : null}
          {citation.row_start ? ` · Rows ${citation.row_start}–${citation.row_end}` : null}
        </p>
        {citation.score ? (
          <span className="mt-2 inline-block rounded bg-line/40 px-1.5 py-0.5 text-[10px] text-ink font-medium">
            Score: {citation.score.toFixed(4)}
          </span>
        ) : null}
      </div>
      <div className="rounded-xl border border-line/60 bg-white p-3 shadow-inner">
        <p className="font-medium text-mist uppercase tracking-wider text-[10px] mb-1">Snippet</p>
        <p className="whitespace-pre-wrap leading-relaxed text-ink/90 text-xs">{citation.snippet}</p>
      </div>
    </div>
  );
}
