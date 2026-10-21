import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { MainLayout } from '../layouts/MainLayout';
import { LandingPage } from '../pages/LandingPage';
import { PersonaDashboardPage } from '../pages/PersonaDashboardPage';
import { HistoricalAnalysisPage } from '../pages/HistoricalAnalysisPage';
import { DataModelHealthPage } from '../pages/DataModelHealthPage';
import { AiAssistantPage } from '../pages/AiAssistantPage';
import { OverviewPage } from '../pages/OverviewPage';
import { DemandForecastingPage } from '../pages/DemandForecastingPage';
import { PeakDemandPage } from '../pages/PeakDemandPage';
import { AnomalyDetectionPage } from '../pages/AnomalyDetectionPage';
import { CustomerAnalyticsPage } from '../pages/CustomerAnalyticsPage';
import { EnergyInsightsPage } from '../pages/EnergyInsightsPage';
import { ProfilePage } from '../pages/ProfilePage';

export const AppRoutes: React.FC = () => {
  return (
    <Routes>
      {/* 1. Public Landing Page with 3 Persona Cards */}
      <Route path="/" element={<LandingPage />} />
      <Route path="/landing" element={<LandingPage />} />

      {/* Dedicated Platform Data & Model Health Page (No Sidebar, Admin Header) */}
      <Route path="/health" element={<DataModelHealthPage />} />
      <Route path="/data-model-health" element={<Navigate to="/health" replace />} />

      {/* 2. Authenticated / Selected Persona Workspace Shell */}
      <Route element={<MainLayout />}>
        {/* Persona Navigation Tabs */}
        <Route path="/app" element={<PersonaDashboardPage />} />
        <Route path="/app/historical" element={<HistoricalAnalysisPage />} />
        <Route path="/app/customers" element={<CustomerAnalyticsPage />} />
        <Route path="/app/health" element={<Navigate to="/health" replace />} />
        <Route path="/app/assistant" element={<AiAssistantPage />} />

        {/* Deep Grid Analytics Suite */}
        <Route path="/overview" element={<OverviewPage />} />
        <Route path="/forecasting" element={<DemandForecastingPage />} />
        <Route path="/peak-demand" element={<PeakDemandPage />} />
        <Route path="/anomalies" element={<AnomalyDetectionPage />} />
        <Route path="/customers" element={<CustomerAnalyticsPage />} />
        <Route path="/insights" element={<EnergyInsightsPage />} />
        <Route path="/profile" element={<ProfilePage />} />
      </Route>

      {/* Catch-all fallback */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
};
