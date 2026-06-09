import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Sparkles, MessageSquare, FileText, Receipt, History, FolderKanban, ChevronRight } from 'lucide-react';
import { getAlert, postAlertComment, postTriageRun, getAgentRun, postLiveMcpWorkflow } from '../api/client';
import PageHeader from '../components/ui/PageHeader';
import Card from '../components/ui/Card';
import Button from '../components/ui/Button';
import Badge from '../components/ui/Badge';
import { LoadingBlock } from '../components/ui/Spinner';
import ErrorMessage from '../components/shared/ErrorMessage';
import SeverityBadge from '../components/shared/SeverityBadge';
import StatusBadge from '../components/shared/StatusBadge';
import OfficerAvatar from '../components/shared/OfficerAvatar';
import SanctionsPepFlag from '../components/shared/SanctionsPepFlag';
import AgentReviewPanel from '../components/AgentReviewPanel';
import AgentTraceDrawer from '../components/AgentTraceDrawer';
import DispositionControls from '../components/DispositionControls';

function Field({ label, value }) {
  return (
    <div className="flex gap-3 text-sm py-1">
      <span className="text-ink-subtle w-32 shrink-0">{label}</span>
      <span className="text-ink break-words">{value ?? '—'}</span>
    </div>
  );
}

function FatfBadge({ status }) {
  if (!status || status === 'none') return null;
  return <Badge tone={status === 'blacklist' ? 'red' : 'amber'}>{status}</Badge>;
}

function money(v) {
  return v != null ? `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—';
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
  const [liveWorkflow, setLiveWorkflow] = useState(null);
  const [triageError, setTriageError] = useState(null);
  const [traceOpen, setTraceOpen] = useState(false);

  function loadAlert() {
    setLoading(true);
    getAlert(id)
      .then(d => {
        setAlert(d);
        if (d.latest_run_id && !agentRun) getAgentRun(d.latest_run_id).then(setAgentRun).catch(() => {});
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

  async function handleLiveWorkflow(workflow) {
    setLiveWorkflow(workflow);
    setTriageError(null);
    try {
      const result = await postLiveMcpWorkflow({ workflow, alert_id: Number(id) });
      const run = await getAgentRun(result.run_id);
      setAgentRun(run);
    } catch (e) {
      setTriageError(e.response?.data?.detail || e.message);
    } finally {
      setLiveWorkflow(null);
    }
  }

  if (loading) return <LoadingBlock label="Loading alert…" />;
  if (error) return <ErrorMessage message={error} />;
  if (!alert) return null;

  const workflowLaunchers = [
    {
      key: 'deterministic',
      label: 'Deterministic',
      detail: 'Policy triage',
      loading: triaging,
      onClick: handleTriage,
    },
    {
      key: 'triage',
      label: 'Live Triage',
      detail: 'MCP triage',
      loading: liveWorkflow === 'triage',
      onClick: () => handleLiveWorkflow('triage'),
    },
    {
      key: 'investigation',
      label: 'Investigate',
      detail: 'Evidence review',
      loading: liveWorkflow === 'investigation',
      onClick: () => handleLiveWorkflow('investigation'),
    },
  ];

  return (
    <div>
      <PageHeader
        title={`Alert #${alert.alert_id}`}
        breadcrumb={<Link to="/alerts" className="hover:text-brand">Alerts</Link>}
        subtitle={alert.rule_name}
        actions={<div className="flex items-center gap-2"><SeverityBadge severity={alert.severity} /><StatusBadge status={alert.status} /></div>}
      />

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* Left: case file */}
        <div className="xl:col-span-2 space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card title="Triggering Transaction" icon={Receipt}>
              <Field label="Amount" value={alert.amount != null ? `${alert.amount} ${alert.currency_code}` : '—'} />
              <Field label="Amount (USD)" value={money(alert.amount_usd)} />
              <Field label="Type" value={alert.transaction_type} />
              <div className="flex gap-3 text-sm py-1">
                <span className="text-ink-subtle w-32 shrink-0">Destination</span>
                <span className="text-ink flex items-center gap-2">
                  {alert.destination_country_name || alert.destination_country || '—'}
                  <FatfBadge status={alert.destination_fatf_status} />
                </span>
              </div>
              <Field label="Date" value={alert.transaction_date ? new Date(alert.transaction_date).toLocaleString() : '—'} />
              <Field label="Reference" value={alert.reference_number} />
            </Card>

            <Card title="Customer" icon={FileText} actions={<Link to={`/customers/${alert.customer_id}`} className="text-xs font-medium text-brand hover:underline inline-flex items-center">Profile <ChevronRight className="w-3.5 h-3.5" /></Link>}>
              <div className="flex items-center gap-2 mb-2">
                <Link to={`/customers/${alert.customer_id}`} className="text-base font-semibold text-ink hover:text-brand">{alert.customer_name}</Link>
                <SanctionsPepFlag hasSanctions={alert.has_sanctions_hit} hasPep={alert.has_pep_hit} />
              </div>
              <Field label="Risk Level" value={alert.risk_level} />
              <Field label="KYC Status" value={alert.kyc_status} />
              <Field label="Nationality" value={alert.nationality_name || alert.nationality} />
              <Field label="Assigned To" value={alert.officer_name} />
            </Card>
          </div>

          {alert.recent_transactions?.length > 0 && (
            <Card title="Recent Transactions" icon={Receipt} bodyClassName="p-0">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-ink-subtle uppercase tracking-wide bg-surface-2/60">
                    <th className="font-medium px-4 py-2">Date</th>
                    <th className="font-medium px-4 py-2">Type</th>
                    <th className="font-medium px-4 py-2 text-right">Amount</th>
                    <th className="font-medium px-4 py-2">Country</th>
                    <th className="font-medium px-4 py-2 text-center">Flag</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {alert.recent_transactions.slice(0, 10).map(t => (
                    <tr key={t.transaction_id} className="hover:bg-surface-2">
                      <td className="px-4 py-2 text-ink-subtle text-xs">{new Date(t.created_at).toLocaleDateString()}</td>
                      <td className="px-4 py-2 text-ink-muted">{t.transaction_type}</td>
                      <td className="px-4 py-2 text-right tnum text-ink">{money(t.amount_usd)}</td>
                      <td className="px-4 py-2 text-ink-muted">{t.destination_country || '—'}</td>
                      <td className="px-4 py-2 text-center">{t.is_flagged ? <span className="text-red-500 font-bold">!</span> : ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {alert.prior_alerts?.length > 0 && (
              <Card title="Prior Alerts" icon={History}>
                <div className="space-y-2">
                  {alert.prior_alerts.slice(0, 5).map(a => (
                    <div key={a.alert_id} className="flex items-center gap-2 text-sm">
                      <SeverityBadge severity={a.severity} />
                      <Link to={`/alerts/${a.alert_id}`} className="text-brand hover:underline font-mono text-xs">#{a.alert_id}</Link>
                      <span className="text-ink-muted truncate flex-1">{a.rule_name}</span>
                      <StatusBadge status={a.status} />
                    </div>
                  ))}
                </div>
              </Card>
            )}
            {alert.prior_cases?.length > 0 && (
              <Card title="Prior Cases" icon={FolderKanban}>
                <div className="space-y-2">
                  {alert.prior_cases.slice(0, 5).map(c => (
                    <div key={c.case_id} className="flex items-center gap-2 text-sm">
                      <Link to={`/cases/${c.case_id}`} className="text-brand hover:underline font-mono text-xs">#{c.case_id}</Link>
                      <span className="text-ink-muted flex-1">{c.case_type}</span>
                      <StatusBadge status={c.status} />
                    </div>
                  ))}
                </div>
              </Card>
            )}
          </div>

          <Card title="Comments" icon={MessageSquare}>
            {alert.comments?.length === 0 && <p className="text-sm text-ink-subtle mb-3">No comments yet.</p>}
            <div className="space-y-4 mb-4">
              {alert.comments?.map(c => (
                <div key={c.comment_id} className="flex gap-2.5">
                  <OfficerAvatar name={c.officer_name} officerId={c.officer_id} />
                  <div>
                    <div className="flex items-baseline gap-2">
                      <span className="text-sm font-medium text-ink">{c.officer_name}</span>
                      <span className="text-xs text-ink-subtle">{new Date(c.created_at).toLocaleString()}</span>
                    </div>
                    <p className="text-sm text-ink-muted mt-0.5">{c.comment}</p>
                  </div>
                </div>
              ))}
            </div>
            <form onSubmit={handleComment} className="flex gap-2">
              <input
                value={comment}
                onChange={e => setComment(e.target.value)}
                placeholder="Add a comment…"
                className="flex-1 bg-surface border border-border rounded-lg px-3 py-2 text-sm text-ink placeholder:text-ink-subtle focus:outline-none focus:ring-2 focus:ring-brand/30"
              />
              <Button type="submit" disabled={!comment.trim()} loading={commenting}>Post</Button>
            </form>
          </Card>
        </div>

        {/* Right: agent + disposition */}
        <div className="space-y-6">
          <Card title="Agent Review" icon={Sparkles}>
            <div className="mb-4">
              <div className="text-xs font-semibold text-ink-subtle uppercase tracking-wide mb-2">Workflow launcher</div>
              <div className="grid grid-cols-3 overflow-hidden rounded-lg border border-border bg-surface">
                {workflowLaunchers.map(item => {
                  const running = Boolean(item.loading);
                  return (
                    <button
                      key={item.key}
                      type="button"
                      onClick={item.onClick}
                      disabled={triaging || Boolean(liveWorkflow)}
                      className={`min-w-0 border-r border-border px-2.5 py-2 text-left last:border-r-0 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 ${
                        running ? 'bg-brand-soft text-brand' : 'text-ink hover:bg-surface-2 disabled:text-ink-subtle'
                      }`}
                    >
                      <div className="flex items-center gap-1.5">
                        {running ? (
                          <span className="w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin" />
                        ) : (
                          <Sparkles className="w-3.5 h-3.5 shrink-0" />
                        )}
                        <span className="text-xs font-semibold truncate">{item.label}</span>
                      </div>
                      <div className="text-[11px] text-ink-subtle truncate mt-0.5">{item.detail}</div>
                    </button>
                  );
                })}
              </div>
            </div>
            {triageError && <div className="mb-3"><ErrorMessage message={triageError} /></div>}
            {agentRun ? (
              <AgentReviewPanel runId={agentRun?.run?.run_id} onViewTrace={() => setTraceOpen(true)} />
            ) : (
              <p className="text-sm text-ink-subtle">No agent run yet. Run deterministic triage, live triage, or live investigation. The agent produces an advisory proposal only.</p>
            )}
          </Card>

          <Card title="Disposition">
            <DispositionControls alertId={id} onSuccess={loadAlert} />
          </Card>
        </div>
      </div>

      <AgentTraceDrawer runId={agentRun?.run?.run_id} isOpen={traceOpen} onClose={() => setTraceOpen(false)} />
    </div>
  );
}
