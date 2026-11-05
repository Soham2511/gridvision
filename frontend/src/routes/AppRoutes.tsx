import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { MainLayout } from '../layouts/MainLayout';
import { LandingPage } from '../pages/LandingPage';
import { LoginPage } from '../pages/LoginPage';
import { RegisterPage } from '../pages/RegisterPage';
import { ProtectedRoute } from '../components/auth/ProtectedRoute';
import { PersonaDashboardPage } from '../pages/PersonaDashboardPage';
import { HistoricalAnalysisPage } from '../pages/HistoricalAnalysisPage';
import { DataModelHealthPage } from '../pages/DataModelHealthPage';
import {
  AiAssistantPage,
  CommercialAssistantPage,
} from '../pages/AiAssistantPage';
import { OverviewPage } from '../pages/OverviewPage';
import { DemandForecastingPage } from '../pages/DemandForecastingPage';
import { PeakDemandPage } from '../pages/PeakDemandPage';
import { CustomerAnalyticsPage } from '../pages/CustomerAnalyticsPage';
import { EnergyInsightsPage } from '../pages/EnergyInsightsPage';
import { ProfilePage } from '../pages/ProfilePage';
import { GovernmentSegmentationPage } from '../pages/GovernmentSegmentationPage';
import { ComplaintCentrePage } from '../../../ai/residential/frontend/src/pages/ComplaintCentrePage';
import { usePersona } from '../context';
import { ReportsPage } from '../pages/ReportsPage';
import { NotificationsPage } from '../pages/NotificationsPage';
import { JSONReportGeneratorPage } from '../pages/JSONReportGeneratorPage';
import { TopHeader } from '../layouts/TopHeader';

const DeveloperJSONReportGeneratorPage: React.FC = () => (
  <div style={{ minHeight: '100vh', background: '#F8FAFC' }}>
    <TopHeader showLogo isAdmin />
    <div style={{ maxWidth: 1240, margin: '0 auto', padding: '2rem' }}>
      <JSONReportGeneratorPage />
    </div>
  </div>
);

const PersonaCustomerSegmentationPage: React.FC = () => {
  const { currentPersona } = usePersona();
  return currentPersona === 'government'
    ? <GovernmentSegmentationPage />
    : <CustomerAnalyticsPage />;
};

export const AppRoutes: React.FC = () => {
  return (
    <Routes>
      {/* 1. Public Landing Page & Auth Routes */}
      <Route path="/" element={<LandingPage />} />
      <Route path="/landing" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/commercial-assistant" element={<CommercialAssistantPage />} />

      {/* Dedicated Platform Data & Model Health Page (No Sidebar, Admin Header) */}
      <Route path="/health" element={<DataModelHealthPage />} />
      <Route path="/data-model-health" element={<Navigate to="/health" replace />} />
      <Route path="/developer/json-report-generator" element={<DeveloperJSONReportGeneratorPage />} />
      <Route path="/app/json-report-generator" element={<Navigate to="/developer/json-report-generator" replace />} />

      {/* 2. Authenticated Persona Workspace Shell */}
      <Route element={<ProtectedRoute><MainLayout /></ProtectedRoute>}>
        {/* Persona Navigation Tabs */}
        <Route path="/app" element={<PersonaDashboardPage />} />
        <Route path="/app/historical" element={<HistoricalAnalysisPage />} />
        <Route path="/app/complaints" element={<ComplaintCentrePage />} />
        <Route path="/complaints" element={<Navigate to="/app/complaints" replace />} />
        <Route path="/app/customers" element={<PersonaCustomerSegmentationPage />} />
        <Route path="/app/government/segmentation" element={<Navigate to="/app/customers" replace />} />
        <Route path="/app/health" element={<Navigate to="/health" replace />} />
        <Route path="/app/assistant" element={<AiAssistantPage />} />
        <Route path="/assistant" element={<Navigate to="/app/assistant" replace />} />
        <Route path="/app/reports" element={<ReportsPage />} />
        <Route path="/app/notifications" element={<NotificationsPage />} />
        <Route path="/models" element={<Navigate to="/health?tab=forecast" replace />} />
        <Route path="/models/customer" element={<Navigate to="/health?tab=bill-prediction" replace />} />

        {/* Deep Grid Analytics Suite */}
        <Route path="/overview" element={<OverviewPage />} />
        <Route path="/forecasting" element={<DemandForecastingPage />} />
        <Route path="/peak-demand" element={<PeakDemandPage />} />
        <Route path="/anomalies" element={<Navigate to="/health?tab=anomaly" replace />} />
        <Route path="/customers" element={<CustomerAnalyticsPage />} />
        <Route path="/insights" element={<EnergyInsightsPage />} />
        <Route path="/profile" element={<ProfilePage />} />
      </Route>

      {/* Catch-all fallback */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
};
