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
  const [rejected, setRejected] = React.useState<string[]>([]);
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
    setRejected([]);
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


  const reject = async (detection: ShelfDetection) => {
    if (!analysis || !activeStoreId) return;
    setBusy(true);
    setError('');
    try {
      await apiFetch(
        `/inventory/stores/${activeStoreId}/images/${analysis.upload_id}/detections/${detection.detected_product_id}/reject`,
        { method: 'POST', body: JSON.stringify({ notes: 'Owner rejected this detection as not an inventory item.' }) },
      );
      setRejected((items) => [...items, detection.detected_product_id]);
      setMessage('Detection rejected. Inventory was not changed.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not reject this detection');
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
              const isConfirmed = confirmed.includes(d.detected_product_id);
              const isRejected = rejected.includes(d.detected_product_id);
              const done = isConfirmed || isRejected;
              return (
                <div key={d.detected_product_id} className="rounded-lg border border-slate-200 p-3 space-y-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs font-semibold text-slate-900">
                      Region {index + 1} · {d.detector_label} · {(d.detection_confidence * 100).toFixed(0)}% detector confidence
                    </p>
                    <span className={done ? 'text-xs text-teal-700' : 'text-xs text-amber-700'}>
                      {isConfirmed ? 'Confirmed' : isRejected ? 'Rejected' : d.is_unknown ? 'Unknown SKU candidate' : 'Review required'}
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
                    <div className="flex flex-wrap gap-2">
                      <Button size="sm" disabled={busy} onClick={() => confirm(d)}>
                        Confirm SKU and add quantity
                      </Button>
                      <Button size="sm" variant="ghost" disabled={busy} onClick={() => reject(d)}>
                        Reject detection
                      </Button>
                    </div>
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

type PhotoReviewDetection = {
  id: string;
  bbox: number[];
  detection_confidence: number;
  ocr_text: string;
  top_matches: ShelfCandidate[];
  is_unknown: boolean;
  owner_action: string;
  selected_product_id: string | null;
  owner_entered_qty: string | null;
};
type PhotoReviewUpload = {
  id: string;
  status: string;
  detector_model: string;
  detected_count: number;
  created_at_utc: string;
  detections: PhotoReviewDetection[];
};

export const DetectionReviewPage: React.FC = () => {
  const { activeStoreId } = useStoreContext();
  const queryClient = useQueryClient();
  const [selected, setSelected] = React.useState<Record<string, string>>({});
  const [quantities, setQuantities] = React.useState<Record<string, string>>({});
  const [expiryDates, setExpiryDates] = React.useState<Record<string, string>>({});
  const [prices, setPrices] = React.useState<Record<string, string>>({});
  const [busyId, setBusyId] = React.useState('');
  const [error, setError] = React.useState('');
  const [message, setMessage] = React.useState('');
  const { data, isLoading, error: queryError } = useQuery({
    queryKey: ['inventory-photo-reviews', activeStoreId],
    queryFn: () => apiFetch<{ uploads: PhotoReviewUpload[] }>(
      `/inventory/stores/${activeStoreId}/images?limit=50`,
    ),
    enabled: Boolean(activeStoreId),
  });
  const { data: catalogue = [] } = useQuery({
    queryKey: ['inventory-catalogue-for-review'],
    queryFn: () => apiFetch<Array<{ id: string; sku_code: string; name: string; brand: string }>>(
      '/inventory/products?limit=2000',
    ),
  });

  const decide = async (uploadId: string, detection: PhotoReviewDetection, decision: 'confirm' | 'reject') => {
    if (!activeStoreId) return;
    setBusyId(detection.id);
    setError('');
    setMessage('');
    try {
      const endpoint = `/inventory/stores/${activeStoreId}/images/${uploadId}/detections/${detection.id}/${decision}`;
      if (decision === 'reject') {
        await apiFetch(endpoint, {
          method: 'POST',
          body: JSON.stringify({ notes: 'Owner rejected this historical detection.' }),
        });
      } else {
        const productId = selected[detection.id] ?? detection.top_matches[0]?.product_id ?? '';
        const quantity = Number(quantities[detection.id]);
        if (!productId || !Number.isFinite(quantity) || quantity <= 0) {
          setError('Select a catalogue SKU and enter the physically counted quantity.');
          return;
        }
        const payload: Record<string, unknown> = { product_id: productId, quantity };
        const expiry = expiryDates[detection.id];
        const price = prices[detection.id];
        if (expiry) payload.expiry_date = expiry;
        if (price) payload.selling_price_paise = Math.round(Number(price) * 100);
        await apiFetch(endpoint, { method: 'POST', body: JSON.stringify(payload) });
      }
      setMessage(decision === 'confirm' ? 'Owner-confirmed stock added to inventory.' : 'Detection rejected; inventory was not changed.');
      await queryClient.invalidateQueries({ queryKey: ['inventory-photo-reviews', activeStoreId] });
      queryClient.invalidateQueries({ queryKey: ['inventory'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save owner review');
    } finally {
      setBusyId('');
    }
  };

  return (
    <div className="space-y-5">
      <StageNotice
        stage="Stage 3 · Persisted owner detection review"
        summary="Review previous shelf-photo analyses, OCR evidence, catalogue candidates and owner decisions. Unconfirmed detections remain pending; inventory changes only after owner confirmation."
      />
      {isLoading && <p className="text-xs text-slate-500">Loading shelf-photo history…</p>}
      {(queryError || error) && <p className="text-xs text-red-700">{error || (queryError instanceof Error ? queryError.message : 'Could not load shelf-photo history')}</p>}
      {message && <p className="text-xs text-teal-800">{message}</p>}
      {!isLoading && !queryError && (data?.uploads ?? []).length === 0 && (
        <Card>
          <CardContent>
            <p className="py-3 text-xs text-slate-500">No shelf-photo analyses have been recorded for this store.</p>
            <Link to="/inventory" className="text-xs font-medium text-teal-800 underline">Open inventory to start a shelf-photo analysis</Link>
          </CardContent>
        </Card>
      )}
      {(data?.uploads ?? []).map((upload) => (
        <Card key={upload.id}>
          <CardHeader>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className="font-display text-sm font-semibold text-slate-900">
                  Shelf photo · {new Date(upload.created_at_utc).toLocaleString('en-IN')}
                </h3>
                <p className="mt-1 text-xs text-slate-500">
                  {upload.detector_model} · {upload.detected_count} object regions · Upload {upload.id.slice(0, 8)}
                </p>
              </div>
              <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-700">{upload.status.replaceAll('_', ' ')}</span>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {upload.detections.length === 0 && (
              <p className="text-xs text-slate-500">No object regions were recorded for this upload.</p>
            )}
            {upload.detections.map((detection, index) => (
              <div key={detection.id} className="rounded-lg border border-slate-200 p-3 space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-xs font-semibold text-slate-900">
                    Region {index + 1} · {(detection.detection_confidence * 100).toFixed(0)}% detector confidence
                  </p>
                  <span className="text-xs text-slate-600">{detection.owner_action.replaceAll('_', ' ')}</span>
                </div>
                <p className="text-xs text-slate-500">OCR evidence: {detection.ocr_text || 'No readable package text'}</p>
                {detection.owner_entered_qty && (
                  <p className="text-xs text-slate-700">Owner-confirmed quantity added: {detection.owner_entered_qty}</p>
                )}
                {detection.top_matches.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-slate-600">Ranked catalogue candidates</p>
                    <ul className="mt-1 space-y-1">
                      {detection.top_matches.map((candidate) => (
                        <li key={candidate.product_id} className="text-xs text-slate-600">
                          {candidate.sku_code} · {candidate.brand} {candidate.name} · {(candidate.score * 100).toFixed(1)}%
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {detection.owner_action === 'pending' && (
                  <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                    <label className="text-xs text-slate-600">
                      Confirm SKU
                      <select
                        value={selected[detection.id] ?? detection.top_matches[0]?.product_id ?? ''}
                        disabled={busyId === detection.id}
                        onChange={(event) => setSelected((v) => ({ ...v, [detection.id]: event.target.value }))}
                        className="mt-1 h-9 w-full rounded-lg border border-slate-300 px-2 text-xs"
                      >
                        <option value="">Choose a product</option>
                        {catalogue.map((product) => (
                          <option key={product.id} value={product.id}>{product.sku_code} · {product.brand} {product.name}</option>
                        ))}
                      </select>
                    </label>
                    <label className="text-xs text-slate-600">
                      Physically counted quantity
                      <input
                        type="number" min="0.001" step="0.001"
                        value={quantities[detection.id] ?? ''}
                        disabled={busyId === detection.id}
                        onChange={(event) => setQuantities((v) => ({ ...v, [detection.id]: event.target.value }))}
                        className="mt-1 h-9 w-full rounded-lg border border-slate-300 px-2 text-xs"
                      />
                    </label>
                    <label className="text-xs text-slate-600">
                      Batch expiry date (optional)
                      <input
                        type="date"
                        value={expiryDates[detection.id] ?? ''}
                        disabled={busyId === detection.id}
                        onChange={(event) => setExpiryDates((v) => ({ ...v, [detection.id]: event.target.value }))}
                        className="mt-1 h-9 w-full rounded-lg border border-slate-300 px-2 text-xs"
                      />
                    </label>
                    <label className="text-xs text-slate-600">
                      Selling price in ₹ (optional)
                      <input
                        type="number" min="0.01" step="0.01"
                        value={prices[detection.id] ?? ''}
                        disabled={busyId === detection.id}
                        onChange={(event) => setPrices((v) => ({ ...v, [detection.id]: event.target.value }))}
                        className="mt-1 h-9 w-full rounded-lg border border-slate-300 px-2 text-xs"
                      />
                    </label>
                    <div className="flex flex-wrap gap-2 md:col-span-2">
                      <Button size="sm" disabled={busyId !== ''} onClick={() => decide(upload.id, detection, 'confirm')}>
                        Confirm SKU and add quantity
                      </Button>
                      <Button size="sm" variant="ghost" disabled={busyId !== ''} onClick={() => decide(upload.id, detection, 'reject')}>
                        Reject detection
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      ))}
    </div>
  );
};

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
  const [selectedProductId, setSelectedProductId] = React.useState('');
  const [model, setModel] = React.useState<'moving_average' | 'seasonal_naive'>('moving_average');
  const { data: products = [] } = useQuery({
    queryKey: ['forecast-catalogue'],
    queryFn: () => apiFetch<Array<{ id: string; sku_code: string; name: string }>>(
      '/inventory/products?limit=2000',
    ),
  });
  const productId = selectedProductId || products[0]?.id || '';
  const { data: history } = useQuery({
    queryKey: ['sales-history-180', activeStoreId],
    queryFn: () =>
      apiFetch<{
        days: number;
        series: Array<{ date: string; units_sold: number; revenue_paise: number; festival_tag: string | null }>;
      }>(`/forecasting/stores/${activeStoreId}/sales-history`),
    enabled: Boolean(activeStoreId),
  });
  const { data: forecast, isLoading: forecastLoading, error: forecastError } = useQuery({
    queryKey: ['sku-forecast', activeStoreId, productId, model],
    queryFn: () => apiFetch<{
      model_name: string; predicted_qty: number; daily_mean: number;
      lower_bound_qty: number; upper_bound_qty: number; horizon_days: number;
      history_days: number; data_quality: string;
    }>(`/forecasting/stores/${activeStoreId}/products/${productId}/forecast?horizon_days=7&model=${model}`),
    enabled: Boolean(activeStoreId && productId),
  });

  const chartData = (history?.series ?? []).map((s) => ({
    date: s.date.slice(5),
    units: s.units_sold,
    festival: s.festival_tag,
  }));

  return (
    <div className="space-y-5">
      <StageNotice
        stage="Stage 4 · Sales history and SKU demand baseline"
        summary="The historical chart shows recorded store sales. Per-SKU forecasts use a moving-average or seven-day seasonal-naive baseline. Croston-TSB, LightGBM, model selection and rolling backtests are not enabled yet."
      />
      <Card>
        <CardHeader>
          <h3 className="font-display text-sm font-semibold text-slate-900">
            7-day demand forecast
          </h3>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="text-xs text-slate-600">
              Product SKU
              <select
                value={productId}
                onChange={(event) => setSelectedProductId(event.target.value)}
                className="mt-1 h-9 w-full rounded-lg border border-slate-300 px-2 text-xs"
              >
                {products.map((product) => (
                  <option key={product.id} value={product.id}>{product.sku_code} · {product.name}</option>
                ))}
              </select>
            </label>
            <label className="text-xs text-slate-600">
              Forecast baseline
              <select
                value={model}
                onChange={(event) => setModel(event.target.value as 'moving_average' | 'seasonal_naive')}
                className="mt-1 h-9 w-full rounded-lg border border-slate-300 px-2 text-xs"
              >
                <option value="moving_average">Moving average</option>
                <option value="seasonal_naive">7-day seasonal naive</option>
              </select>
            </label>
          </div>
          {forecastLoading && <p className="text-xs text-slate-500">Calculating forecast…</p>}
          {forecastError && <p className="text-xs text-amber-700">{forecastError instanceof Error ? forecastError.message : 'Forecast unavailable for this SKU'}</p>}
          {forecast && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="rounded-lg bg-slate-50 p-3">
                <p className="text-xs text-slate-500">7-day expected demand</p>
                <p className="mt-1 text-lg font-semibold text-slate-900">{formatQty(forecast.predicted_qty, '')}</p>
              </div>
              <div className="rounded-lg bg-slate-50 p-3">
                <p className="text-xs text-slate-500">Daily average</p>
                <p className="mt-1 text-lg font-semibold text-slate-900">{formatQty(forecast.daily_mean, '')}</p>
              </div>
              <div className="rounded-lg bg-slate-50 p-3">
                <p className="text-xs text-slate-500">Forecast interval</p>
                <p className="mt-1 text-sm font-semibold text-slate-900">{formatQty(forecast.lower_bound_qty, '')}–{formatQty(forecast.upper_bound_qty, '')}</p>
              </div>
              <div className="rounded-lg bg-slate-50 p-3">
                <p className="text-xs text-slate-500">Baseline / history</p>
                <p className="mt-1 text-sm font-semibold text-slate-900">{forecast.model_name} · {forecast.history_days} days</p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <h3 className="font-display text-sm font-semibold text-slate-900">
            Daily store sales ({history?.days ?? 0} observed dates · 180-day window)
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
      }>(`/inventory/stores/${activeStoreId}/batches`),
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
