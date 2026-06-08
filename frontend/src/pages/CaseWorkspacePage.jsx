import { useState, useEffect } from 'react';
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

  // eslint-disable-next-line react-hooks/exhaustive-deps
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
