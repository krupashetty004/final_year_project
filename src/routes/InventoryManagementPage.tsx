import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Search } from 'lucide-react';
import { apiFetch } from '../lib/api';
import { useStoreContext } from '../hooks/useStoreContext';
import { formatINR, formatISTDate, formatQty } from '../lib/formatters';
import { Card, CardContent, CardHeader } from '../components/ui/Card';
import { Button } from '../components/ui/Button';

interface InventoryRow {
  id: string;
  product_id: string;
  sku_code: string;
  name: string;
  brand: string;
  category: string;
  available_qty: number;
  reserved_qty: number;
  incoming_qty: number;
  unit_type: string;
  selling_price_paise: number;
  cost_price_paise: number;
  mrp_paise: number;
  reorder_point_qty: number;
  supplier_name: string | null;
  lead_time_days: number | null;
  nearest_expiry_date: string | null;
  is_loose_commodity: number;
  clearance_enabled: number;
  version: number;
}

const FILTER_TABS = [
  { id: 'all', label: 'All Stock' },
  { id: 'low_stock', label: 'Low Stock' },
  { id: 'out_of_stock', label: 'Out of Stock' },
  { id: 'expiring_soon', label: 'Expiring <= 7d' },
  { id: 'loose', label: 'Loose Commodities' },
] as const;

export const InventoryManagementPage: React.FC = () => {
  const { activeStoreId } = useStoreContext();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<(typeof FILTER_TABS)[number]['id']>('all');
  const [editing, setEditing] = useState<InventoryRow | null>(null);
  const [editQty, setEditQty] = useState('');
  const [editReserved, setEditReserved] = useState('');
  const [editPriceRupees, setEditPriceRupees] = useState('');
  const [editError, setEditError] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['inventory', activeStoreId, search, filter],
    queryFn: () =>
      apiFetch<{ items: InventoryRow[] }>(
        `/stores/${activeStoreId}/inventory?search=${encodeURIComponent(search)}&filter=${filter}`,
      ),
    enabled: Boolean(activeStoreId),
  });

  const updateMutation = useMutation({
    mutationFn: (payload: {
      inventoryId: string;
      available_qty: number;
      reserved_qty: number;
      selling_price_paise: number;
      version: number;
    }) =>
      apiFetch(`/stores/${activeStoreId}/inventory/${payload.inventoryId}`, {
        method: 'PATCH',
        body: JSON.stringify({
          available_qty: payload.available_qty,
          reserved_qty: payload.reserved_qty,
          selling_price_paise: payload.selling_price_paise,
          version: payload.version,
        }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['inventory', activeStoreId] });
      queryClient.invalidateQueries({ queryKey: ['dashboard', activeStoreId] });
      setEditing(null);
      setEditError('');
    },
    onError: (err) => {
      setEditError(err instanceof Error ? err.message : 'Update rejected');
    },
  });

  const startEdit = (row: InventoryRow) => {
    setEditing(row);
    setEditQty(String(row.available_qty));
    setEditReserved(String(row.reserved_qty));
    setEditPriceRupees(String(row.selling_price_paise / 100));
    setEditError('');
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h2 className="font-display text-lg font-semibold text-slate-900">
            Store Inventory & Batch Control
          </h2>
          <p className="text-xs text-slate-500">
            Enforces selling price ≤ MRP, reserved ≤ available, and optimistic locking (`version`)
          </p>
        </div>
      </div>

      <Card>
        <CardContent className="p-4 flex flex-col lg:flex-row lg:items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-1 rounded-lg bg-slate-100 p-1">
            {FILTER_TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setFilter(tab.id)}
                className={`rounded-md px-3 py-1.5 text-xs font-medium whitespace-nowrap transition-colors ${
                  filter === tab.id ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div className="relative w-full lg:w-72">
            <Search className="h-4 w-4 text-slate-400 absolute left-3 top-2.5" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filter SKU or product..."
              className="w-full h-9 rounded-lg border border-slate-300 pl-9 pr-3 text-xs"
            />
          </div>
        </CardContent>

        <div className="overflow-x-auto border-t border-slate-200">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-200 bg-slate-50 text-slate-500">
              <tr>
                <th className="py-2.5 px-4 font-medium">SKU</th>
                <th className="py-2.5 px-4 font-medium">Product</th>
                <th className="py-2.5 px-4 font-medium text-right">Available</th>
                <th className="py-2.5 px-4 font-medium text-right">Reserved</th>
                <th className="py-2.5 px-4 font-medium text-right">ROP</th>
                <th className="py-2.5 px-4 font-medium text-right">Price</th>
                <th className="py-2.5 px-4 font-medium text-right">MRP</th>
                <th className="py-2.5 px-4 font-medium text-right">Nearest Expiry</th>
                <th className="py-2.5 px-4 font-medium text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {isLoading ? (
                <tr>
                  <td colSpan={9} className="py-8 text-center text-slate-500">
                    Loading store inventory...
                  </td>
                </tr>
              ) : (data?.items ?? []).length === 0 ? (
                <tr>
                  <td colSpan={9} className="py-8 text-center text-slate-500">
                    No inventory items match this filter.
                  </td>
                </tr>
              ) : (
                (data?.items ?? []).map((row) => {
                  const isOut = row.available_qty === 0;
                  const isLow = row.available_qty > 0 && row.available_qty <= row.reorder_point_qty;
                  return (
                    <tr key={row.id} className="hover:bg-slate-50">
                      <td className="py-2.5 px-4 font-mono-num text-slate-600">{row.sku_code}</td>
                      <td className="py-2.5 px-4">
                        <div className="font-medium text-slate-900">{row.name}</div>
                        <div className="text-slate-500">
                          {row.category} · v{row.version}
                          {isOut ? ' · Out of stock' : isLow ? ' · Low stock' : ''}
                        </div>
                      </td>
                      <td
                        className={`py-2.5 px-4 font-mono-num text-right font-medium ${
                          isOut ? 'text-red-700' : isLow ? 'text-amber-700' : 'text-slate-900'
                        }`}
                      >
                        {formatQty(row.available_qty, row.unit_type)}
                      </td>
                      <td className="py-2.5 px-4 font-mono-num text-right text-slate-600">
                        {formatQty(row.reserved_qty, row.unit_type)}
                      </td>
                      <td className="py-2.5 px-4 font-mono-num text-right text-slate-500">
                        {formatQty(row.reorder_point_qty, row.unit_type)}
                      </td>
                      <td className="py-2.5 px-4 font-mono-num text-right font-medium text-slate-900">
                        {formatINR(row.selling_price_paise)}
                      </td>
                      <td className="py-2.5 px-4 font-mono-num text-right text-slate-500">
                        {formatINR(row.mrp_paise)}
                      </td>
                      <td className="py-2.5 px-4 font-mono-num text-right text-slate-600">
                        {formatISTDate(row.nearest_expiry_date)}
                      </td>
                      <td className="py-2.5 px-4 text-right">
                        <Button variant="secondary" size="sm" onClick={() => startEdit(row)}>
                          Adjust
                        </Button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Edit Modal enforcing DB constraints */}
      {editing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
          <Card className="w-full max-w-md">
            <CardHeader>
              <h3 className="font-display text-sm font-semibold text-slate-900">
                Adjust Stock & Price · {editing.sku_code}
              </h3>
              <p className="text-xs text-slate-500 mt-0.5">{editing.name}</p>
            </CardHeader>
            <CardContent>
              {editError && (
                <div className="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800">
                  {editError}
                </div>
              )}
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  updateMutation.mutate({
                    inventoryId: editing.id,
                    available_qty: Number(editQty),
                    reserved_qty: Number(editReserved),
                    selling_price_paise: Math.round(Number(editPriceRupees) * 100),
                    version: editing.version,
                  });
                }}
                className="space-y-3"
              >
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-slate-700 mb-1">
                      Available ({editing.unit_type})
                    </label>
                    <input
                      type="number"
                      step={editing.is_loose_commodity ? '0.01' : '1'}
                      min="0"
                      required
                      value={editQty}
                      onChange={(e) => setEditQty(e.target.value)}
                      className="w-full h-9 rounded-lg border border-slate-300 px-3 text-xs font-mono-num"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-700 mb-1">
                      Reserved ({editing.unit_type})
                    </label>
                    <input
                      type="number"
                      step={editing.is_loose_commodity ? '0.01' : '1'}
                      min="0"
                      required
                      value={editReserved}
                      onChange={(e) => setEditReserved(e.target.value)}
                      className="w-full h-9 rounded-lg border border-slate-300 px-3 text-xs font-mono-num"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">
                    Selling Price (₹) — MRP cap {formatINR(editing.mrp_paise)}
                  </label>
                  <input
                    type="number"
                    step="1"
                    min="1"
                    required
                    value={editPriceRupees}
                    onChange={(e) => setEditPriceRupees(e.target.value)}
                    className="w-full h-9 rounded-lg border border-slate-300 px-3 text-xs font-mono-num"
                  />
                </div>

                <div className="text-xs text-slate-500">
                  Lock Version: <span className="font-mono-num">v{editing.version}</span> · Cost:{' '}
                  <span className="font-mono-num">{formatINR(editing.cost_price_paise)}</span>
                </div>

                <div className="flex justify-end gap-2 pt-2">
                  <Button type="button" variant="secondary" size="sm" onClick={() => setEditing(null)}>
                    Cancel
                  </Button>
                  <Button type="submit" size="sm" disabled={updateMutation.isPending}>
                    {updateMutation.isPending ? 'Saving...' : 'Commit Change'}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
};
