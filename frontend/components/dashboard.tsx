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
  const grouped = new Map<string, number>();
  for (const point of points) {
    const day = point.day.slice(0, 10);
    grouped.set(day, (grouped.get(day) || 0) + point.total_tokens);
  }
  const rows = [...grouped.entries()];
  const max = Math.max(...rows.map(([, value]) => value), 1);
  return (
    <section className="rounded-2xl border border-line bg-white p-5">
      <h2 className="font-display text-2xl">Tokens by day</h2>
      <div className="mt-6 flex h-48 items-end gap-3">
        {rows.map(([day, value]) => (
          <div key={day} className="flex flex-1 flex-col items-center gap-2">
            <div className="flex w-full flex-1 items-end">
              <div className="w-full rounded-t-lg bg-moss" style={{ height: `${Math.max(8, (value / max) * 100)}%` }} />
            </div>
            <span className="text-[11px] text-mist">{day.slice(5)}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
