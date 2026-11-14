import React, { useEffect, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { apiFetch } from '../lib/api';
import { useStoreContext } from '../hooks/useStoreContext';
import { Card, CardContent, CardHeader } from '../components/ui/Card';
import { Button } from '../components/ui/Button';

export const SettingsPage: React.FC = () => {
  const { i18n } = useTranslation();
  const { activeStore, activeStoreId } = useStoreContext();
  const queryClient = useQueryClient();

  const [minMarginPct, setMinMarginPct] = useState('10');
  const [clearanceAllowed, setClearanceAllowed] = useState(false);
  const [savedMsg, setSavedMsg] = useState('');

  useEffect(() => {
    if (activeStore) {
      setMinMarginPct(String(activeStore.default_min_margin_bps / 100));
      setClearanceAllowed(Boolean(activeStore.clearance_below_margin_allowed));
    }
  }, [activeStore]);

  const mutation = useMutation({
    mutationFn: () =>
      apiFetch(`/stores/${activeStoreId}/settings`, {
        method: 'PATCH',
        body: JSON.stringify({
          default_min_margin_bps: Math.round(Number(minMarginPct) * 100),
          clearance_below_margin_allowed: clearanceAllowed,
          preferred_language: i18n.language as 'en' | 'hi' | 'kn',
        }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['stores'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard', activeStoreId] });
      setSavedMsg('Store pricing & localization rules saved.');
    },
  });

  return (
    <div className="max-w-2xl space-y-6">
      <Card>
        <CardHeader>
          <h2 className="font-display text-base font-semibold text-slate-900">
            Store Pricing & Localization Settings
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            {activeStore ? `${activeStore.store_code} · ${activeStore.name}` : 'Select a store'}
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          {savedMsg && (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800">
              {savedMsg}
            </div>
          )}

          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">
              Default Minimum Margin (%)
            </label>
            <input
              type="number"
              min="0"
              max="50"
              step="0.5"
              value={minMarginPct}
              onChange={(e) => setMinMarginPct(e.target.value)}
              className="w-full h-10 rounded-lg border border-slate-300 px-3 text-sm font-mono-num"
            />
            <p className="mt-1 text-xs text-slate-500">
              Stored in basis points (bps). Selling price must remain ≥ cost × (1 + min margin) unless batch clearance is enabled.
            </p>
          </div>

          <label className="flex items-start gap-2.5 text-xs text-slate-700">
            <input
              type="checkbox"
              checked={clearanceAllowed}
              onChange={(e) => setClearanceAllowed(e.target.checked)}
              className="mt-0.5"
            />
            <span>
              Allow Smart Pricing Agent to recommend expiring-batch clearance below minimum margin (requires explicit owner approval per batch).
            </span>
          </label>

          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">
              Interface Language (react-i18next)
            </label>
            <select
              value={i18n.language}
              onChange={(e) => i18n.changeLanguage(e.target.value)}
              className="w-full h-10 rounded-lg border border-slate-300 bg-white px-3 text-sm"
            >
              <option value="en">English (en)</option>
              <option value="hi">हिन्दी (hi)</option>
              <option value="kn">ಕನ್ನಡ (kn)</option>
            </select>
          </div>

          <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
            {mutation.isPending ? 'Saving...' : 'Save Store Configuration'}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
};
