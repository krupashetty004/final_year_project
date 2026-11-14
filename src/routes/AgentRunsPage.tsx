import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../lib/api';
import { useStoreContext } from '../hooks/useStoreContext';
import { formatIST } from '../lib/formatters';
import { Card, CardContent, CardHeader } from '../components/ui/Card';

interface AgentRunRow {
  id: string;
  agent_type: string;
  model_name: string;
  model_version: string;
  status: string;
  latency_ms: number;
  fallback_used: number;
  fallback_reason: string | null;
  started_at_utc: string;
}

export const AgentRunsPage: React.FC = () => {
  const { activeStoreId } = useStoreContext();

  const { data, isLoading } = useQuery({
    queryKey: ['agent-runs', activeStoreId],
    queryFn: () => apiFetch<{ runs: AgentRunRow[] }>(`/stores/${activeStoreId}/agent-runs`),
    enabled: Boolean(activeStoreId),
  });

  return (
    <Card>
      <CardHeader>
        <h2 className="font-display text-base font-semibold text-slate-900">
          Agent Execution Audit Log (`agent_runs`)
        </h2>
        <p className="text-xs text-slate-500">
          Records inputs, outputs, model versions, latency, and deterministic fallback status for every AI run.
        </p>
      </CardHeader>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-200 bg-slate-50 text-slate-500">
              <tr>
                <th className="py-2.5 px-4 font-medium">Agent</th>
                <th className="py-2.5 px-4 font-medium">Model & Version</th>
                <th className="py-2.5 px-4 font-medium">Status</th>
                <th className="py-2.5 px-4 font-medium text-right">Latency</th>
                <th className="py-2.5 px-4 font-medium">Fallback</th>
                <th className="py-2.5 px-4 font-medium text-right">Started (IST)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {isLoading ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-slate-500">
                    Loading agent runs...
                  </td>
                </tr>
              ) : (data?.runs ?? []).length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-10 text-center text-slate-500">
                    No agent runs executed yet in Stage 1 Foundation. Vision, Forecasting, and Smart Pricing executions will populate this audit table in Stages 3–5.
                  </td>
                </tr>
              ) : (
                (data?.runs ?? []).map((run) => (
                  <tr key={run.id} className="hover:bg-slate-50">
                    <td className="py-2.5 px-4 font-medium text-slate-900">{run.agent_type}</td>
                    <td className="py-2.5 px-4 font-mono-num text-slate-700">
                      {run.model_name} · {run.model_version}
                    </td>
                    <td className="py-2.5 px-4 text-slate-700">{run.status}</td>
                    <td className="py-2.5 px-4 font-mono-num text-right">{run.latency_ms} ms</td>
                    <td className="py-2.5 px-4 text-slate-600">
                      {run.fallback_used ? `Yes (${run.fallback_reason || 'fallback'})` : 'No'}
                    </td>
                    <td className="py-2.5 px-4 font-mono-num text-right text-slate-500">
                      {formatIST(run.started_at_utc)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
};
