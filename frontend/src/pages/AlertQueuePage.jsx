import { useState, useEffect, useCallback } from 'react';
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

  // eslint-disable-next-line react-hooks/set-state-in-effect
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
