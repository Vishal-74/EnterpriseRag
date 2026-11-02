"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { api } from "@/lib/api";
import type { AgentRun, DocumentItem } from "@/lib/types";

export function Agent() {
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [task, setTask] = useState("Find the most common system failure causes and give a report");
  const [active, setActive] = useState<AgentRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const load = useCallback(() => {
    Promise.all([api.runs(), api.documents()])
      .then(([nextRuns, nextDocuments]) => {
        setRuns(nextRuns.items);
        setDocuments(nextDocuments.items.filter((item) => item.status === "ready"));
        setError(null);
      })
      .catch((caught: Error) => setError(caught.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const activeId = active?.id;
  const activeStatus = active?.status;

  useEffect(() => {
    if (!activeId || activeStatus !== "running") return;
    const timer = window.setInterval(() => {
      void api.run(activeId).then((next) => {
        setActive(next);
        setRuns((current) => current.map((run) => (run.id === next.id ? next : run)));
      });
    }, 1500);
    return () => window.clearInterval(timer);
  }, [activeId, activeStatus]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setStarting(true);
    setError(null);
    try {
      const run = await api.startRun({ task, document_ids: selected });
      setActive(run);
      load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The agent could not start.");
    } finally {
      setStarting(false);
    }
  }

  const report = active?.final_output?.report;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="font-display text-4xl">Agent</h1>
        <p className="mt-1 text-mist">Search, analysis, and a structured report. Each tool call is stored.</p>
      </header>
      <form className="space-y-3 rounded-2xl border border-line bg-white p-4" onSubmit={onSubmit}>
        <textarea className="min-h-24 w-full rounded-xl border border-line px-3 py-2" value={task} onChange={(event) => setTask(event.target.value)} />
        <div className="flex flex-wrap gap-2 text-sm">
          {documents.map((document) => (
            <label key={document.id} className="rounded-full bg-paper px-2 py-1">
              <input
                className="mr-1"
                type="checkbox"
                checked={selected.includes(document.id)}
                onChange={(event) =>
                  setSelected((current) =>
                    event.target.checked ? [...current, document.id] : current.filter((id) => id !== document.id),
                  )
                }
              />
              {document.original_filename}
            </label>
          ))}
        </div>
        <button className="rounded-full bg-ink px-4 py-2 text-paper disabled:opacity-60" disabled={starting} type="submit">
          {starting ? "Running…" : "Run agent"}
        </button>
      </form>
      {loading ? <LoadingState label="Loading runs" /> : null}
      {error ? <ErrorState message={error} onRetry={load} /> : null}
      {!loading && runs.length === 0 && !active ? (
        <EmptyState title="No runs yet" body="Start a task to see the tool timeline." />
      ) : null}
      {active ? (
        <section className="grid gap-4 min-w-0 max-w-full lg:grid-cols-[1fr_1fr]">
          <ol className="min-w-0 space-y-3">
            {active.steps.map((step) => (
              <li key={step.id} className="min-w-0 overflow-hidden rounded-2xl border border-line bg-white p-4">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium">{step.tool_name}</span>
                  <span className="text-mist">
                    {step.status} · {step.latency_ms} ms
                  </span>
                </div>
                {step.error ? <p className="mt-2 text-sm text-red-800 break-words">{step.error}</p> : null}
                <pre className="mt-2 max-w-full overflow-x-auto rounded bg-paper/60 p-2 text-xs text-mist whitespace-pre-wrap break-all">
                  {JSON.stringify(step.tool_output, null, 2)}
                </pre>
              </li>
            ))}
            {active.status === "running" ? <li className="text-sm text-mist">Waiting for the next step…</li> : null}
          </ol>
          <article className="min-w-0 overflow-hidden rounded-2xl border border-line bg-white p-4">
            <h2 className="font-display text-2xl">{report?.title || "Report"}</h2>
            <p className="mt-2 text-sm text-mist">
              Status {active.status}
              {active.stop_reason ? ` · ${active.stop_reason}` : ""}
              {active.error ? ` · ${active.error}` : ""}
            </p>
            {report ? (
              <div className="mt-4 space-y-3 text-sm break-words">
                <p className="leading-relaxed">{report.summary}</p>
                {report.findings.map((finding, idx) => (
                  <div key={idx} className="rounded-xl border border-line/60 bg-paper/40 p-3">
                    <p className="font-medium text-ink">{finding.statement}</p>
                    {finding.evidence?.length ? (
                      <p className="mt-1 text-xs text-mist break-words">Evidence: {finding.evidence.join("; ")}</p>
                    ) : null}
                  </div>
                ))}
                {report.recommendations.length ? (
                  <div className="rounded-xl border border-line/60 bg-paper/40 p-3">
                    <p className="font-medium text-ink">Recommendations</p>
                    <p className="mt-1 text-xs text-mist">{report.recommendations.join(" ")}</p>
                  </div>
                ) : null}
                {report.gaps.length ? (
                  <div className="rounded-xl border border-line/60 bg-paper/40 p-3">
                    <p className="font-medium text-ink">Identified Gaps</p>
                    <p className="mt-1 text-xs text-mist">{report.gaps.join(" ")}</p>
                  </div>
                ) : null}
              </div>
            ) : (
              <p className="mt-4 text-sm text-mist">The report appears when the run finishes.</p>
            )}
          </article>
        </section>
      ) : null}
      {runs.length > 0 ? (
        <ul className="space-y-2 text-sm">
          {runs.map((run) => (
            <li key={run.id}>
              <button className="underline" type="button" onClick={() => void api.run(run.id).then(setActive)}>
                {run.task.slice(0, 80)} · {run.status}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
