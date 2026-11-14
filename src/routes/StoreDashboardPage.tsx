import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { apiFetch } from '../lib/api';
import { useStoreContext } from '../hooks/useStoreContext';
import { formatINR, formatIST, formatQty } from '../lib/formatters';
import { Card, CardContent, CardHeader } from '../components/ui/Card';
import { Button } from '../components/ui/Button';

interface DashboardPayload {
  store: {
    id: string;
    store_code: string;
    name: string;
    city: string;
    state: string;
    pincode: string;
    is_verified: number;
    default_min_margin_bps: number;
  };
  kpis: {
    total_products: number;
    total_available_units: number;
    low_stock_products: number;
    out_of_stock_products: number;
    reorder_required_products: number;
    expiring_products: number;
    stock_retail_value_paise: number;
    stock_cost_value_paise: number;
  };
  recent_updates: Array<{
    id: string;
    sku_code: string;
    name: string;
    brand: string;
    category: string;
    available_qty: number;
    unit_type: string;
    selling_price_paise: number;
    mrp_paise: number;
    updated_at_utc: string;
  }>;
  sales_series_30d: Array<{
    day: string;
    total_units: number;
    revenue_paise: number;
    festival_tag: string | null;
  }>;
  category_breakdown: Array<{
    category: string;
    sku_count: number;
    total_qty: number;
    retail_value_paise: number;
  }>;
}

interface HealthPayload {
  status: string;
  database_engine: string;
  synthetic_seed: number;
  gemini_configured: boolean;
  table_counts: Record<string, number>;
}

export const StoreDashboardPage: React.FC = () => {
  const { t } = useTranslation();
  const { activeStoreId } = useStoreContext();
  const [aiSummary, setAiSummary] = useState<{
    summary: string;
    provider: string;
    fallback_used: boolean;
  } | null>(null);
  const [loadingSummary, setLoadingSummary] = useState(false);

  const { data: dashboard, isLoading } = useQuery({
    queryKey: ['dashboard', activeStoreId],
    queryFn: () => apiFetch<DashboardPayload>(`/stores/${activeStoreId}/dashboard`),
    enabled: Boolean(activeStoreId),
  });

  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: () => apiFetch<HealthPayload>('/health'),
  });

  const handleGenerateBriefing = async () => {
    if (!activeStoreId) return;
    setLoadingSummary(true);
    try {
      const res = await apiFetch<{ summary: string; provider: string; fallback_used: boolean }>(
        '/ai/explain-summary',
        {
          method: 'POST',
          body: JSON.stringify({ store_id: activeStoreId }),
        },
      );
      setAiSummary(res);
    } finally {
      setLoadingSummary(false);
    }
  };

  if (isLoading || !dashboard) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
          {Array.from({ length: 6 }).map((_, idx) => (
            <div key={idx} className="h-28 rounded-xl border border-slate-200 bg-white animate-pulse" />
          ))}
        </div>
        <div className="h-80 rounded-xl border border-slate-200 bg-white animate-pulse" />
      </div>
    );
  }

  const kpis = [
    {
      label: t('kpi.totalProducts'),
      value: String(dashboard.kpis.total_products),
      sub: `Retail value ${formatINR(dashboard.kpis.stock_retail_value_paise)}`,
      tone: 'text-slate-900',
    },
    {
      label: t('kpi.availableUnits'),
      value: dashboard.kpis.total_available_units.toLocaleString('en-IN', {
        maximumFractionDigits: 1,
      }),
      sub: `Cost value ${formatINR(dashboard.kpis.stock_cost_value_paise)}`,
      tone: 'text-slate-900',
    },
    {
      label: t('kpi.lowStock'),
      value: String(dashboard.kpis.low_stock_products),
      sub: 'At or below reorder point',
      tone: dashboard.kpis.low_stock_products > 0 ? 'text-amber-700' : 'text-emerald-700',
    },
    {
      label: t('kpi.outOfStock'),
      value: String(dashboard.kpis.out_of_stock_products),
      sub: 'Zero available quantity',
      tone: dashboard.kpis.out_of_stock_products > 0 ? 'text-red-700' : 'text-emerald-700',
    },
    {
      label: t('kpi.reorderRequired'),
      value: String(dashboard.kpis.reorder_required_products),
      sub: 'Available + incoming < ROP',
      tone: dashboard.kpis.reorder_required_products > 0 ? 'text-amber-700' : 'text-slate-900',
    },
    {
      label: t('kpi.expiringSoon'),
      value: String(dashboard.kpis.expiring_products),
      sub: 'Batches expiring within 7 days',
      tone: dashboard.kpis.expiring_products > 0 ? 'text-red-700' : 'text-emerald-700',
    },
  ];

  const chartData = dashboard.sales_series_30d.map((d) => ({
    day: d.day.slice(5),
    revenueRupees: Math.round(d.revenue_paise / 100),
    units: d.total_units,
    festival: d.festival_tag,
  }));

  const categoryChartData = dashboard.category_breakdown.map((c) => ({
    category: c.category.replace(' essentials', '').replace(' and ', ' & '),
    valueRupees: Math.round(c.retail_value_paise / 100),
    skus: c.sku_count,
  }));

  return (
    <div className="space-y-6">
      {/* Store Identity & Action Strip */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="font-display text-xl font-bold text-slate-900">
            {dashboard.store.name}
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            {dashboard.store.store_code} · {dashboard.store.city}, {dashboard.store.state}{' '}
            {dashboard.store.pincode} ·{' '}
            {dashboard.store.is_verified ? 'Verified Kirana Partner' : 'Verification Pending'} · Min
            margin {(dashboard.store.default_min_margin_bps / 100).toFixed(1)}%
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Button variant="secondary" size="sm" onClick={handleGenerateBriefing} disabled={loadingSummary}>
            {loadingSummary ? 'Summarizing...' : 'Generate Store Briefing'}
          </Button>
          <Link to="/inventory">
            <Button size="sm">Manage Inventory</Button>
          </Link>
        </div>
      </div>

      {/* Deterministic / Gemini Store Briefing */}
      {aiSummary && (
        <Card>
          <CardContent className="py-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div className="space-y-1">
              <div className="text-xs font-medium text-slate-500">
                Store Briefing · Source: {aiSummary.provider}
                {aiSummary.fallback_used ? ' (Deterministic fallback active)' : ''}
              </div>
              <p className="text-sm text-slate-800">{aiSummary.summary}</p>
            </div>
            <button
              type="button"
              onClick={() => setAiSummary(null)}
              className="text-xs text-slate-500 hover:text-slate-900 shrink-0 self-start sm:self-center"
            >
              Dismiss
            </button>
          </CardContent>
        </Card>
      )}

      {/* 6-Column KPI Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
        {kpis.map((item) => (
          <Card key={item.label}>
            <CardContent className="p-4">
              <div className="text-xs font-medium text-slate-500">{item.label}</div>
              <div className={`mt-2 font-mono-num text-2xl font-semibold ${item.tone}`}>
                {item.value}
              </div>
              <div className="mt-1 text-xs text-slate-500 font-mono-num">{item.sub}</div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2">
          <CardHeader className="flex items-center justify-between">
            <div>
              <h3 className="font-display text-sm font-semibold text-slate-900">
                30-Day Store Revenue & Sales Velocity (Synthetic History)
              </h3>
              <p className="text-xs text-slate-500">
                Aggregated from `sales` table in integer paise, formatted in INR
              </p>
            </div>
            <Link to="/forecasting" className="text-xs font-medium text-teal-700 hover:underline">
              View 180-day series
            </Link>
          </CardHeader>
          <CardContent className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                <XAxis dataKey="day" tick={{ fontSize: 11, fill: '#64748B' }} />
                <YAxis tick={{ fontSize: 11, fill: '#64748B' }} />
                <Tooltip
                  formatter={(value) => [`₹${Number(value ?? 0).toLocaleString('en-IN')}`, 'Revenue']}
                />
                <Area
                  type="monotone"
                  dataKey="revenueRupees"
                  stroke="#0F766E"
                  fill="#CCFBF1"
                  strokeWidth={2}
                />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <h3 className="font-display text-sm font-semibold text-slate-900">
              Stock Value by Grocery Category
            </h3>
            <p className="text-xs text-slate-500">Current on-hand retail valuation (₹)</p>
          </CardHeader>
          <CardContent className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={categoryChartData} layout="vertical" margin={{ left: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                <XAxis type="number" tick={{ fontSize: 10, fill: '#64748B' }} />
                <YAxis
                  type="category"
                  dataKey="category"
                  width={105}
                  tick={{ fontSize: 10, fill: '#475569' }}
                />
                <Tooltip
                  formatter={(value) => [`₹${Number(value ?? 0).toLocaleString('en-IN')}`, 'Retail Value']}
                />
                <Bar dataKey="valueRupees" fill="#0F766E" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* Recent Inventory Updates & Stage 1 18-Table Database Health */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <Card className="xl:col-span-2">
          <CardHeader className="flex items-center justify-between">
            <div>
              <h3 className="font-display text-sm font-semibold text-slate-900">
                Recent Inventory Records
              </h3>
              <p className="text-xs text-slate-500">
                Timestamps stored in UTC and rendered in IST (Asia/Kolkata)
              </p>
            </div>
            <Link to="/inventory" className="text-xs font-medium text-teal-700 hover:underline">
              Open full inventory
            </Link>
          </CardHeader>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-slate-200 bg-slate-50 text-slate-500">
                <tr>
                  <th className="py-2.5 px-4 font-medium">SKU</th>
                  <th className="py-2.5 px-4 font-medium">Product</th>
                  <th className="py-2.5 px-4 font-medium text-right">Available</th>
                  <th className="py-2.5 px-4 font-medium text-right">Selling Price</th>
                  <th className="py-2.5 px-4 font-medium text-right">MRP</th>
                  <th className="py-2.5 px-4 font-medium text-right">Updated (IST)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {dashboard.recent_updates.map((row) => (
                  <tr key={row.id} className="hover:bg-slate-50">
                    <td className="py-2.5 px-4 font-mono-num text-slate-600">{row.sku_code}</td>
                    <td className="py-2.5 px-4 font-medium text-slate-900">{row.name}</td>
                    <td className="py-2.5 px-4 font-mono-num text-right">
                      {formatQty(row.available_qty, row.unit_type)}
                    </td>
                    <td className="py-2.5 px-4 font-mono-num text-right text-slate-900">
                      {formatINR(row.selling_price_paise)}
                    </td>
                    <td className="py-2.5 px-4 font-mono-num text-right text-slate-500">
                      {formatINR(row.mrp_paise)}
                    </td>
                    <td className="py-2.5 px-4 font-mono-num text-right text-slate-500 whitespace-nowrap">
                      {formatIST(row.updated_at_utc)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card>
          <CardHeader>
            <h3 className="font-display text-sm font-semibold text-slate-900">
              Database Schema Audit (18 Tables)
            </h3>
            <p className="text-xs text-slate-500">
              {health ? `${health.database_engine} · Seed ${health.synthetic_seed}` : 'Checking...'}
            </p>
          </CardHeader>
          <CardContent className="p-0">
            <div className="max-h-80 overflow-y-auto divide-y divide-slate-100">
              {health &&
                Object.entries(health.table_counts).map(([table, count]) => (
                  <div
                    key={table}
                    className="flex items-center justify-between px-4 py-2 text-xs"
                  >
                    <span className="font-mono-num text-slate-700">{table}</span>
                    <span className="font-mono-num font-medium text-slate-900">
                      {count.toLocaleString('en-IN')} rows
                    </span>
                  </div>
                ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};
