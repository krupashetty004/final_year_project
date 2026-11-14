import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, Search } from 'lucide-react';
import { apiFetch } from '../lib/api';
import { formatINR } from '../lib/formatters';
import { Card, CardContent, CardHeader } from '../components/ui/Card';
import { Button } from '../components/ui/Button';

interface ProductItem {
  id: string;
  sku_code: string;
  name: string;
  brand: string;
  variant: string;
  category: string;
  unit_type: string;
  pack_size_value: number;
  pack_size_unit: string;
  is_loose_commodity: number;
  mrp_paise: number;
  default_cost_paise: number;
  expiry_category: string;
  is_synthetic: number;
}

interface CatalogueResponse {
  total: number;
  limit: number;
  offset: number;
  categories: Array<{ category: string; count: number }>;
  items: ProductItem[];
}

export const ProductCataloguePage: React.FC = () => {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');
  const [looseOnly, setLooseOnly] = useState(false);
  const [page, setPage] = useState(0);
  const [showCreate, setShowCreate] = useState(false);
  const [formError, setFormError] = useState('');

  // Create Master Product Form State
  const [name, setName] = useState('');
  const [brand, setBrand] = useState('');
  const [newCategory, setNewCategory] = useState('Rice and grains');
  const [unitType, setUnitType] = useState<'pcs' | 'kg' | 'g' | 'l' | 'ml' | 'pack'>('kg');
  const [packVal, setPackVal] = useState('1');
  const [isLoose, setIsLoose] = useState(true);
  const [mrpRupees, setMrpRupees] = useState('72');
  const [costRupees, setCostRupees] = useState('58');
  const [expiryCategory, setExpiryCategory] = useState<'dairy' | 'bakery' | 'snacks' | 'grocery' | 'other'>('grocery');

  const limit = 25;

  const { data, isLoading } = useQuery({
    queryKey: ['products', search, category, looseOnly, page],
    queryFn: () =>
      apiFetch<CatalogueResponse>(
        `/products?search=${encodeURIComponent(search)}&category=${encodeURIComponent(category)}&loose_only=${looseOnly}&limit=${limit}&offset=${page * limit}`,
      ),
  });

  const createMutation = useMutation({
    mutationFn: () =>
      apiFetch('/products', {
        method: 'POST',
        body: JSON.stringify({
          name,
          brand,
          category: newCategory,
          unit_type: unitType,
          pack_size_value: Number(packVal),
          pack_size_unit: unitType,
          is_loose_commodity: isLoose,
          mrp_paise: Math.round(Number(mrpRupees) * 100),
          default_cost_paise: Math.round(Number(costRupees) * 100),
          expiry_category: expiryCategory,
        }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] });
      setShowCreate(false);
      setName('');
      setBrand('');
      setFormError('');
    },
    onError: (err) => {
      setFormError(err instanceof Error ? err.message : 'Failed to create product');
    },
  });

  const totalPages = data ? Math.ceil(data.total / limit) : 1;

  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h2 className="font-display text-lg font-semibold text-slate-900">
            Shared Master Product Catalogue
          </h2>
          <p className="text-xs text-slate-500">
            Canonical SKU identity shared across all Kirana stores · {data?.total ?? 0} total SKUs
          </p>
        </div>
        <Button size="sm" onClick={() => setShowCreate((v) => !v)}>
          <Plus className="h-4 w-4" />
          Add Master Product
        </Button>
      </div>

      {showCreate && (
        <Card>
          <CardHeader>
            <h3 className="font-display text-sm font-semibold text-slate-900">
              Create Master SKU (Packaged or Loose Commodity)
            </h3>
          </CardHeader>
          <CardContent>
            {formError && (
              <div className="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800">
                {formError}
              </div>
            )}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                createMutation.mutate();
              }}
              className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3"
            >
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Product Name</label>
                <input
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Toor Dal Unpolished"
                  className="w-full h-9 rounded-lg border border-slate-300 px-3 text-xs"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Brand</label>
                <input
                  required
                  value={brand}
                  onChange={(e) => setBrand(e.target.value)}
                  placeholder="Kirana Loose / Tata Sampann"
                  className="w-full h-9 rounded-lg border border-slate-300 px-3 text-xs"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Category</label>
                <select
                  value={newCategory}
                  onChange={(e) => setNewCategory(e.target.value)}
                  className="w-full h-9 rounded-lg border border-slate-300 px-2 text-xs bg-white"
                >
                  {(data?.categories ?? []).map((c) => (
                    <option key={c.category} value={c.category}>
                      {c.category}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Unit Type</label>
                <select
                  value={unitType}
                  onChange={(e) => setUnitType(e.target.value as typeof unitType)}
                  className="w-full h-9 rounded-lg border border-slate-300 px-2 text-xs bg-white"
                >
                  <option value="pcs">pcs</option>
                  <option value="kg">kg (Loose per kg)</option>
                  <option value="g">g</option>
                  <option value="l">l</option>
                  <option value="ml">ml</option>
                  <option value="pack">pack</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Pack Size</label>
                <input
                  type="number"
                  step="0.01"
                  required
                  value={packVal}
                  onChange={(e) => setPackVal(e.target.value)}
                  className="w-full h-9 rounded-lg border border-slate-300 px-3 text-xs font-mono-num"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">MRP (₹)</label>
                <input
                  type="number"
                  step="1"
                  required
                  value={mrpRupees}
                  onChange={(e) => setMrpRupees(e.target.value)}
                  className="w-full h-9 rounded-lg border border-slate-300 px-3 text-xs font-mono-num"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Default Cost (₹)</label>
                <input
                  type="number"
                  step="1"
                  required
                  value={costRupees}
                  onChange={(e) => setCostRupees(e.target.value)}
                  className="w-full h-9 rounded-lg border border-slate-300 px-3 text-xs font-mono-num"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Expiry Profile</label>
                <select
                  value={expiryCategory}
                  onChange={(e) => setExpiryCategory(e.target.value as typeof expiryCategory)}
                  className="w-full h-9 rounded-lg border border-slate-300 px-2 text-xs bg-white"
                >
                  <option value="grocery">Grocery</option>
                  <option value="dairy">Dairy</option>
                  <option value="bakery">Bread & Bakery</option>
                  <option value="snacks">Packaged Snacks</option>
                  <option value="other">Other</option>
                </select>
              </div>
              <div className="sm:col-span-2 lg:col-span-4 flex items-center justify-between pt-2">
                <label className="inline-flex items-center gap-2 text-xs text-slate-700">
                  <input
                    type="checkbox"
                    checked={isLoose}
                    onChange={(e) => setIsLoose(e.target.checked)}
                  />
                  Loose commodity sold by weight (rice, dal, sugar)
                </label>
                <div className="flex items-center gap-2">
                  <Button type="button" variant="secondary" size="sm" onClick={() => setShowCreate(false)}>
                    Cancel
                  </Button>
                  <Button type="submit" size="sm" disabled={createMutation.isPending}>
                    {createMutation.isPending ? 'Saving...' : 'Save Master SKU'}
                  </Button>
                </div>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {/* Search & Category Filters */}
      <Card>
        <CardContent className="p-4 flex flex-col md:flex-row md:items-center gap-3">
          <div className="relative flex-1">
            <Search className="h-4 w-4 text-slate-400 absolute left-3 top-2.5" />
            <input
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(0);
              }}
              placeholder="Search SKU code, product name, or brand..."
              className="w-full h-9 rounded-lg border border-slate-300 pl-9 pr-3 text-xs focus:outline-none focus:ring-2 focus:ring-teal-600"
            />
          </div>
          <select
            value={category}
            onChange={(e) => {
              setCategory(e.target.value);
              setPage(0);
            }}
            className="h-9 rounded-lg border border-slate-300 bg-white px-3 text-xs text-slate-800"
          >
            <option value="">All 9 Grocery Categories</option>
            {(data?.categories ?? []).map((c) => (
              <option key={c.category} value={c.category}>
                {c.category} ({c.count})
              </option>
            ))}
          </select>
          <label className="inline-flex items-center gap-2 text-xs text-slate-700 whitespace-nowrap">
            <input
              type="checkbox"
              checked={looseOnly}
              onChange={(e) => {
                setLooseOnly(e.target.checked);
                setPage(0);
              }}
            />
            Loose commodities only
          </label>
        </CardContent>

        <div className="overflow-x-auto border-t border-slate-200">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-200 bg-slate-50 text-slate-500">
              <tr>
                <th className="py-2.5 px-4 font-medium">SKU</th>
                <th className="py-2.5 px-4 font-medium">Product Name</th>
                <th className="py-2.5 px-4 font-medium">Brand</th>
                <th className="py-2.5 px-4 font-medium">Category</th>
                <th className="py-2.5 px-4 font-medium">Pack / Unit</th>
                <th className="py-2.5 px-4 font-medium text-right">Default Cost</th>
                <th className="py-2.5 px-4 font-medium text-right">MRP</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {isLoading ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-slate-500">
                    Loading catalogue...
                  </td>
                </tr>
              ) : (data?.items ?? []).length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-slate-500">
                    No matching products found.
                  </td>
                </tr>
              ) : (
                (data?.items ?? []).map((item) => (
                  <tr key={item.id} className="hover:bg-slate-50">
                    <td className="py-2.5 px-4 font-mono-num text-slate-600">{item.sku_code}</td>
                    <td className="py-2.5 px-4 font-medium text-slate-900">
                      {item.name}
                      {item.is_loose_commodity ? (
                        <span className="ml-2 text-slate-500 font-normal">· Loose / kg</span>
                      ) : null}
                    </td>
                    <td className="py-2.5 px-4 text-slate-700">{item.brand}</td>
                    <td className="py-2.5 px-4 text-slate-600">{item.category}</td>
                    <td className="py-2.5 px-4 font-mono-num text-slate-600">
                      {item.pack_size_value} {item.pack_size_unit} ({item.unit_type})
                    </td>
                    <td className="py-2.5 px-4 font-mono-num text-right text-slate-600">
                      {formatINR(item.default_cost_paise)}
                    </td>
                    <td className="py-2.5 px-4 font-mono-num text-right font-medium text-slate-900">
                      {formatINR(item.mrp_paise)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div className="border-t border-slate-200 px-4 py-3 flex items-center justify-between text-xs text-slate-600">
          <span className="font-mono-num">
            Page {page + 1} of {Math.max(1, totalPages)}
          </span>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="secondary"
              disabled={page === 0}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
            >
              Previous
            </Button>
            <Button
              size="sm"
              variant="secondary"
              disabled={page + 1 >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
};
