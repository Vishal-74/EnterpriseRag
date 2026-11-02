"use client";

import { useCallback, useEffect, useState } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { api } from "@/lib/api";
import { ClientError, type DocumentItem } from "@/lib/types";

export function Documents() {
  const [items, setItems] = useState<DocumentItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);

  const load = useCallback(() => {
    api
      .documents()
      .then((payload) => {
        setItems(payload.items);
        setError(null);
      })
      .catch((caught: Error) => setError(caught.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!items.some((item) => item.status === "pending" || item.status === "processing")) return;
    const timer = window.setInterval(load, 2000);
    return () => window.clearInterval(timer);
  }, [items, load]);

  async function upload(files: FileList | null) {
    if (!files?.length) return;
    setUploading(true);
    setNotice(null);
    try {
      for (const file of Array.from(files)) {
        try {
          await api.upload(file);
        } catch (caught) {
          if (caught instanceof ClientError && caught.code === "duplicate_document") {
            setNotice(`${file.name} was already uploaded.`);
          } else {
            throw caught;
          }
        }
      }
      load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  }

  async function remove(id: string) {
    await api.removeDocument(id);
    load();
  }

  async function reprocess(id: string) {
    await api.reprocess(id);
    load();
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="font-display text-4xl">Documents</h1>
        <p className="mt-1 text-mist">PDF, TXT, Markdown, and CSV. Processing continues after the upload returns.</p>
      </header>
      <label className="block cursor-pointer rounded-2xl border border-dashed border-moss/40 bg-white px-6 py-10 text-center">
        <input
          className="sr-only"
          type="file"
          multiple
          accept=".pdf,.txt,.md,.csv,text/plain,text/markdown,text/csv,application/pdf"
          onChange={(event) => {
            void upload(event.target.files);
            event.target.value = "";
          }}
        />
        <span className="font-medium">{uploading ? "Uploading…" : "Drop files or click to upload"}</span>
        <span className="mt-1 block text-sm text-mist">10 MB maximum. Duplicate files are rejected.</span>
      </label>
      {notice ? <p className="rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-950">{notice}</p> : null}
      {loading ? <LoadingState label="Loading documents" /> : null}
      {error ? <ErrorState message={error} onRetry={load} /> : null}
      {!loading && !error && items.length === 0 ? (
        <EmptyState title="No documents yet" body="Upload a file to parse, chunk, and embed it." />
      ) : null}
      {!loading && items.length > 0 ? (
        <div className="overflow-x-auto rounded-2xl border border-line bg-white">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-mist">
              <tr>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Size</th>
                <th className="px-4 py-3">Chunks</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id} className="border-t border-line">
                  <td className="px-4 py-3">
                    <div className="font-medium">{item.original_filename}</div>
                    {item.error_message ? <div className="text-xs text-red-700">{item.error_message}</div> : null}
                  </td>
                  <td className="px-4 py-3">
                    <Status value={item.status} />
                  </td>
                  <td className="px-4 py-3">{formatBytes(item.size_bytes)}</td>
                  <td className="px-4 py-3">{item.chunk_count}</td>
                  <td className="px-4 py-3 text-right">
                    <button className="mr-3 underline" type="button" onClick={() => void reprocess(item.id)}>
                      Reprocess
                    </button>
                    <button className="underline" type="button" onClick={() => void remove(item.id)}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}

function Status({ value }: { value: DocumentItem["status"] }) {
  const tone =
    value === "ready" ? "bg-emerald-100 text-emerald-900" : value === "failed" ? "bg-red-100 text-red-900" : "bg-amber-100 text-amber-950";
  return <span className={`rounded-full px-2 py-1 text-xs ${tone}`}>{value}</span>;
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  return `${Math.round((bytes / 1024) * 10) / 10} KB`;
}
