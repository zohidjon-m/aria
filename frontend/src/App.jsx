import { Routes, Route, Navigate } from 'react-router-dom';
import Nav from './components/Nav';
import AlertQueuePage from './pages/AlertQueuePage';
import AlertDetailPage from './pages/AlertDetailPage';
import CustomerRiskPage from './pages/CustomerRiskPage';
import InvestigationGraphPage from './pages/InvestigationGraphPage';
import CaseWorkspacePage from './pages/CaseWorkspacePage';

export default function App() {
  return (
    <div className="min-h-screen bg-dark-bg text-gray-100">
      <Nav />
      <div className="pt-12">
        <Routes>
          <Route path="/" element={<Navigate to="/alerts" replace />} />
          <Route path="/alerts" element={<AlertQueuePage />} />
          <Route path="/alerts/:id" element={<AlertDetailPage />} />
          <Route path="/customers/:id" element={<CustomerRiskPage />} />
          <Route path="/customers/:id/graph" element={<InvestigationGraphPage />} />
          <Route path="/cases/:id" element={<CaseWorkspacePage />} />
        </Routes>
      </div>
    </div>
  );
}
