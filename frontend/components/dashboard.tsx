"use client";

import { useCallback, useEffect, useState } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { api } from "@/lib/api";
import type { MetricsSummary, UsagePoint } from "@/lib/types";

export function Dashboard() {
  const [summary, setSummary] = useState<MetricsSummary | null>(null);
  const [series, setSeries] = useState<UsagePoint[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([api.summary(), api.timeseries()])
      .then(([nextSummary, nextSeries]) => {
        setSummary(nextSummary);
        setSeries(nextSeries);
        setError(null);
      })
      .catch((caught: Error) => setError(caught.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <LoadingState label="Loading usage" />;
  if (error || !summary) return <ErrorState message={error || "Usage could not be loaded."} onRetry={load} />;

  const cards = [
    ["Documents", summary.documents],
    ["Conversations", summary.conversations],
    ["Agent runs", summary.agent_runs],
    ["Model calls", summary.requests],
    ["Tokens", summary.total_tokens.toLocaleString()],
    ["Avg latency", `${Math.round(summary.avg_latency_ms)} ms`],
    ["P95 latency", `${Math.round(summary.p95_latency_ms)} ms`],
    ["Error rate", `${Math.round(summary.error_rate * 1000) / 10}%`],
    ["Estimated cost", `$${summary.estimated_cost_usd.toFixed(4)}`],
  ];

  return (
    <div className="space-y-8">
      <header>
        <h1 className="font-display text-4xl">Overview</h1>
        <p className="mt-1 text-mist">Numbers come from your usage log. An empty account shows zeros.</p>
      </header>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {cards.map(([label, value]) => (
          <article key={String(label)} className="rounded-2xl border border-line bg-white px-4 py-4">
            <p className="text-xs uppercase tracking-[0.14em] text-mist">{label}</p>
            <p className="mt-2 font-display text-3xl">{value}</p>
          </article>
        ))}
      </section>
      {series.length === 0 ? (
        <EmptyState title="No model calls yet" body="Ask a question or run the agent and this chart will fill from the log." />
      ) : (
        <TokenChart points={series} />
      )}
    </div>
  );
}

function TokenChart({ points }: { points: UsagePoint[] }) {
  const grouped = new Map<string, { total: number; models: Record<string, number> }>();
  for (const point of points) {
    const day = point.day.slice(0, 10);
    const current = grouped.get(day) || { total: 0, models: {} };
    current.total += point.total_tokens;
    if (point.total_tokens > 0) {
      current.models[point.model] = (current.models[point.model] || 0) + point.total_tokens;
    }
    grouped.set(day, current);
  }
  const rows = [...grouped.entries()];
  const max = Math.max(...rows.map(([, data]) => data.total), 1);
  const totalTokens = rows.reduce((sum, [, d]) => sum + d.total, 0);

  return (
    <section className="rounded-2xl border border-line bg-white p-6 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line/60 pb-4">
        <div>
          <h2 className="font-display text-2xl text-ink">Tokens by day</h2>
          <p className="text-xs text-mist">Daily consumption across all operations and agent runs</p>
        </div>
        <div className="rounded-xl bg-paper px-3 py-1.5 text-sm font-medium text-ink">
          {totalTokens.toLocaleString()} tokens logged
        </div>
      </div>
      <div className="mt-6 flex h-52 items-end justify-start gap-6 overflow-x-auto rounded-xl border border-line/40 bg-[#faf8f5] p-6">
        {rows.map(([day, data]) => {
          const heightPct = Math.max(16, Math.round((data.total / max) * 100));
          return (
            <div key={day} className="flex h-full w-28 flex-col items-center justify-end gap-2">
              <span className="text-xs font-semibold text-ink">
                {data.total > 1000 ? `${(data.total / 1000).toFixed(1)}k` : data.total}
              </span>
              <div className="relative flex h-32 w-14 items-end justify-center rounded-lg bg-line/20 p-1">
                <div
                  className="w-full rounded-md bg-moss transition-all duration-300"
                  style={{ height: `${heightPct}%`, minHeight: "14px" }}
                  title={`${day}: ${data.total.toLocaleString()} tokens`}
                />
              </div>
              <span className="text-xs font-medium text-mist">{day.slice(5)}</span>
            </div>
          );
        })}
      </div>
      {rows.length > 0 && Object.keys(rows[0][1].models).length > 0 ? (
        <div className="mt-4 flex flex-wrap gap-2 text-xs text-mist">
          <span className="font-medium text-ink">By model:</span>
          {Object.entries(rows[0][1].models).map(([model, count]) => (
            <span key={model} className="rounded-md border border-line/60 bg-paper px-2 py-0.5">
              {model}: <strong className="text-ink">{count.toLocaleString()}</strong>
            </span>
          ))}
        </div>
      ) : null}
    </section>
  );
}
