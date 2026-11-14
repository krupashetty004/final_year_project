import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { StoreProvider } from './hooks/useStoreContext';
import { DashboardLayout } from './layouts/DashboardLayout';
import { StoreDashboardPage } from './routes/StoreDashboardPage';
import { LoginPage } from './routes/LoginPage';
import { ProductCataloguePage } from './routes/ProductCataloguePage';
import { InventoryManagementPage } from './routes/InventoryManagementPage';
import { SettingsPage } from './routes/SettingsPage';
import { AgentRunsPage } from './routes/AgentRunsPage';
import {
  DemandForecastingPage,
  DetectionReviewPage,
  PricingInboxPage,
  ProductAnalyticsPage,
  ReferenceImagesPage,
  ReorderRecommendationsPage,
  SmartPricingDashboardPage,
  UploadShelfPhotoPage,
} from './routes/StagePreviewPages';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <StoreProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<DashboardLayout />}>
              <Route path="/" element={<StoreDashboardPage />} />
              <Route path="/login" element={<LoginPage />} />
              <Route path="/catalogue" element={<ProductCataloguePage />} />
              <Route path="/inventory" element={<InventoryManagementPage />} />
              <Route path="/upload-photo" element={<UploadShelfPhotoPage />} />
              <Route path="/detection-review" element={<DetectionReviewPage />} />
              <Route path="/reference-images" element={<ReferenceImagesPage />} />
              <Route path="/forecasting" element={<DemandForecastingPage />} />
              <Route path="/reorders" element={<ReorderRecommendationsPage />} />
              <Route path="/pricing" element={<SmartPricingDashboardPage />} />
              <Route path="/pricing-inbox" element={<PricingInboxPage />} />
              <Route path="/analytics" element={<ProductAnalyticsPage />} />
              <Route path="/agent-runs" element={<AgentRunsPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </StoreProvider>
    </QueryClientProvider>
  );
}
