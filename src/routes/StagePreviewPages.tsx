import React from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { apiFetch } from '../lib/api';
import { useStoreContext } from '../hooks/useStoreContext';
import { formatINR, formatISTDate, formatQty } from '../lib/formatters';
import { Card, CardContent, CardHeader } from '../components/ui/Card';
import { Button } from '../components/ui/Button';

const StageNotice: React.FC<{ stage: string; summary: string }> = ({ stage, summary }) => (
  <div className="rounded-xl border border-slate-200 bg-white px-5 py-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
    <div>
      <div className="text-xs font-medium text-teal-800">{stage}</div>
      <p className="text-sm text-slate-700 mt-0.5">{summary}</p>
    </div>
    <Link to="/inventory" className="shrink-0">
      <Button variant="secondary" size="sm">
        Open Active Inventory
      </Button>
    </Link>
  </div>
);

type ShelfCandidate = { product_id: string; sku_code: string; name: string; brand: string; score: number };
type ShelfDetection = {
  detected_product_id: string;
  detector_label: string;
  detection_confidence: number;
  ocr_text: string;
  top_matches: ShelfCandidate[];
  is_unknown: boolean;
};
type ShelfAnalysis = {
  upload_id: string;
  status: string;
  detected_count: number;
  vision: { detections: ShelfDetection[]; owner_quantity_confirmation_required: boolean };
};

export const UploadShelfPhotoPage: React.FC = () => {
  const { activeStoreId } = useStoreContext();
  const [file, setFile] = React.useState<File | null>(null);
  const [analysis, setAnalysis] = React.useState<ShelfAnalysis | null>(null);
  const [selected, setSelected] = React.useState<Record<string, string>>({});
  const [quantities, setQuantities] = React.useState<Record<string, string>>({});
  const [expiryDates, setExpiryDates] = React.useState<Record<string, string>>({});
  const [prices, setPrices] = React.useState<Record<string, string>>({});
  const [confirmed, setConfirmed] = React.useState<string[]>([]);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState('');
  const [message, setMessage] = React.useState('');
  const queryClient = useQueryClient();

  const { data: catalogue = [] } = useQuery({
    queryKey: ['inventory-catalogue-for-review'],
    queryFn: () => apiFetch<Array<{ id: string; sku_code: string; name: string; brand: string }>>(
      '/inventory/products?limit=2000',
    ),
  });

  const analyze = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!file || !activeStoreId) return;
    setBusy(true);
    setError('');
    setMessage('');
    setAnalysis(null);
    setConfirmed([]);
    try {
      const body = new FormData();
      body.append('file', file);
      const result = await apiFetch<ShelfAnalysis>(
        `/inventory/stores/${activeStoreId}/images/analyze`,
        { method: 'POST', body },
      );
      setAnalysis(result);
      setSelected(Object.fromEntries(result.vision.detections.map((d) => [
        d.detected_product_id, d.top_matches[0]?.product_id ?? '',
      ])));
      setMessage(`Analysis complete: ${result.detected_count} object regions require review.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Shelf image analysis failed');
    } finally {
      setBusy(false);
    }
  };

  const confirm = async (detection: ShelfDetection) => {
    if (!analysis || !activeStoreId) return;
    const productId = selected[detection.detected_product_id];
    const quantity = Number(quantities[detection.detected_product_id]);
    if (!productId || !Number.isFinite(quantity) || quantity <= 0) {
      setError('Select a catalogue SKU and enter the physically counted quantity.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const payload: Record<string, unknown> = { product_id: productId, quantity };
      const expiry = expiryDates[detection.detected_product_id];
      const price = prices[detection.detected_product_id];
      if (expiry) payload.expiry_date = expiry;
      if (price) payload.selling_price_paise = Math.round(Number(price) * 100);
      await apiFetch(
        `/inventory/stores/${activeStoreId}/images/${analysis.upload_id}/detections/${detection.detected_product_id}/confirm`,
        { method: 'POST', body: JSON.stringify(payload) },
      );
      setConfirmed((items) => [...items, detection.detected_product_id]);
      setMessage('Owner-confirmed stock quantity added to inventory.');
      queryClient.invalidateQueries({ queryKey: ['inventory'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not confirm this detection');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5">
      <StageNotice
        stage="Stage 3 · OCR-assisted shelf-photo beta"
        summary="Generic YOLO object regions and OCR text are used to rank catalogue candidates. This is not a retail-trained detector; owner SKU selection and physical quantity confirmation are mandatory."
      />
      <Card>
        <CardHeader>
          <h2 className="font-display text-sm font-semibold text-slate-900">Upload a shelf photo</h2>
        </CardHeader>
        <CardContent className="space-y-3">
          <form onSubmit={analyze} className="flex flex-col sm:flex-row gap-3">
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              className="min-w-0 flex-1 text-xs"
            />
            <Button type="submit" disabled={!file || !activeStoreId || busy}>
              {busy ? 'Processing…' : 'Analyze shelf photo'}
            </Button>
          </form>
          <p className="text-xs text-slate-500">JPEG, PNG or WebP; maximum 10 MB. Each confirmed quantity is added as a new stock count.</p>
          {error && <p className="text-xs text-red-700">{error}</p>}
          {message && <p className="text-xs text-teal-800">{message}</p>}
        </CardContent>
      </Card>
      {analysis && (
        <Card>
          <CardHeader>
            <h2 className="font-display text-sm font-semibold text-slate-900">
              Detection review · {analysis.detected_count} object regions
            </h2>
          </CardHeader>
          <CardContent className="space-y-4">
            {analysis.vision.detections.length === 0 && (
              <p className="text-xs text-slate-500">No objects were detected. Try a clearer, well-lit photo.</p>
            )}
            {analysis.vision.detections.map((d, index) => {
              const done = confirmed.includes(d.detected_product_id);
              return (
                <div key={d.detected_product_id} className="rounded-lg border border-slate-200 p-3 space-y-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs font-semibold text-slate-900">
                      Region {index + 1} · {d.detector_label} · {(d.detection_confidence * 100).toFixed(0)}% detector confidence
                    </p>
                    <span className={done ? 'text-xs text-teal-700' : 'text-xs text-amber-700'}>
                      {done ? 'Confirmed' : d.is_unknown ? 'Unknown SKU candidate' : 'Review required'}
                    </span>
                  </div>
                  <p className="text-xs text-slate-500">OCR: {d.ocr_text || 'No readable package text found'}</p>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <label className="text-xs text-slate-600">
                      Confirm SKU
                      <select
                        value={selected[d.detected_product_id] ?? ''}
                        disabled={done || busy}
                        onChange={(event) => setSelected((v) => ({ ...v, [d.detected_product_id]: event.target.value }))}
                        className="mt-1 w-full h-9 rounded-lg border border-slate-300 px-2 text-xs"
                      >
                        <option value="">Choose a product</option>
                        {catalogue.map((p) => (
                          <option key={p.id} value={p.id}>{p.sku_code} · {p.brand} {p.name}</option>
                        ))}
                      </select>
                    </label>
                    <label className="text-xs text-slate-600">
                      Physically counted quantity
                      <input
                        type="number" min="0.001" step="0.001" required
                        value={quantities[d.detected_product_id] ?? ''}
                        disabled={done || busy}
                        onChange={(event) => setQuantities((v) => ({ ...v, [d.detected_product_id]: event.target.value }))}
                        className="mt-1 w-full h-9 rounded-lg border border-slate-300 px-2 text-xs"
                      />
                    </label>
                    <label className="text-xs text-slate-600">
                      Batch expiry date (optional)
                      <input
                        type="date"
                        value={expiryDates[d.detected_product_id] ?? ''}
                        disabled={done || busy}
                        onChange={(event) => setExpiryDates((v) => ({ ...v, [d.detected_product_id]: event.target.value }))}
                        className="mt-1 w-full h-9 rounded-lg border border-slate-300 px-2 text-xs"
                      />
                    </label>
                    <label className="text-xs text-slate-600">
                      Selling price in ₹ (optional)
                      <input
                        type="number" min="0.01" step="0.01"
                        value={prices[d.detected_product_id] ?? ''}
                        disabled={done || busy}
                        onChange={(event) => setPrices((v) => ({ ...v, [d.detected_product_id]: event.target.value }))}
                        className="mt-1 w-full h-9 rounded-lg border border-slate-300 px-2 text-xs"
                      />
                    </label>
                  </div>
                  {!done && (
                    <Button size="sm" disabled={busy} onClick={() => confirm(d)}>
                      Confirm SKU and add quantity
                    </Button>
                  )}
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export const DetectionReviewPage: React.FC = () => (
  <div className="space-y-5">
    <StageNotice
      stage="Stage 3 Target · Owner Detection Review"
      summary="No shelf photographs uploaded yet. Confirmed detections will populate `inventory_image_uploads`, `detected_products`, and `owner_approvals`."
    />
  </div>
);

export const ReferenceImagesPage: React.FC = () => {
  const { data } = useQuery({
    queryKey: ['products-ref-preview'],
    queryFn: () =>
      apiFetch<{
        total: number;
        items: Array<{ id: string; sku_code: string; name: string; brand: string; category: string }>;
      }>('/products?limit=20&offset=0'),
  });

  return (
    <div className="space-y-5">
      <StageNotice
        stage="Stage 1 SKU Catalogue · Stage 3 Image Matching"
        summary={`800 master SKU reference image entries are registered in \`product_images\`. DINOv2-small / CLIP ViT-B/32 vector indexing activates in Stage 3.`}
      />
      <Card>
        <CardHeader>
          <h3 className="font-display text-sm font-semibold text-slate-900">
            Registered Master SKU Reference Registry (Sample 20 of {data?.total ?? 800})
          </h3>
        </CardHeader>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-200 bg-slate-50 text-slate-500">
              <tr>
                <th className="py-2.5 px-4 font-medium">SKU</th>
                <th className="py-2.5 px-4 font-medium">Master Product</th>
                <th className="py-2.5 px-4 font-medium">Brand</th>
                <th className="py-2.5 px-4 font-medium">Category</th>
                <th className="py-2.5 px-4 font-medium">Embedding Target</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {(data?.items ?? []).map((p) => (
                <tr key={p.id}>
                  <td className="py-2 px-4 font-mono-num text-slate-600">{p.sku_code}</td>
                  <td className="py-2 px-4 font-medium text-slate-900">{p.name}</td>
                  <td className="py-2 px-4 text-slate-700">{p.brand}</td>
                  <td className="py-2 px-4 text-slate-600">{p.category}</td>
                  <td className="py-2 px-4 font-mono-num text-slate-500">OCR catalogue matching · embeddings pending</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
};

export const DemandForecastingPage: React.FC = () => {
  const { activeStoreId } = useStoreContext();
  const { data } = useQuery({
    queryKey: ['sales-history-180', activeStoreId],
    queryFn: () =>
      apiFetch<{
        days: number;
        series: Array<{ date: string; units_sold: number; revenue_paise: number; festival_tag: string | null }>;
      >(`/forecasting/stores/${activeStoreId}/sales-history`),
    enabled: Boolean(activeStoreId),
  });

  const chartData = (data?.series ?? []).map((s) => ({
    date: s.date.slice(5),
    units: s.units_sold,
    festival: s.festival_tag,
  }));

  return (
    <div className="space-y-5">
      <StageNotice
        stage="Stage 1 Seeded Sales History · Stage 4 Forecasting Pipeline"
        summary="The historical chart shows recorded store sales. Per-SKU forecasts use an available moving-average or seven-day seasonal-naive baseline; advanced model selection and rolling backtests are pending."
      />
      <Card>
        <CardHeader>
          <h3 className="font-display text-sm font-semibold text-slate-900">
            6-Month Daily Units Sold ({data?.days ?? 0} days · Synthetic Dataset)
          </h3>
        </CardHeader>
        <CardContent className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#64748B' }} />
              <YAxis tick={{ fontSize: 11, fill: '#64748B' }} />
              <Tooltip />
              <Line type="monotone" dataKey="units" stroke="#0F766E" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </div>
  );
};

export const ReorderRecommendationsPage: React.FC = () => {
  const { activeStoreId } = useStoreContext();
  const queryClient = useQueryClient();
  const [quantities, setQuantities] = React.useState<Record<string, string>>({});
  const [busyId, setBusyId] = React.useState('');
  const [message, setMessage] = React.useState('');
  const [error, setError] = React.useState('');
  const { data, refetch, isLoading } = useQuery({
    queryKey: ['reorder-suggestions', activeStoreId],
    queryFn: () => apiFetch<{ suggestions: Array<{
      id: string; product_id: string; sku_code: string; product_name: string; current_available_qty: number;
      suggested_qty: number; supplier_pack_size: number;
      estimated_cost_paise: number; explanation: string; status: string;
    }> }>(`/forecasting/stores/${activeStoreId}/reorder-suggestions`),
    enabled: Boolean(activeStoreId),
  });

  const generate = async () => {
    if (!activeStoreId) return;
    setBusyId('generate'); setError(''); setMessage('');
    try {
      const result = await apiFetch<{ created_count: number }>(
        `/forecasting/stores/${activeStoreId}/reorder-suggestions/generate`,
        { method: 'POST' },
      );
      setMessage(`Generated ${result.created_count} new reorder suggestions.`);
      await refetch();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not generate suggestions');
    } finally { setBusyId(''); }
  };

  const decide = async (id: string, decision: 'accepted' | 'edited' | 'rejected') => {
    if (!activeStoreId) return;
    setBusyId(id); setError('');
    try {
      const payload: Record<string, unknown> = { decision };
      if (decision === 'edited') payload.final_qty = Number(quantities[id]);
      await apiFetch(
        `/forecasting/stores/${activeStoreId}/reorder-suggestions/${id}/decision`,
        { method: 'POST', body: JSON.stringify(payload) },
      );
      setMessage(`Suggestion ${decision}.`);
      queryClient.invalidateQueries({ queryKey: ['reorder-suggestions', activeStoreId] });
      await refetch();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save decision');
    } finally { setBusyId(''); }
  };

  return (
    <div className="space-y-5">
      <StageNotice
        stage="Stage 4 · Baseline forecast and reorder planner"
        summary="Moving-average demand history, lead-time demand, safety stock and supplier pack-size rounding generate recommendations. Owner approval is required; this action does not create a purchase order."
      />
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs text-slate-500">Pending suggestions: {data?.suggestions.length ?? 0}</p>
        <Button size="sm" disabled={!activeStoreId || busyId !== ''} onClick={generate}>
          {busyId === 'generate' ? 'Generating…' : 'Generate reorder suggestions'}
        </Button>
      </div>
      {error && <p className="text-xs text-red-700">{error}</p>}
      {message && <p className="text-xs text-teal-800">{message}</p>}
      <Card>
        <CardContent className="divide-y divide-slate-100">
          {isLoading && <p className="py-4 text-xs text-slate-500">Loading suggestions…</p>}
          {!isLoading && (data?.suggestions ?? []).length === 0 && (
            <p className="py-4 text-xs text-slate-500">No pending suggestions. Generate them after sales history is available.</p>
          )}
          {(data?.suggestions ?? []).map((row) => (
            <div key={row.id} className="py-4 space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs font-semibold text-slate-900">{row.sku_code} · {row.product_name}</p>
                <p className="text-xs text-slate-600">Suggested: {formatQty(row.suggested_qty, '')} · Cost: {formatINR(row.estimated_cost_paise)}</p>
              </div>
              <p className="text-xs text-slate-500">{row.explanation}</p>
              <div className="flex flex-wrap items-end gap-2">
                <label className="text-xs text-slate-600">
                  Edit quantity (pack size {row.supplier_pack_size})
                  <input
                    type="number" min="0.001" step={row.supplier_pack_size}
                    value={quantities[row.id] ?? String(row.suggested_qty)}
                    onChange={(event) => setQuantities((v) => ({ ...v, [row.id]: event.target.value }))}
                    className="mt-1 block h-9 w-36 rounded-lg border border-slate-300 px-2 text-xs"
                  />
                </label>
                <Button size="sm" disabled={busyId !== ''} onClick={() => decide(row.id, 'accepted')}>Approve suggestion</Button>
                <Button size="sm" variant="secondary" disabled={busyId !== ''} onClick={() => decide(row.id, 'edited')}>Approve edited</Button>
                <Button size="sm" variant="ghost" disabled={busyId !== ''} onClick={() => decide(row.id, 'rejected')}>Reject</Button>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
};

export const SmartPricingDashboardPage: React.FC = () => {
  const { activeStoreId } = useStoreContext();
  const queryClient = useQueryClient();
  const [generating, setGenerating] = React.useState(false);
  const [message, setMessage] = React.useState('');
  const [error, setError] = React.useState('');
  const { data } = useQuery({
    queryKey: ['competitor-comp', activeStoreId],
    queryFn: () => apiFetch<{
      nearby_verified_store_count: number;
      comparisons: Array<{
        product_id: string;
        sku_code: string;
        name: string;
        selling_price_paise: number;
        mrp_paise: number;
        nearby_verified_stores: number;
        nearby_median_paise: number | null;
        diff_vs_median_pct: number | null;
      }>;
    }>(`/pricing/stores/${activeStoreId}/competitor-comparison`),
    enabled: Boolean(activeStoreId),
  });

  const generateRecommendations = async () => {
    if (!activeStoreId) return;
    setGenerating(true); setError(''); setMessage('');
    try {
      const result = await apiFetch<{ created_count: number; skipped_count: number }>(
        `/pricing/stores/${activeStoreId}/recommendations/generate`,
        { method: 'POST' },
      );
      setMessage(`Created ${result.created_count} recommendations; skipped ${result.skipped_count} items with an existing pending recommendation or infeasible constraints.`);
      queryClient.invalidateQueries({ queryKey: ['pricing-recommendations', activeStoreId] });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not generate recommendations');
    } finally { setGenerating(false); }
  };

  return (
    <div className="space-y-5">
      <StageNotice
        stage="Stage 5 · Rule-based Smart Pricing Agent"
        summary={`Comparisons use verified competitor observations from the previous 30 days within 2 km. Expiry markdown and excess-stock rules are active; learned price elasticity is not enabled.`}
      />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-slate-500">
          {data?.nearby_verified_store_count ?? 0} verified competitor stores in the 2 km comparison set
        </p>
        <Button size="sm" disabled={!activeStoreId || generating} onClick={generateRecommendations}>
          {generating ? 'Generating…' : 'Generate pricing recommendations'}
        </Button>
      </div>
      {error && <p className="text-xs text-red-700">{error}</p>}
      {message && <p className="text-xs text-teal-800">{message}</p>}
      <Card>
        <CardHeader>
          <h3 className="font-display text-sm font-semibold text-slate-900">
            Nearby verified store comparison
          </h3>
        </CardHeader>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-200 bg-slate-50 text-slate-500">
              <tr>
                <th className="py-2.5 px-4 font-medium">SKU</th>
                <th className="py-2.5 px-4 font-medium">Product</th>
                <th className="py-2.5 px-4 font-medium text-right">Store Price</th>
                <th className="py-2.5 px-4 font-medium text-right">MRP</th>
                <th className="py-2.5 px-4 font-medium text-right">2km Median</th>
                <th className="py-2.5 px-4 font-medium text-right">Diff vs Median</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {(data?.comparisons ?? []).slice(0, 30).map((row) => (
                <tr key={row.product_id}>
                  <td className="py-2 px-4 font-mono-num text-slate-600">{row.sku_code}</td>
                  <td className="py-2 px-4 font-medium text-slate-900">{row.name}</td>
                  <td className="py-2 px-4 font-mono-num text-right">{formatINR(row.selling_price_paise)}</td>
                  <td className="py-2 px-4 font-mono-num text-right text-slate-500">{formatINR(row.mrp_paise)}</td>
                  <td className="py-2 px-4 font-mono-num text-right">
                    {row.nearby_median_paise ? formatINR(row.nearby_median_paise) : '—'}
                  </td>
                  <td className="py-2 px-4 font-mono-num text-right text-slate-600">
                    {row.diff_vs_median_pct !== null ? `${row.diff_vs_median_pct > 0 ? '+' : ''}${row.diff_vs_median_pct}%` : 'No recent peers'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
};

export const PricingInboxPage: React.FC = () => {
  const { activeStoreId } = useStoreContext();
  const queryClient = useQueryClient();
  const [prices, setPrices] = React.useState<Record<string, string>>({});
  const [busyId, setBusyId] = React.useState('');
  const [message, setMessage] = React.useState('');
  const [error, setError] = React.useState('');
  const { data, refetch, isLoading } = useQuery({
    queryKey: ['pricing-recommendations', activeStoreId],
    queryFn: () => apiFetch<{ recommendations: Array<{
      id: string; product_id: string; sku_code: string; product_name: string; current_price_paise: number;
      recommended_price_paise: number; status: string; explanation: string;
    }> }>(`/pricing/stores/${activeStoreId}/recommendations?status=pending`),
    enabled: Boolean(activeStoreId),
  });

  const decide = async (id: string, decision: 'accepted' | 'edited' | 'rejected') => {
    if (!activeStoreId) return;
    setBusyId(id); setError('');
    try {
      const payload: Record<string, unknown> = { decision };
      if (decision === 'edited') payload.final_price_paise = Math.round(Number(prices[id]) * 100);
      await apiFetch(
        `/pricing/stores/${activeStoreId}/recommendations/${id}/decision`,
        { method: 'POST', body: JSON.stringify(payload) },
      );
      setMessage(`Recommendation ${decision}. Approved changes are recorded in price history.`);
      queryClient.invalidateQueries({ queryKey: ['pricing-recommendations', activeStoreId] });
      await refetch();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save pricing decision');
    } finally { setBusyId(''); }
  };

  return (
    <div className="space-y-5">
      <StageNotice
        stage="Stage 5 · Owner pricing approval inbox"
        summary="The deterministic pricing engine considers recent verified competitor prices, expiry dates and excess-stock pressure. Price elasticity is not trained yet. Prices never change until the owner approves."
      />
      {error && <p className="text-xs text-red-700">{error}</p>}
      {message && <p className="text-xs text-teal-800">{message}</p>}
      <Card>
        <CardHeader>
          <h2 className="font-display text-sm font-semibold text-slate-900">Pending price recommendations</h2>
        </CardHeader>
        <CardContent className="divide-y divide-slate-100">
          {isLoading && <p className="py-4 text-xs text-slate-500">Loading recommendations…</p>}
          {!isLoading && (data?.recommendations ?? []).length === 0 && (
            <p className="py-4 text-xs text-slate-500">No pending pricing recommendations. Generate them from the Smart Pricing dashboard.</p>
          )}
          {(data?.recommendations ?? []).map((row) => (
            <div key={row.id} className="py-4 space-y-2">
              <p className="text-xs font-semibold text-slate-900">{row.sku_code} · {row.product_name}</p>
              <div className="flex flex-wrap gap-4 text-xs text-slate-600">
                <span>Current: {formatINR(row.current_price_paise)}</span>
                <span>Recommended: {formatINR(row.recommended_price_paise)}</span>
              </div>
              <p className="text-xs text-slate-500">{row.explanation}</p>
              <div className="flex flex-wrap items-end gap-2">
                <label className="text-xs text-slate-600">
                  Edit price in ₹
                  <input
                    type="number" min="0.01" step="1"
                    value={prices[row.id] ?? String(row.recommended_price_paise / 100)}
                    onChange={(event) => setPrices((v) => ({ ...v, [row.id]: event.target.value }))}
                    className="mt-1 block h-9 w-32 rounded-lg border border-slate-300 px-2 text-xs"
                  />
                </label>
                <Button size="sm" disabled={busyId !== ''} onClick={() => decide(row.id, 'accepted')}>Approve</Button>
                <Button size="sm" variant="secondary" disabled={busyId !== ''} onClick={() => decide(row.id, 'edited')}>Approve edited</Button>
                <Button size="sm" variant="ghost" disabled={busyId !== ''} onClick={() => decide(row.id, 'rejected')}>Reject</Button>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
};

export const ProductAnalyticsPage: React.FC = () => {
  const { activeStoreId } = useStoreContext();
  const { data } = useQuery({
    queryKey: ['batches-analytics', activeStoreId],
    queryFn: () =>
      apiFetch<{
        batches: Array<{
          id: string;
          sku_code: string;
          name: string;
          batch_code: string;
          remaining_qty: number;
          expiry_date: string;
          status: string;
          expiry_category: string;
        }>;
      }>(`/stores/${activeStoreId}/batches`),
    enabled: Boolean(activeStoreId),
  });

  return (
    <div className="space-y-5">
      <StageNotice
        stage="Stage 1 Stock Batch Tracking · Stage 4–5 Product Analytics"
        summary="Batch-level expiry dates and remaining quantities are live below to support FIFO monitoring and Stage 5 expiry markdown calculations."
      />
      <Card>
        <CardHeader>
          <h3 className="font-display text-sm font-semibold text-slate-900">
            Batch Expiry Ledger (Sorted Earliest Expiry First)
          </h3>
        </CardHeader>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-200 bg-slate-50 text-slate-500">
              <tr>
                <th className="py-2.5 px-4 font-medium">Batch Code</th>
                <th className="py-2.5 px-4 font-medium">SKU · Product</th>
                <th className="py-2.5 px-4 font-medium">Expiry Profile</th>
                <th className="py-2.5 px-4 font-medium text-right">Remaining Qty</th>
                <th className="py-2.5 px-4 font-medium text-right">Expiry Date</th>
                <th className="py-2.5 px-4 font-medium text-right">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {(data?.batches ?? []).slice(0, 25).map((b) => (
                <tr key={b.id}>
                  <td className="py-2 px-4 font-mono-num text-slate-600">{b.batch_code}</td>
                  <td className="py-2 px-4 font-medium text-slate-900">
                    {b.sku_code} · {b.name}
                  </td>
                  <td className="py-2 px-4 text-slate-600">{b.expiry_category}</td>
                  <td className="py-2 px-4 font-mono-num text-right">{formatQty(b.remaining_qty, '')}</td>
                  <td className="py-2 px-4 font-mono-num text-right">{formatISTDate(b.expiry_date)}</td>
                  <td
                    className={`py-2 px-4 text-right font-medium ${
                      b.status === 'expiring_soon' ? 'text-red-700' : 'text-slate-600'
                    }`}
                  >
                    {b.status}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
};
