import { useState, useEffect } from 'react';
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

  // eslint-disable-next-line react-hooks/exhaustive-deps
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
