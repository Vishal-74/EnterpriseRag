"use client";

import { useCallback, useEffect, useState } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { api } from "@/lib/api";
import type { ActivityRow, UsageRow } from "@/lib/types";

export function Logs() {
  const [usage, setUsage] = useState<UsageRow[]>([]);
  const [activity, setActivity] = useState<ActivityRow[]>([]);
  const [status, setStatus] = useState("");
  const [action, setAction] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([api.usage(status || undefined), api.activity(action || undefined)])
      .then(([nextUsage, nextActivity]) => {
        setUsage(nextUsage.items);
        setActivity(nextActivity.items);
        setError(null);
      })
      .catch((caught: Error) => setError(caught.message))
      .finally(() => setLoading(false));
  }, [status, action]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-8">
      <header>
        <h1 className="font-display text-4xl">Activity</h1>
        <p className="mt-1 text-mist">Model calls and account events for this user.</p>
      </header>
      <div className="flex flex-wrap gap-3 text-sm">
        <label>
          Call status
          <select className="ml-2 rounded-lg border border-line bg-white px-2 py-1" value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="">All</option>
            <option value="success">Success</option>
            <option value="error">Error</option>
          </select>
        </label>
        <label>
          Action
          <input
            className="ml-2 rounded-lg border border-line bg-white px-2 py-1"
            placeholder="chat.answer"
            value={action}
            onChange={(event) => setAction(event.target.value)}
          />
        </label>
      </div>
      {loading ? <LoadingState label="Loading logs" /> : null}
      {error ? <ErrorState message={error} onRetry={load} /> : null}
      {!loading && usage.length === 0 ? <EmptyState title="No model calls" body="Calls appear here after chat, rewrite, or an agent run." /> : null}
      {usage.length > 0 ? (
        <div className="overflow-x-auto rounded-2xl border border-line bg-white">
          <table className="w-full min-w-[860px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-mist">
              <tr>
                <th className="px-3 py-2">Time</th>
                <th className="px-3 py-2">Operation</th>
                <th className="px-3 py-2">Model</th>
                <th className="px-3 py-2">Tokens</th>
                <th className="px-3 py-2">Latency</th>
                <th className="px-3 py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {usage.map((row) => (
                <tr key={row.id} className="border-t border-line">
                  <td className="px-3 py-2">{new Date(row.created_at).toLocaleString()}</td>
                  <td className="px-3 py-2">{row.operation}</td>
                  <td className="px-3 py-2">
                    {row.provider}/{row.model}
                  </td>
                  <td className="px-3 py-2">{row.total_tokens}</td>
                  <td className="px-3 py-2">{row.latency_ms} ms</td>
                  <td className="px-3 py-2">
                    {row.status}
                    {row.error ? `: ${row.error}` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {activity.length > 0 ? (
        <div className="overflow-x-auto rounded-2xl border border-line bg-white">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-mist">
              <tr>
                <th className="px-3 py-2">Time</th>
                <th className="px-3 py-2">Action</th>
                <th className="px-3 py-2">Resource</th>
              </tr>
            </thead>
            <tbody>
              {activity.map((row) => (
                <tr key={row.id} className="border-t border-line">
                  <td className="px-3 py-2">{new Date(row.created_at).toLocaleString()}</td>
                  <td className="px-3 py-2">{row.action}</td>
                  <td className="px-3 py-2">
                    {row.resource_type} {row.resource_id}
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
