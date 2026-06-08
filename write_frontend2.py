import pathlib

SRC = pathlib.Path("D:/sejong_major/projects/compliance-agent/frontend/src")
COMPONENTS = SRC / "components"
PAGES = SRC / "pages"
PAGES.mkdir(exist_ok=True)

# ── Nav.jsx ──────────────────────────────────────────────────────────────────
(COMPONENTS / "Nav.jsx").write_text(r"""import { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { getOfficers, getHealth } from '../api/client';

export default function Nav() {
  const location = useLocation();
  const [officers, setOfficers] = useState([]);
  const [officerId, setOfficerId] = useState(localStorage.getItem('officerId') || '1');
  const [healthy, setHealthy] = useState(null);

  useEffect(() => {
    getOfficers().then(d => setOfficers(d)).catch(() => {});
    getHealth().then(() => setHealthy(true)).catch(() => setHealthy(false));
  }, []);

  function handleOfficerChange(e) {
    setOfficerId(e.target.value);
    localStorage.setItem('officerId', e.target.value);
    window.location.reload();
  }

  const navLink = (to, label) => (
    <Link
      to={to}
      className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
        location.pathname.startsWith(to)
          ? 'bg-brand-primary text-white'
          : 'text-gray-400 hover:text-white'
      }`}
    >
      {label}
    </Link>
  );

  return (
    <nav className="fixed top-0 left-0 right-0 z-40 h-12 bg-dark-panel border-b border-dark-border flex items-center px-4 gap-4">
      <span className="text-brand-primary font-bold text-sm tracking-wide mr-2">AML WORKBENCH</span>
      {navLink('/alerts', 'Alerts')}
      <div className="flex-1" />
      <select
        value={officerId}
        onChange={handleOfficerChange}
        className="bg-dark-bg border border-dark-border text-gray-300 text-xs rounded px-2 py-1"
      >
        {officers.length === 0 && <option value={officerId}>Officer #{officerId}</option>}
        {officers.map(o => (
          <option key={o.officer_id} value={String(o.officer_id)}>
            {o.full_name} ({o.role_name})
          </option>
        ))}
      </select>
      <span
        title={healthy === null ? 'Checking...' : healthy ? 'API healthy' : 'API unreachable'}
        className={`w-2 h-2 rounded-full ${
          healthy === null ? 'bg-gray-500' : healthy ? 'bg-green-500' : 'bg-red-500'
        }`}
      />
    </nav>
  );
}
""", encoding="utf-8")

# ── App.jsx ───────────────────────────────────────────────────────────────────
(SRC / "App.jsx").write_text(r"""import { Routes, Route, Navigate } from 'react-router-dom';
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
""", encoding="utf-8")

# ── AlertQueuePage.jsx ────────────────────────────────────────────────────────
(PAGES / "AlertQueuePage.jsx").write_text(r"""import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { getAlerts, getOfficers } from '../api/client';
import SeverityBadge from '../components/shared/SeverityBadge';
import StatusBadge from '../components/shared/StatusBadge';
import OfficerAvatar from '../components/shared/OfficerAvatar';
import SanctionsPepFlag from '../components/shared/SanctionsPepFlag';
import LoadingSpinner from '../components/shared/LoadingSpinner';
import ErrorMessage from '../components/shared/ErrorMessage';

const SEVERITIES = ['critical', 'high', 'medium', 'low'];
const STATUSES = ['open', 'under_review', 'escalated', 'dismissed', 'resolved'];
const SORT_OPTIONS = [
  { value: 'created_at', label: 'Newest' },
  { value: 'amount', label: 'Amount' },
  { value: 'severity', label: 'Severity' },
];

function ageLabel(dateStr) {
  const diff = Date.now() - new Date(dateStr).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export default function AlertQueuePage() {
  const [alerts, setAlerts] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [officers, setOfficers] = useState([]);
  const [filters, setFilters] = useState({ severity: '', status: 'open', assigned_to: '', sort_by: 'created_at' });

  const limit = 20;

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    const params = { page, limit, ...filters };
    Object.keys(params).forEach(k => !params[k] && delete params[k]);
    getAlerts(params)
      .then(d => { setAlerts(d.items); setTotal(d.total); })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [page, filters]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { getOfficers().then(setOfficers).catch(() => {}); }, []);

  function setFilter(key, val) {
    setFilters(f => ({ ...f, [key]: val }));
    setPage(1);
  }

  const start = (page - 1) * limit + 1;
  const end = Math.min(page * limit, total);

  return (
    <div className="p-4">
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <span className="text-xs text-gray-500 uppercase tracking-wide mr-1">Severity</span>
        {['', ...SEVERITIES].map(s => (
          <button
            key={s}
            onClick={() => setFilter('severity', s)}
            className={`px-2 py-0.5 rounded text-xs font-semibold border transition-colors ${
              filters.severity === s
                ? 'bg-brand-primary border-brand-primary text-white'
                : 'border-dark-border text-gray-400 hover:text-white'
            }`}
          >
            {s || 'All'}
          </button>
        ))}
        <span className="text-xs text-gray-500 uppercase tracking-wide ml-2 mr-1">Status</span>
        {['', ...STATUSES].map(s => (
          <button
            key={s}
            onClick={() => setFilter('status', s)}
            className={`px-2 py-0.5 rounded text-xs font-semibold border transition-colors ${
              filters.status === s
                ? 'bg-brand-primary border-brand-primary text-white'
                : 'border-dark-border text-gray-400 hover:text-white'
            }`}
          >
            {s || 'All'}
          </button>
        ))}
        <select
          value={filters.assigned_to}
          onChange={e => setFilter('assigned_to', e.target.value)}
          className="ml-2 bg-dark-panel border border-dark-border text-gray-300 text-xs rounded px-2 py-1"
        >
          <option value="">Any Officer</option>
          {officers.map(o => <option key={o.officer_id} value={o.officer_id}>{o.full_name}</option>)}
        </select>
        <select
          value={filters.sort_by}
          onChange={e => setFilter('sort_by', e.target.value)}
          className="bg-dark-panel border border-dark-border text-gray-300 text-xs rounded px-2 py-1"
        >
          {SORT_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <button onClick={load} className="ml-auto px-3 py-1 text-xs bg-dark-panel border border-dark-border rounded hover:border-brand-primary text-gray-300">
          Refresh
        </button>
      </div>

      {error && <ErrorMessage message={error} />}
      {loading ? <LoadingSpinner /> : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="border-b border-dark-border text-gray-500 uppercase tracking-wide">
                  <th className="pb-2 text-left w-20">Severity</th>
                  <th className="pb-2 text-left w-16">ID</th>
                  <th className="pb-2 text-left">Rule</th>
                  <th className="pb-2 text-left">Customer</th>
                  <th className="pb-2 text-right w-28">Amount USD</th>
                  <th className="pb-2 text-left w-28">Status</th>
                  <th className="pb-2 text-left w-16">Age</th>
                  <th className="pb-2 text-left w-8">Officer</th>
                  <th className="pb-2 text-left w-20">Flags</th>
                </tr>
              </thead>
              <tbody>
                {alerts.map(a => (
                  <tr key={a.alert_id} className="border-b border-dark-border hover:bg-dark-panel transition-colors">
                    <td className="py-2"><SeverityBadge severity={a.severity} /></td>
                    <td className="py-2">
                      <Link to={`/alerts/${a.alert_id}`} className="text-brand-primary hover:underline font-mono">
                        #{a.alert_id}
                      </Link>
                    </td>
                    <td className="py-2 text-gray-300 truncate max-w-xs">{a.rule_name}</td>
                    <td className="py-2">
                      <Link to={`/customers/${a.customer_id}`} className="text-brand-accent hover:underline">
                        {a.customer_name}
                      </Link>
                    </td>
                    <td className="py-2 text-right font-mono text-gray-200">
                      {a.amount_usd != null ? `$${Number(a.amount_usd).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—'}
                    </td>
                    <td className="py-2"><StatusBadge status={a.status} /></td>
                    <td className="py-2 text-gray-500">{ageLabel(a.created_at)}</td>
                    <td className="py-2">
                      {a.officer_name && <OfficerAvatar name={a.officer_name} />}
                    </td>
                    <td className="py-2 flex gap-1">
                      {a.has_sanctions_hit && <SanctionsPepFlag type="sanctions" />}
                      {a.has_pep_hit && <SanctionsPepFlag type="pep" />}
                    </td>
                  </tr>
                ))}
                {alerts.length === 0 && (
                  <tr><td colSpan={9} className="py-8 text-center text-gray-500">No alerts match the current filters.</td></tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between mt-3 text-xs text-gray-500">
            <span>{total > 0 ? `${start}–${end} of ${total}` : '0 results'}</span>
            <div className="flex gap-2">
              <button onClick={() => setPage(p => p - 1)} disabled={page === 1} className="px-2 py-1 border border-dark-border rounded disabled:opacity-30 hover:border-brand-primary">Prev</button>
              <button onClick={() => setPage(p => p + 1)} disabled={end >= total} className="px-2 py-1 border border-dark-border rounded disabled:opacity-30 hover:border-brand-primary">Next</button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
""", encoding="utf-8")

# ── AlertDetailPage.jsx ───────────────────────────────────────────────────────
(PAGES / "AlertDetailPage.jsx").write_text(r"""import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  getAlert, postAlertComment, postTriageRun, getAgentRun,
} from '../api/client';
import SeverityBadge from '../components/shared/SeverityBadge';
import StatusBadge from '../components/shared/StatusBadge';
import OfficerAvatar from '../components/shared/OfficerAvatar';
import SanctionsPepFlag from '../components/shared/SanctionsPepFlag';
import LoadingSpinner from '../components/shared/LoadingSpinner';
import ErrorMessage from '../components/shared/ErrorMessage';
import AgentProposalPanel from '../components/AgentProposalPanel';
import AgentTraceDrawer from '../components/AgentTraceDrawer';
import DispositionControls from '../components/DispositionControls';

function FatfBadge({ status }) {
  if (!status || status === 'none') return null;
  const cls = status === 'blacklist' ? 'bg-red-900 text-red-300' : 'bg-amber-900 text-amber-300';
  return <span className={`text-xs px-1 py-0.5 rounded font-mono uppercase ${cls}`}>{status}</span>;
}

function Card({ title, children }) {
  return (
    <div className="bg-dark-panel border border-dark-border rounded p-3 mb-3">
      {title && <div className="text-xs uppercase tracking-wide text-gray-500 mb-2 font-semibold">{title}</div>}
      {children}
    </div>
  );
}

function Field({ label, value }) {
  return (
    <div className="flex gap-2 text-xs mb-1">
      <span className="text-gray-500 w-32 shrink-0">{label}</span>
      <span className="text-gray-200 break-all">{value ?? '—'}</span>
    </div>
  );
}

export default function AlertDetailPage() {
  const { id } = useParams();
  const [alert, setAlert] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [comment, setComment] = useState('');
  const [commenting, setCommenting] = useState(false);
  const [agentRun, setAgentRun] = useState(null);
  const [triaging, setTriaging] = useState(false);
  const [triageError, setTriageError] = useState(null);
  const [traceOpen, setTraceOpen] = useState(false);

  function loadAlert() {
    setLoading(true);
    getAlert(id)
      .then(d => {
        setAlert(d);
        if (d.latest_run_id && !agentRun) {
          getAgentRun(d.latest_run_id).then(setAgentRun).catch(() => {});
        }
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }

  useEffect(() => { loadAlert(); }, [id]);

  function handleComment(e) {
    e.preventDefault();
    if (!comment.trim()) return;
    setCommenting(true);
    postAlertComment(id, comment)
      .then(() => { setComment(''); loadAlert(); })
      .catch(e => alert(e.message))
      .finally(() => setCommenting(false));
  }

  async function handleTriage() {
    setTriaging(true);
    setTriageError(null);
    try {
      const result = await postTriageRun(id);
      const run = await getAgentRun(result.run_id);
      setAgentRun(run);
    } catch (e) {
      setTriageError(e.response?.data?.detail || e.message);
    } finally {
      setTriaging(false);
    }
  }

  if (loading) return <div className="p-4"><LoadingSpinner /></div>;
  if (error) return <div className="p-4"><ErrorMessage message={error} /></div>;
  if (!alert) return null;

  return (
    <div className="p-4">
      <div className="text-xs text-gray-500 mb-3">
        <Link to="/alerts" className="hover:text-brand-primary">Alerts</Link>
        <span className="mx-1">/</span>
        <span className="text-gray-300">#{alert.alert_id}</span>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {/* Left column */}
        <div>
          <Card title="Alert">
            <div className="flex gap-2 items-center mb-2">
              <SeverityBadge severity={alert.severity} />
              <StatusBadge status={alert.status} />
            </div>
            <Field label="Alert ID" value={`#${alert.alert_id}`} />
            <Field label="Rule" value={alert.rule_name} />
            <Field label="Created" value={new Date(alert.created_at).toLocaleString()} />
            <Field label="Assigned To" value={alert.officer_name} />
          </Card>

          <Card title="Triggering Transaction">
            <Field label="Amount" value={alert.amount != null ? `${alert.amount} ${alert.currency_code}` : '—'} />
            <Field label="Amount USD" value={alert.amount_usd != null ? `$${Number(alert.amount_usd).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '—'} />
            <Field label="Type" value={alert.transaction_type} />
            <div className="flex gap-2 text-xs mb-1">
              <span className="text-gray-500 w-32 shrink-0">Destination</span>
              <span className="text-gray-200 flex items-center gap-1">
                {alert.destination_country_name || alert.destination_country || '—'}
                <FatfBadge status={alert.destination_fatf_status} />
              </span>
            </div>
            <Field label="Date" value={alert.transaction_date ? new Date(alert.transaction_date).toLocaleDateString() : '—'} />
            <Field label="Reference" value={alert.reference_number} />
          </Card>

          <Card title="Customer">
            <div className="flex items-center gap-2 mb-2">
              <Link to={`/customers/${alert.customer_id}`} className="text-brand-accent hover:underline font-semibold text-sm">
                {alert.customer_name}
              </Link>
              {alert.has_sanctions_hit && <SanctionsPepFlag type="sanctions" />}
              {alert.has_pep_hit && <SanctionsPepFlag type="pep" />}
            </div>
            <Field label="Risk Level" value={alert.risk_level} />
            <Field label="KYC Status" value={alert.kyc_status} />
            <Field label="Nationality" value={alert.nationality_name || alert.nationality} />
          </Card>

          {alert.recent_transactions?.length > 0 && (
            <Card title="Recent Transactions">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-gray-500 border-b border-dark-border">
                    <th className="pb-1 text-left">Date</th>
                    <th className="pb-1 text-left">Type</th>
                    <th className="pb-1 text-right">Amount USD</th>
                    <th className="pb-1 text-left">Country</th>
                    <th className="pb-1 text-center">Flag</th>
                  </tr>
                </thead>
                <tbody>
                  {alert.recent_transactions.slice(0, 10).map(t => (
                    <tr key={t.transaction_id} className="border-b border-dark-border">
                      <td className="py-1 text-gray-500">{new Date(t.created_at).toLocaleDateString()}</td>
                      <td className="py-1 text-gray-300">{t.transaction_type}</td>
                      <td className="py-1 text-right font-mono text-gray-200">
                        {t.amount_usd != null ? `$${Number(t.amount_usd).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '—'}
                      </td>
                      <td className="py-1 text-gray-400">{t.destination_country || '—'}</td>
                      <td className="py-1 text-center">{t.is_flagged ? <span className="text-red-400">!</span> : ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}

          {alert.prior_alerts?.length > 0 && (
            <Card title="Prior Alerts (top 5)">
              {alert.prior_alerts.slice(0, 5).map(a => (
                <div key={a.alert_id} className="flex items-center gap-2 text-xs py-1 border-b border-dark-border last:border-0">
                  <SeverityBadge severity={a.severity} />
                  <Link to={`/alerts/${a.alert_id}`} className="text-brand-primary hover:underline">#{a.alert_id}</Link>
                  <span className="text-gray-400 truncate">{a.rule_name}</span>
                  <span className="ml-auto text-gray-500">{new Date(a.created_at).toLocaleDateString()}</span>
                  <StatusBadge status={a.status} />
                </div>
              ))}
            </Card>
          )}

          {alert.prior_cases?.length > 0 && (
            <Card title="Prior Cases (top 5)">
              {alert.prior_cases.slice(0, 5).map(c => (
                <div key={c.case_id} className="flex items-center gap-2 text-xs py-1 border-b border-dark-border last:border-0">
                  <Link to={`/cases/${c.case_id}`} className="text-brand-primary hover:underline">#{c.case_id}</Link>
                  <span className="text-gray-400">{c.case_type}</span>
                  <StatusBadge status={c.status} />
                  <span className="ml-auto text-gray-500">{new Date(c.opened_at).toLocaleDateString()}</span>
                </div>
              ))}
            </Card>
          )}

          <Card title="Comments">
            {alert.comments?.length === 0 && <p className="text-xs text-gray-500">No comments yet.</p>}
            {alert.comments?.map(c => (
              <div key={c.comment_id} className="flex gap-2 mb-3">
                <OfficerAvatar name={c.officer_name} />
                <div>
                  <div className="flex items-baseline gap-2">
                    <span className="text-xs font-semibold text-gray-300">{c.officer_name}</span>
                    <span className="text-xs text-gray-600">{new Date(c.created_at).toLocaleString()}</span>
                  </div>
                  <p className="text-xs text-gray-300 mt-0.5">{c.comment}</p>
                </div>
              </div>
            ))}
            <form onSubmit={handleComment} className="mt-2 flex gap-2">
              <input
                value={comment}
                onChange={e => setComment(e.target.value)}
                placeholder="Add a comment..."
                className="flex-1 bg-dark-bg border border-dark-border rounded px-2 py-1 text-xs text-gray-200 focus:outline-none focus:border-brand-primary"
              />
              <button
                type="submit"
                disabled={!comment.trim() || commenting}
                className="px-3 py-1 text-xs bg-brand-primary rounded disabled:opacity-40 hover:opacity-90"
              >
                Post
              </button>
            </form>
          </Card>
        </div>

        {/* Right column */}
        <div>
          <Card>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs uppercase tracking-wide text-gray-500 font-semibold">Agent Triage</span>
              <button
                onClick={handleTriage}
                disabled={triaging}
                className="px-3 py-1 text-xs bg-brand-primary rounded hover:opacity-90 disabled:opacity-40 flex items-center gap-1"
              >
                {triaging ? <><LoadingSpinner size="sm" /> Running...</> : 'Run Agent Triage'}
              </button>
            </div>
            {triageError && <ErrorMessage message={triageError} />}
            {agentRun ? (
              <AgentProposalPanel run={agentRun} onViewTrace={() => setTraceOpen(true)} />
            ) : (
              <p className="text-xs text-gray-500">No agent run yet. Click "Run Agent Triage" to analyze this alert.</p>
            )}
          </Card>

          <Card title="Disposition">
            <DispositionControls alertId={id} onSuccess={loadAlert} />
          </Card>
        </div>
      </div>

      <AgentTraceDrawer
        runId={agentRun?.run?.run_id}
        isOpen={traceOpen}
        onClose={() => setTraceOpen(false)}
      />
    </div>
  );
}
""", encoding="utf-8")

# ── CustomerRiskPage.jsx ──────────────────────────────────────────────────────
(PAGES / "CustomerRiskPage.jsx").write_text(r"""import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getCustomer, getCustomerTransactions, getCustomerCases } from '../api/client';
import StatusBadge from '../components/shared/StatusBadge';
import SanctionsPepFlag from '../components/shared/SanctionsPepFlag';
import LoadingSpinner from '../components/shared/LoadingSpinner';
import ErrorMessage from '../components/shared/ErrorMessage';

const TABS = ['Overview', 'Transactions', 'Cases', 'Risk History'];

function Field({ label, value }) {
  return (
    <div className="flex gap-2 text-xs mb-1">
      <span className="text-gray-500 w-36 shrink-0">{label}</span>
      <span className="text-gray-200">{value ?? '—'}</span>
    </div>
  );
}

function Card({ title, children }) {
  return (
    <div className="bg-dark-panel border border-dark-border rounded p-3 mb-3">
      {title && <div className="text-xs uppercase tracking-wide text-gray-500 mb-2 font-semibold">{title}</div>}
      {children}
    </div>
  );
}

function RiskLevelBadge({ level }) {
  const map = { critical: 'text-red-400', high: 'text-orange-400', medium: 'text-yellow-400', low: 'text-green-400' };
  return <span className={`text-xs font-mono uppercase font-bold ${map[level] || 'text-gray-400'}`}>{level || '—'}</span>;
}

export default function CustomerRiskPage() {
  const { id } = useParams();
  const [customer, setCustomer] = useState(null);
  const [tab, setTab] = useState('Overview');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [txPage, setTxPage] = useState(1);
  const [txData, setTxData] = useState(null);
  const [txLoading, setTxLoading] = useState(false);
  const [cases, setCases] = useState(null);
  const [casesLoading, setCasesLoading] = useState(false);
  const [isFlagged, setIsFlagged] = useState(null);

  useEffect(() => {
    setLoading(true);
    getCustomer(id)
      .then(setCustomer)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    if (tab !== 'Transactions') return;
    setTxLoading(true);
    const params = { page: txPage, limit: 50 };
    if (isFlagged !== null) params.is_flagged = isFlagged;
    getCustomerTransactions(id, params)
      .then(setTxData)
      .finally(() => setTxLoading(false));
  }, [id, tab, txPage, isFlagged]);

  useEffect(() => {
    if (tab !== 'Cases') return;
    setCasesLoading(true);
    getCustomerCases(id)
      .then(setCases)
      .finally(() => setCasesLoading(false));
  }, [id, tab]);

  if (loading) return <div className="p-4"><LoadingSpinner /></div>;
  if (error) return <div className="p-4"><ErrorMessage message={error} /></div>;
  if (!customer) return null;

  const hasSanctions = customer.sanctions_matches?.length > 0;
  const hasPep = customer.pep_matches?.length > 0;

  return (
    <div className="p-4">
      <div className="text-xs text-gray-500 mb-3">
        <Link to="/alerts" className="hover:text-brand-primary">Alerts</Link>
        <span className="mx-1">/</span>
        <span className="text-gray-300">{customer.full_name}</span>
        <Link to={`/customers/${id}/graph`} className="ml-4 text-brand-primary hover:underline text-xs">View Transaction Graph</Link>
      </div>

      <div className="flex items-center gap-3 mb-4">
        <h1 className="text-lg font-semibold text-gray-100">{customer.full_name}</h1>
        <RiskLevelBadge level={customer.risk_level} />
        {hasSanctions && <SanctionsPepFlag type="sanctions" />}
        {hasPep && <SanctionsPepFlag type="pep" />}
      </div>

      <div className="flex gap-1 mb-4 border-b border-dark-border">
        {TABS.map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-1.5 text-xs font-medium border-b-2 transition-colors ${
              tab === t ? 'border-brand-primary text-brand-primary' : 'border-transparent text-gray-500 hover:text-gray-300'
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === 'Overview' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div>
            <Card title="KYC Profile">
              <Field label="Customer ID" value={customer.customer_id} />
              <Field label="Date of Birth" value={customer.date_of_birth} />
              <Field label="Nationality" value={`${customer.nationality_name || ''} (${customer.nationality || '—'})`} />
              <Field label="KYC Status" value={customer.kyc_status} />
              <Field label="KYC Verified At" value={customer.kyc_verified_at ? new Date(customer.kyc_verified_at).toLocaleDateString() : null} />
              <Field label="Customer Since" value={customer.customer_since ? new Date(customer.customer_since).toLocaleDateString() : null} />
              <Field label="Branch" value={customer.branch_name} />
              <Field label="Email" value={customer.email} />
              <Field label="Phone" value={customer.phone} />
            </Card>

            <Card title="Sanctions / PEP">
              {!hasSanctions && !hasPep ? (
                <p className="text-xs text-green-400 font-semibold">No active sanctions or PEP matches.</p>
              ) : (
                <>
                  {hasSanctions && (
                    <div className="mb-2">
                      <p className="text-xs text-red-400 font-semibold mb-1">Sanctions Hits</p>
                      {customer.sanctions_matches.map((m, i) => (
                        <div key={i} className="text-xs text-gray-300 py-0.5 border-b border-dark-border last:border-0">
                          {m.matched_name} — {m.entity_type} — {m.sanction_type} ({m.listed_by})
                        </div>
                      ))}
                    </div>
                  )}
                  {hasPep && (
                    <div>
                      <p className="text-xs text-amber-400 font-semibold mb-1">PEP Hits</p>
                      {customer.pep_matches.map((m, i) => (
                        <div key={i} className="text-xs text-gray-300 py-0.5 border-b border-dark-border last:border-0">
                          {m.matched_name} — {m.position} — {m.pep_level} ({m.country_code})
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </Card>
          </div>

          <div>
            <Card title="Accounts">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-gray-500 border-b border-dark-border">
                    <th className="pb-1 text-left">Account</th>
                    <th className="pb-1 text-left">Type</th>
                    <th className="pb-1 text-right">Balance</th>
                    <th className="pb-1 text-left">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {customer.accounts?.map(a => (
                    <tr key={a.account_id} className="border-b border-dark-border">
                      <td className="py-1 font-mono text-gray-300">{a.account_number}</td>
                      <td className="py-1 text-gray-400">{a.account_type}</td>
                      <td className="py-1 text-right font-mono text-gray-200">
                        {a.current_balance != null ? `$${Number(a.current_balance).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '—'}
                      </td>
                      <td className="py-1"><StatusBadge status={a.status} /></td>
                    </tr>
                  ))}
                  {!customer.accounts?.length && <tr><td colSpan={4} className="py-2 text-gray-500">No accounts.</td></tr>}
                </tbody>
              </table>
            </Card>

            {customer.baseline && (
              <Card title="Transaction Baseline">
                <Field label="Avg Transaction" value={customer.baseline.avg_transaction != null ? `$${Number(customer.baseline.avg_transaction).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : null} />
                <Field label="Max Transaction" value={customer.baseline.max_transaction != null ? `$${Number(customer.baseline.max_transaction).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : null} />
                <Field label="Monthly Volume" value={customer.baseline.monthly_volume != null ? `$${Number(customer.baseline.monthly_volume).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : null} />
                <Field label="International %" value={customer.baseline.international_pct != null ? `${customer.baseline.international_pct}%` : null} />
                <Field label="Cash %" value={customer.baseline.cash_pct != null ? `${customer.baseline.cash_pct}%` : null} />
                <Field label="Typical Countries" value={customer.baseline.typical_countries?.join(', ')} />
                <Field label="Computed At" value={customer.baseline.computed_at ? new Date(customer.baseline.computed_at).toLocaleDateString() : null} />
              </Card>
            )}

            {customer.latest_risk_score && (
              <Card title="Latest Risk Score">
                <Field label="Score" value={`${customer.latest_risk_score.score} / 100`} />
                <Field label="Level" value={<RiskLevelBadge level={customer.latest_risk_score.score_level} />} />
                <Field label="Computed By" value={customer.latest_risk_score.computed_by} />
                <Field label="Computed At" value={customer.latest_risk_score.computed_at ? new Date(customer.latest_risk_score.computed_at).toLocaleString() : null} />
                {customer.latest_risk_score.reasoning && (
                  <div className="mt-2 text-xs text-gray-400 bg-dark-bg rounded p-2">{customer.latest_risk_score.reasoning}</div>
                )}
              </Card>
            )}
          </div>
        </div>
      )}

      {tab === 'Transactions' && (
        <div>
          <div className="flex gap-2 mb-3 text-xs">
            {[null, true, false].map(v => (
              <button
                key={String(v)}
                onClick={() => { setIsFlagged(v); setTxPage(1); }}
                className={`px-2 py-0.5 rounded border transition-colors ${isFlagged === v ? 'bg-brand-primary border-brand-primary text-white' : 'border-dark-border text-gray-400 hover:text-white'}`}
              >
                {v === null ? 'All' : v ? 'Flagged' : 'Not Flagged'}
              </button>
            ))}
          </div>
          {txLoading ? <LoadingSpinner /> : txData && (
            <>
              <table className="w-full text-xs border-collapse">
                <thead>
                  <tr className="border-b border-dark-border text-gray-500 uppercase tracking-wide">
                    <th className="pb-2 text-left">Date</th>
                    <th className="pb-2 text-left">Type</th>
                    <th className="pb-2 text-right">Amount USD</th>
                    <th className="pb-2 text-left">Country</th>
                    <th className="pb-2 text-left">Account</th>
                    <th className="pb-2 text-center">Flagged</th>
                  </tr>
                </thead>
                <tbody>
                  {txData.items.map(t => (
                    <tr key={t.transaction_id} className="border-b border-dark-border hover:bg-dark-panel">
                      <td className="py-1.5 text-gray-500">{new Date(t.created_at).toLocaleDateString()}</td>
                      <td className="py-1.5 text-gray-300">{t.transaction_type}</td>
                      <td className="py-1.5 text-right font-mono text-gray-200">
                        {t.amount_usd != null ? `$${Number(t.amount_usd).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '—'}
                      </td>
                      <td className="py-1.5 text-gray-400">{t.destination_country_name || t.destination_country || '—'}</td>
                      <td className="py-1.5 font-mono text-gray-500">{t.account_number}</td>
                      <td className="py-1.5 text-center">{t.is_flagged ? <span className="text-red-400 font-bold">!</span> : ''}</td>
                    </tr>
                  ))}
                  {txData.items.length === 0 && <tr><td colSpan={6} className="py-4 text-center text-gray-500">No transactions.</td></tr>}
                </tbody>
              </table>
              <div className="flex items-center justify-between mt-2 text-xs text-gray-500">
                <span>{txData.total} total</span>
                <div className="flex gap-2">
                  <button onClick={() => setTxPage(p => p - 1)} disabled={txPage === 1} className="px-2 py-1 border border-dark-border rounded disabled:opacity-30">Prev</button>
                  <button onClick={() => setTxPage(p => p + 1)} disabled={txData.items.length < 50} className="px-2 py-1 border border-dark-border rounded disabled:opacity-30">Next</button>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {tab === 'Cases' && (
        casesLoading ? <LoadingSpinner /> : (
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="border-b border-dark-border text-gray-500 uppercase tracking-wide">
                <th className="pb-2 text-left">Case</th>
                <th className="pb-2 text-left">Type</th>
                <th className="pb-2 text-left">Priority</th>
                <th className="pb-2 text-left">Status</th>
                <th className="pb-2 text-left">Officer</th>
                <th className="pb-2 text-left">Opened</th>
                <th className="pb-2 text-right">Alerts</th>
              </tr>
            </thead>
            <tbody>
              {(cases || []).map(c => (
                <tr key={c.case_id} className="border-b border-dark-border hover:bg-dark-panel">
                  <td className="py-1.5"><Link to={`/cases/${c.case_id}`} className="text-brand-primary hover:underline">#{c.case_id}</Link></td>
                  <td className="py-1.5 text-gray-300">{c.case_type}</td>
                  <td className="py-1.5 text-gray-400">{c.priority}</td>
                  <td className="py-1.5"><StatusBadge status={c.status} /></td>
                  <td className="py-1.5 text-gray-400">{c.officer_name || '—'}</td>
                  <td className="py-1.5 text-gray-500">{new Date(c.opened_at).toLocaleDateString()}</td>
                  <td className="py-1.5 text-right text-gray-400">{c.linked_alert_count}</td>
                </tr>
              ))}
              {!cases?.length && <tr><td colSpan={7} className="py-4 text-center text-gray-500">No cases.</td></tr>}
            </tbody>
          </table>
        )
      )}

      {tab === 'Risk History' && (
        <p className="text-xs text-gray-500">Risk score history is shown in the Overview tab (latest score only). Full history requires a dedicated risk_scores endpoint.</p>
      )}
    </div>
  );
}
""", encoding="utf-8")

# ── CaseWorkspacePage.jsx ─────────────────────────────────────────────────────
(PAGES / "CaseWorkspacePage.jsx").write_text(r"""import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getCase, linkAlertToCase } from '../api/client';
import StatusBadge from '../components/shared/StatusBadge';
import SeverityBadge from '../components/shared/SeverityBadge';
import OfficerAvatar from '../components/shared/OfficerAvatar';
import LoadingSpinner from '../components/shared/LoadingSpinner';
import ErrorMessage from '../components/shared/ErrorMessage';

function Field({ label, value }) {
  return (
    <div className="flex gap-2 text-xs mb-1">
      <span className="text-gray-500 w-32 shrink-0">{label}</span>
      <span className="text-gray-200">{value ?? '—'}</span>
    </div>
  );
}

function PriorityBadge({ priority }) {
  const map = { critical: 'text-red-400', high: 'text-orange-400', medium: 'text-yellow-400', low: 'text-green-400' };
  return <span className={`text-xs font-mono uppercase font-bold ${map[priority] || 'text-gray-400'}`}>{priority || '—'}</span>;
}

export default function CaseWorkspacePage() {
  const { id } = useParams();
  const [caseData, setCaseData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [linkAlertId, setLinkAlertId] = useState('');
  const [linking, setLinking] = useState(false);
  const [linkError, setLinkError] = useState(null);

  function loadCase() {
    setLoading(true);
    getCase(id)
      .then(setCaseData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }

  useEffect(() => { loadCase(); }, [id]);

  function handleLinkAlert(e) {
    e.preventDefault();
    if (!linkAlertId.trim()) return;
    setLinking(true);
    setLinkError(null);
    linkAlertToCase(id, parseInt(linkAlertId))
      .then(() => { setLinkAlertId(''); loadCase(); })
      .catch(e => setLinkError(e.response?.data?.detail || e.message))
      .finally(() => setLinking(false));
  }

  if (loading) return <div className="p-4"><LoadingSpinner /></div>;
  if (error) return <div className="p-4"><ErrorMessage message={error} /></div>;
  if (!caseData) return null;

  return (
    <div className="p-4 max-w-5xl mx-auto">
      <div className="text-xs text-gray-500 mb-3">
        <Link to="/alerts" className="hover:text-brand-primary">Alerts</Link>
        <span className="mx-1">/</span>
        <span className="text-gray-300">Case #{caseData.case_id}</span>
      </div>

      <div className="flex items-center gap-3 mb-4">
        <h1 className="text-lg font-semibold text-gray-100">Case #{caseData.case_id}</h1>
        <PriorityBadge priority={caseData.priority} />
        <StatusBadge status={caseData.status} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        <div className="bg-dark-panel border border-dark-border rounded p-3">
          <div className="text-xs uppercase tracking-wide text-gray-500 mb-2 font-semibold">Case Details</div>
          <Field label="Case Type" value={caseData.case_type} />
          <Field label="Customer" value={
            caseData.customer_id ? (
              <Link to={`/customers/${caseData.customer_id}`} className="text-brand-accent hover:underline">
                {caseData.customer_name || `#${caseData.customer_id}`}
              </Link>
            ) : null
          } />
          <Field label="Opened" value={caseData.opened_at ? new Date(caseData.opened_at).toLocaleString() : null} />
          <Field label="Closed" value={caseData.closed_at ? new Date(caseData.closed_at).toLocaleString() : null} />
          <div className="flex gap-2 text-xs mb-1">
            <span className="text-gray-500 w-32 shrink-0">Assigned Officer</span>
            <span className="flex items-center gap-1">
              {caseData.officer_name && <OfficerAvatar name={caseData.officer_name} />}
              <span className="text-gray-200">{caseData.officer_name || '—'}</span>
            </span>
          </div>
        </div>

        <div className="bg-dark-panel border border-dark-border rounded p-3">
          <div className="text-xs uppercase tracking-wide text-gray-500 mb-2 font-semibold">Summary</div>
          <p className="text-xs text-gray-300 leading-relaxed">
            {caseData.summary || <span className="text-gray-600 italic">No summary provided.</span>}
          </p>
          {caseData.resolution && (
            <div className="mt-3">
              <div className="text-xs uppercase tracking-wide text-gray-500 mb-1 font-semibold">Resolution</div>
              <p className="text-xs text-gray-300 leading-relaxed">{caseData.resolution}</p>
            </div>
          )}
        </div>
      </div>

      <div className="bg-dark-panel border border-dark-border rounded p-3 mb-4">
        <div className="flex items-center justify-between mb-3">
          <div className="text-xs uppercase tracking-wide text-gray-500 font-semibold">Linked Alerts</div>
          <form onSubmit={handleLinkAlert} className="flex gap-2">
            <input
              value={linkAlertId}
              onChange={e => setLinkAlertId(e.target.value)}
              placeholder="Alert ID"
              type="number"
              className="w-24 bg-dark-bg border border-dark-border rounded px-2 py-1 text-xs text-gray-200 focus:outline-none focus:border-brand-primary"
            />
            <button
              type="submit"
              disabled={!linkAlertId.trim() || linking}
              className="px-3 py-1 text-xs bg-brand-primary rounded disabled:opacity-40 hover:opacity-90"
            >
              Link Alert
            </button>
          </form>
        </div>
        {linkError && <ErrorMessage message={linkError} />}
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="border-b border-dark-border text-gray-500 uppercase tracking-wide">
              <th className="pb-2 text-left">Severity</th>
              <th className="pb-2 text-left">Alert</th>
              <th className="pb-2 text-left">Rule</th>
              <th className="pb-2 text-right">Amount USD</th>
              <th className="pb-2 text-left">Status</th>
            </tr>
          </thead>
          <tbody>
            {caseData.alerts?.map(a => (
              <tr key={a.alert_id} className="border-b border-dark-border hover:bg-dark-bg">
                <td className="py-1.5"><SeverityBadge severity={a.severity} /></td>
                <td className="py-1.5">
                  <Link to={`/alerts/${a.alert_id}`} className="text-brand-primary hover:underline">#{a.alert_id}</Link>
                </td>
                <td className="py-1.5 text-gray-400 truncate max-w-xs">{a.rule_name}</td>
                <td className="py-1.5 text-right font-mono text-gray-200">
                  {a.amount_usd != null ? `$${Number(a.amount_usd).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '—'}
                </td>
                <td className="py-1.5"><StatusBadge status={a.status} /></td>
              </tr>
            ))}
            {!caseData.alerts?.length && (
              <tr><td colSpan={5} className="py-4 text-center text-gray-500">No alerts linked to this case.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
""", encoding="utf-8")

# ── InvestigationGraphPage.jsx ────────────────────────────────────────────────
(PAGES / "InvestigationGraphPage.jsx").write_text(r"""import { useState, useEffect, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getCustomer, getCustomerTransactions } from '../api/client';
import LoadingSpinner from '../components/shared/LoadingSpinner';

const FATF_BAD = new Set(['blacklist', 'greylist']);

function buildGraph(customer, txData) {
  const nodes = new Map();
  const edges = new Map();

  const custId = `customer-${customer.customer_id}`;
  nodes.set(custId, {
    id: custId,
    label: customer.full_name,
    type: 'customer',
    hasSanctions: customer.sanctions_matches?.length > 0,
    hasPep: customer.pep_matches?.length > 0,
  });

  for (const acc of customer.accounts || []) {
    const accId = `account-${acc.account_id}`;
    nodes.set(accId, { id: accId, label: acc.account_number, type: 'account', status: acc.status });
    const edgeKey = `${custId}__${accId}`;
    edges.set(edgeKey, { from: custId, to: accId, amount: 0, label: '' });
  }

  for (const tx of txData?.items || []) {
    const fromId = `account-${tx.account_id || 'unknown'}`;
    const isBadCountry = tx.destination_fatf_status && FATF_BAD.has(tx.destination_fatf_status);

    if (tx.counterparty_account_id) {
      const cpId = `counterparty-${tx.counterparty_account_id}`;
      if (!nodes.has(cpId)) {
        nodes.set(cpId, { id: cpId, label: tx.counterparty_account_number || `Acc #${tx.counterparty_account_id}`, type: 'counterparty' });
      }
      const eKey = `${fromId}__${cpId}`;
      const existing = edges.get(eKey) || { from: fromId, to: cpId, amount: 0, isBad: false };
      existing.amount += (tx.amount_usd || 0);
      existing.isBad = existing.isBad || isBadCountry;
      edges.set(eKey, existing);
    }
  }

  return { nodes: Array.from(nodes.values()), edges: Array.from(edges.values()) };
}

function layoutNodes(nodes) {
  const positions = {};
  const center = { x: 400, y: 300 };
  const customerNode = nodes.find(n => n.type === 'customer');
  const rest = nodes.filter(n => n.type !== 'customer');

  if (customerNode) positions[customerNode.id] = center;

  rest.forEach((n, i) => {
    const angle = (2 * Math.PI * i) / rest.length;
    const r = Math.min(200, 80 + rest.length * 20);
    positions[n.id] = { x: center.x + r * Math.cos(angle), y: center.y + r * Math.sin(angle) };
  });

  return positions;
}

export default function InvestigationGraphPage() {
  const { id } = useParams();
  const [customer, setCustomer] = useState(null);
  const [txData, setTxData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    Promise.all([
      getCustomer(id),
      getCustomerTransactions(id, { limit: 200 }),
    ]).then(([c, t]) => { setCustomer(c); setTxData(t); }).finally(() => setLoading(false));
  }, [id]);

  if (loading) return <div className="p-4"><LoadingSpinner /></div>;
  if (!customer) return null;

  const { nodes, edges } = buildGraph(customer, txData);
  const positions = layoutNodes(nodes);

  const nodeColor = (n) => {
    if (n.hasSanctions) return '#ef4444';
    if (n.hasPep) return '#f59e0b';
    if (n.type === 'customer') return '#3b82f6';
    if (n.type === 'account') return (n.status === 'active' ? '#22c55e' : '#6b7280');
    return '#64748b';
  };

  return (
    <div className="p-4">
      <div className="text-xs text-gray-500 mb-3">
        <Link to="/alerts" className="hover:text-brand-primary">Alerts</Link>
        <span className="mx-1">/</span>
        <Link to={`/customers/${id}`} className="hover:text-brand-primary">{customer.full_name}</Link>
        <span className="mx-1">/</span>
        <span className="text-gray-300">Transaction Graph</span>
      </div>

      <div className="flex gap-4">
        <div className="flex-1 bg-dark-panel border border-dark-border rounded overflow-hidden">
          <svg viewBox="0 0 800 600" className="w-full h-[600px]">
            {edges.map((e, i) => {
              const from = positions[e.from];
              const to = positions[e.to];
              if (!from || !to) return null;
              const mx = (from.x + to.x) / 2;
              const my = (from.y + to.y) / 2;
              return (
                <g key={i}>
                  <line
                    x1={from.x} y1={from.y} x2={to.x} y2={to.y}
                    stroke={e.isBad ? '#ef4444' : '#374151'}
                    strokeWidth={e.isBad ? 2 : 1}
                    strokeDasharray={e.isBad ? '4 2' : undefined}
                  />
                  {e.amount > 0 && (
                    <text x={mx} y={my} textAnchor="middle" fontSize={9} fill="#9ca3af" dy={-4}>
                      ${Math.round(e.amount).toLocaleString()}
                    </text>
                  )}
                </g>
              );
            })}
            {nodes.map(n => {
              const pos = positions[n.id];
              if (!pos) return null;
              const r = n.type === 'customer' ? 24 : n.type === 'account' ? 16 : 12;
              return (
                <g key={n.id} onClick={() => setSelected(selected?.id === n.id ? null : n)} style={{ cursor: 'pointer' }}>
                  <circle cx={pos.x} cy={pos.y} r={r} fill={nodeColor(n)} opacity={0.85}
                    stroke={selected?.id === n.id ? '#fff' : 'none'} strokeWidth={2} />
                  <text x={pos.x} y={pos.y + r + 12} textAnchor="middle" fontSize={9} fill="#d1d5db">
                    {n.label?.substring(0, 16)}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>

        {selected && (
          <div className="w-64 bg-dark-panel border border-dark-border rounded p-3 text-xs">
            <div className="font-semibold text-gray-200 mb-2 uppercase tracking-wide">{selected.type}</div>
            <div className="text-gray-400 mb-1 font-mono break-all">{selected.label}</div>
            {selected.status && <div className="text-gray-500">Status: {selected.status}</div>}
            {selected.hasSanctions && <div className="text-red-400 mt-1 font-semibold">SANCTIONS HIT</div>}
            {selected.hasPep && <div className="text-amber-400 mt-1 font-semibold">PEP HIT</div>}
          </div>
        )}
      </div>

      <div className="mt-3 flex gap-4 text-xs text-gray-500">
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full bg-blue-500 inline-block" /> Customer</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full bg-green-500 inline-block" /> Account (active)</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full bg-slate-500 inline-block" /> Counterparty</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full bg-red-500 inline-block" /> Sanctions hit</span>
        <span className="flex items-center gap-1"><span className="border-b-2 border-dashed border-red-500 w-6 inline-block" /> FATF risk country</span>
      </div>
    </div>
  );
}
""", encoding="utf-8")

print("All frontend pages written successfully.")
