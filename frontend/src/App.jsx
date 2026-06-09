import { Routes, Route, Navigate } from 'react-router-dom';
import AppShell from './components/layout/AppShell';
import OverviewPage from './pages/OverviewPage';
import AlertQueuePage from './pages/AlertQueuePage';
import AlertDetailPage from './pages/AlertDetailPage';
import CustomerRiskPage from './pages/CustomerRiskPage';
import InvestigationGraphPage from './pages/InvestigationGraphPage';
import CaseWorkspacePage from './pages/CaseWorkspacePage';
import AuditLogPage from './pages/AuditLogPage';

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/alerts" element={<AlertQueuePage />} />
        <Route path="/alerts/:id" element={<AlertDetailPage />} />
        <Route path="/customers/:id" element={<CustomerRiskPage />} />
        <Route path="/customers/:id/graph" element={<InvestigationGraphPage />} />
        <Route path="/cases/:id" element={<CaseWorkspacePage />} />
        <Route path="/audit" element={<AuditLogPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}
