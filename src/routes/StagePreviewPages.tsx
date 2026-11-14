import React from 'react';
import { useQuery } from '@tanstack/react-query';
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

export const UploadShelfPhotoPage: React.FC = () => (
  <div className="space-y-5">
    <StageNotice
      stage="Stage 3 Target · Photo-to-Catalogue Pipeline"
      summary="Computer vision service boundary (`services/vision`) is scaffolded in Stage 1. RT-DETR detection, YOLO11 baseline evaluation, DINOv2/CLIP embeddings, and EasyOCR matching will be activated in Stage 3."
    />
    <Card>
      <CardHeader>
        <h2 className="font-display text-sm font-semibold text-slate-900">
          Photo-to-Catalogue Architecture Rules
        </h2>
      </CardHeader>
      <CardContent className="text-xs text-slate-600 space-y-2">
        <p>1. Shelf images cannot reliably count stacked items behind front-facing SKUs; owner quantity confirmation is strictly mandatory.</p>
        <p>2. Unknown products will be flagged rather than forced into incorrect SKU matches.</p>
        <p>3. Loose commodities (rice, dal, sugar) always support manual per-kg listing.</p>
      </CardContent>
    </Card>
  </div>
);

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
        stage="Stage 1 Foundation · Stage 3 Embedding Activation"
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
                  <td className="py-2 px-4 font-mono-num text-slate-500">dinov2-small · 512d</td>
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
      }>(`/stores/${activeStoreId}/sales-history`),
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
        summary="180 days of synthetic store sales (including Ugadi, Ganesh Chaturthi, Dasara, Deepavali, and Sankranti demand spikes) are loaded below. Seasonal Naive, Moving Average, Croston/TSB, and LightGBM models activate in Stage 4."
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

export const ReorderRecommendationsPage: React.FC = () => (
  <div className="space-y-5">
    <StageNotice
      stage="Stage 4 Target · Reorder Point & Safety Stock Planner"
      summary="Formula ROP = Expected Lead-Time Demand + (1.65 × σ × √L) with supplier pack-size rounding will generate owner-approvable suggestions here in Stage 4."
    />
  </div>
);

export const SmartPricingDashboardPage: React.FC = () => {
  const { activeStoreId } = useStoreContext();
  const { data } = useQuery({
    queryKey: ['competitor-comp', activeStoreId],
    queryFn: () =>
      apiFetch<{
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
      }>(`/stores/${activeStoreId}/competitor-comparison`),
    enabled: Boolean(activeStoreId),
  });

  return (
    <div className="space-y-5">
      <StageNotice
        stage="Stage 1 Verified Competitor Dataset · Stage 5 Smart Pricing Engine"
        summary={`Found ${data?.nearby_verified_store_count ?? 0} verified Kirana stores within a 2.0 km radius for SKU-level median comparison. Log-log elasticity, expiry markdown, and pricing inbox approvals activate in Stage 5.`}
      />
      <Card>
        <CardHeader>
          <h3 className="font-display text-sm font-semibold text-slate-900">
            Nearby Verified Store Comparison (2 km Radius · Synthetic Data)
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
              {(data?.comparisons ?? []).slice(0, 20).map((row) => (
                <tr key={row.product_id}>
                  <td className="py-2 px-4 font-mono-num text-slate-600">{row.sku_code}</td>
                  <td className="py-2 px-4 font-medium text-slate-900">{row.name}</td>
                  <td className="py-2 px-4 font-mono-num text-right">
                    {formatINR(row.selling_price_paise)}
                  </td>
                  <td className="py-2 px-4 font-mono-num text-right text-slate-500">
                    {formatINR(row.mrp_paise)}
                  </td>
                  <td className="py-2 px-4 font-mono-num text-right">
                    {row.nearby_median_paise ? formatINR(row.nearby_median_paise) : '—'}
                  </td>
                  <td
                    className={`py-2 px-4 font-mono-num text-right ${
                      row.diff_vs_median_pct !== null && row.diff_vs_median_pct > 5
                        ? 'text-amber-700 font-medium'
                        : 'text-slate-600'
                    }`}
                  >
                    {row.diff_vs_median_pct !== null
                      ? `${row.diff_vs_median_pct > 0 ? '+' : ''}${row.diff_vs_median_pct}%`
                      : 'No peers <2km'}
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

export const PricingInboxPage: React.FC = () => (
  <div className="space-y-5">
    <StageNotice
      stage="Stage 5 Target · Owner Pricing Recommendation Inbox"
      summary="Smart Pricing Agent never changes selling prices automatically. Pending recommendations awaiting owner accept/edit/reject will appear here in Stage 5."
    />
  </div>
);

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
