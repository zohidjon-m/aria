import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { Bell, RefreshCw, SlidersHorizontal } from 'lucide-react';
import { getAlerts, getOfficers } from '../api/client';
import PageHeader from '../components/ui/PageHeader';
import Card from '../components/ui/Card';
import Button from '../components/ui/Button';
import { LoadingBlock } from '../components/ui/Spinner';
import EmptyState from '../components/ui/EmptyState';
import ErrorMessage from '../components/shared/ErrorMessage';
import SeverityBadge from '../components/shared/SeverityBadge';
import StatusBadge from '../components/shared/StatusBadge';
import OfficerAvatar from '../components/shared/OfficerAvatar';
import SanctionsPepFlag from '../components/shared/SanctionsPepFlag';
import CaseIndicator from '../components/shared/CaseIndicator';

const SEVERITIES = ['critical', 'high', 'medium', 'low'];
const STATUSES = ['open', 'under_review', 'escalated', 'dismissed', 'resolved'];
const SORT_OPTIONS = [
  { value: 'created_at', label: 'Newest' },
  { value: 'amount', label: 'Amount' },
  { value: 'severity', label: 'Severity' },
];

function ageLabel(d) {
  const diff = Date.now() - new Date(d).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

function Pill({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className={`px-2.5 py-1 rounded-full text-xs font-medium border transition-colors capitalize ${
        active ? 'bg-brand text-white border-brand' : 'bg-surface text-ink-muted border-border hover:border-border-strong'
      }`}
    >
      {children}
    </button>
  );
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

  function setFilter(key, val) { setFilters(f => ({ ...f, [key]: val })); setPage(1); }

  const start = (page - 1) * limit + 1;
  const end = Math.min(page * limit, total);

  return (
    <div>
      <PageHeader
        title="Alert Queue"
        subtitle="Triage and disposition transaction monitoring alerts."
        actions={<Button variant="secondary" size="sm" icon={RefreshCw} onClick={load}>Refresh</Button>}
      />

      <Card bodyClassName="p-0">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 border-b border-border">
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] font-semibold text-ink-subtle uppercase tracking-wider mr-1">Severity</span>
            <Pill active={filters.severity === ''} onClick={() => setFilter('severity', '')}>All</Pill>
            {SEVERITIES.map(s => <Pill key={s} active={filters.severity === s} onClick={() => setFilter('severity', s)}>{s}</Pill>)}
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] font-semibold text-ink-subtle uppercase tracking-wider mr-1">Status</span>
            <Pill active={filters.status === ''} onClick={() => setFilter('status', '')}>All</Pill>
            {STATUSES.map(s => <Pill key={s} active={filters.status === s} onClick={() => setFilter('status', s)}>{s.replace(/_/g, ' ')}</Pill>)}
          </div>
          <div className="flex items-center gap-2 ml-auto">
            <SlidersHorizontal className="w-4 h-4 text-ink-subtle" />
            <select
              value={filters.assigned_to}
              onChange={e => setFilter('assigned_to', e.target.value)}
              className="bg-surface border border-border rounded-lg px-2.5 py-1.5 text-xs text-ink focus:outline-none focus:ring-2 focus:ring-brand/30"
            >
              <option value="">Any officer</option>
              {officers.map(o => <option key={o.officer_id} value={o.officer_id}>{o.full_name}</option>)}
            </select>
            <select
              value={filters.sort_by}
              onChange={e => setFilter('sort_by', e.target.value)}
              className="bg-surface border border-border rounded-lg px-2.5 py-1.5 text-xs text-ink focus:outline-none focus:ring-2 focus:ring-brand/30"
            >
              {SORT_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
        </div>

        {error && <div className="p-4"><ErrorMessage message={error} onRetry={load} /></div>}

        {loading ? (
          <LoadingBlock />
        ) : alerts.length === 0 ? (
          <div className="p-4"><EmptyState icon={Bell} title="No alerts" message="No alerts match the current filters." /></div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-ink-subtle uppercase tracking-wide bg-surface-2/60">
                  <th className="font-medium px-4 py-2.5">Severity</th>
                  <th className="font-medium px-4 py-2.5">ID</th>
                  <th className="font-medium px-4 py-2.5">Rule</th>
                  <th className="font-medium px-4 py-2.5">Customer</th>
                  <th className="font-medium px-4 py-2.5 text-right">Amount</th>
                  <th className="font-medium px-4 py-2.5">Status</th>
                  <th className="font-medium px-4 py-2.5">Flags</th>
                  <th className="font-medium px-4 py-2.5">Officer</th>
                  <th className="font-medium px-4 py-2.5 text-right">Age</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {alerts.map(a => (
                  <tr key={a.alert_id} className="hover:bg-surface-2 transition-colors">
                    <td className="px-4 py-3"><SeverityBadge severity={a.severity} /></td>
                    <td className="px-4 py-3">
                      <Link to={`/alerts/${a.alert_id}`} className="font-mono text-xs font-medium text-brand hover:underline">#{a.alert_id}</Link>
                    </td>
                    <td className="px-4 py-3 text-ink max-w-xs truncate">{a.rule_name}</td>
                    <td className="px-4 py-3">
                      <Link to={`/customers/${a.customer_id}`} className="text-ink-muted hover:text-brand hover:underline">{a.customer_name}</Link>
                    </td>
                    <td className="px-4 py-3 text-right font-semibold text-ink tnum">
                      {a.amount_usd != null ? `$${Number(a.amount_usd).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—'}
                    </td>
                    <td className="px-4 py-3"><StatusBadge status={a.status} /></td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        <SanctionsPepFlag hasSanctions={a.has_sanctions_hit} hasPep={a.has_pep_hit} />
                        <CaseIndicator hasCase={a.has_case} caseId={a.case_id} />
                      </div>
                    </td>
                    <td className="px-4 py-3">{a.officer_name && <OfficerAvatar name={a.officer_name} officerId={a.assigned_to} />}</td>
                    <td className="px-4 py-3 text-right text-xs text-ink-subtle">{ageLabel(a.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="flex items-center justify-between px-4 py-3 border-t border-border">
          <span className="text-xs text-ink-subtle">{total > 0 ? `${start}–${end} of ${total}` : '0 results'}</span>
          <div className="flex gap-2">
            <Button variant="secondary" size="sm" disabled={page === 1} onClick={() => setPage(p => p - 1)}>Prev</Button>
            <Button variant="secondary" size="sm" disabled={end >= total} onClick={() => setPage(p => p + 1)}>Next</Button>
          </div>
        </div>
      </Card>
    </div>
  );
}
