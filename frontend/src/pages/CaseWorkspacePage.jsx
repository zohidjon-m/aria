import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { FolderKanban, Link2, FileText, Sparkles } from 'lucide-react';
import { getCase, getAgentRun, linkAlertToCase, postLiveMcpWorkflow } from '../api/client';
import PageHeader from '../components/ui/PageHeader';
import Card from '../components/ui/Card';
import Button from '../components/ui/Button';
import Badge from '../components/ui/Badge';
import { LoadingBlock } from '../components/ui/Spinner';
import EmptyState from '../components/ui/EmptyState';
import ErrorMessage from '../components/shared/ErrorMessage';
import StatusBadge from '../components/shared/StatusBadge';
import SeverityBadge from '../components/shared/SeverityBadge';
import OfficerAvatar from '../components/shared/OfficerAvatar';
import AgentReviewPanel from '../components/AgentReviewPanel';
import AgentTraceDrawer from '../components/AgentTraceDrawer';

const PRIORITY_TONE = { critical: 'red', high: 'amber', medium: 'violet', low: 'emerald' };

function Field({ label, value }) {
  return (
    <div className="flex gap-3 text-sm py-1">
      <span className="text-ink-subtle w-32 shrink-0">{label}</span>
      <span className="text-ink break-words">{value ?? '—'}</span>
    </div>
  );
}
function money(v) {
  return v != null ? `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—';
}

export default function CaseWorkspacePage() {
  const { id } = useParams();
  const [caseData, setCaseData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [linkAlertId, setLinkAlertId] = useState('');
  const [linking, setLinking] = useState(false);
  const [linkError, setLinkError] = useState(null);
  const [officerContext, setOfficerContext] = useState('');
  const [sarRun, setSarRun] = useState(null);
  const [sarRunning, setSarRunning] = useState(false);
  const [sarError, setSarError] = useState(null);
  const [traceOpen, setTraceOpen] = useState(false);

  function loadCase() {
    setLoading(true);
    getCase(id).then(setCaseData).catch(e => setError(e.message)).finally(() => setLoading(false));
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

  async function handleSarDraft() {
    setSarRunning(true);
    setSarError(null);
    try {
      const result = await postLiveMcpWorkflow({
        workflow: 'sar_drafting',
        case_id: Number(id),
        officer_context: officerContext,
      });
      const run = await getAgentRun(result.run_id);
      setSarRun(run);
    } catch (e) {
      setSarError(e.response?.data?.detail || e.message);
    } finally {
      setSarRunning(false);
    }
  }

  if (loading) return <LoadingBlock label="Loading case…" />;
  if (error) return <ErrorMessage message={error} />;
  if (!caseData) return null;

  return (
    <div>
      <PageHeader
        title={`Case #${caseData.case_id}`}
        breadcrumb={<><Link to="/alerts" className="hover:text-brand">Alerts</Link> <span className="mx-1">/</span> Case</>}
        subtitle={caseData.case_type}
        actions={
          <div className="flex items-center gap-2">
            <Badge tone={PRIORITY_TONE[caseData.priority] || 'slate'} dot>{caseData.priority}</Badge>
            <StatusBadge status={caseData.status} />
          </div>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <Card title="Case Details" icon={FolderKanban}>
          <Field label="Case Type" value={caseData.case_type} />
          <Field label="Customer" value={caseData.customer_id ? <Link to={`/customers/${caseData.customer_id}`} className="text-brand hover:underline">{caseData.customer_name || `#${caseData.customer_id}`}</Link> : null} />
          <Field label="Opened" value={caseData.opened_at ? new Date(caseData.opened_at).toLocaleString() : null} />
          <Field label="Closed" value={caseData.closed_at ? new Date(caseData.closed_at).toLocaleString() : null} />
          <div className="flex gap-3 text-sm py-1">
            <span className="text-ink-subtle w-32 shrink-0">Officer</span>
            <span className="flex items-center gap-2 text-ink">
              {caseData.officer_name && <OfficerAvatar name={caseData.officer_name} officerId={caseData.officer_id} />}
              {caseData.officer_name || '—'}
            </span>
          </div>
        </Card>

        <Card title="Summary" icon={FileText}>
          <p className="text-sm text-ink-muted leading-relaxed">{caseData.summary || <span className="text-ink-subtle italic">No summary provided.</span>}</p>
          {caseData.resolution && (
            <div className="mt-4">
              <p className="text-xs font-semibold text-ink-subtle uppercase tracking-wide mb-1">Resolution</p>
              <p className="text-sm text-ink-muted leading-relaxed">{caseData.resolution}</p>
            </div>
          )}
        </Card>
      </div>

      <Card
        title="SAR Draft Review"
        subtitle="Officer context and draft review"
        icon={Sparkles}
        className="mb-6"
      >
        {sarError && <div className="mb-3"><ErrorMessage message={sarError} /></div>}
        <div className="grid grid-cols-1 xl:grid-cols-[minmax(16rem,22rem)_1fr] gap-4">
          <div className="border border-border rounded-lg p-3">
            <div className="text-xs font-semibold text-ink-subtle uppercase tracking-wide mb-2">Officer context</div>
            <textarea
              value={officerContext}
              onChange={e => setOfficerContext(e.target.value)}
              placeholder="Add case-specific context"
              rows={5}
              className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-sm text-ink placeholder:text-ink-subtle focus:outline-none focus:ring-2 focus:ring-brand/30"
            />
            <Button className="mt-3 w-full" icon={Sparkles} onClick={handleSarDraft} loading={sarRunning}>Draft SAR</Button>
          </div>
          <div className="min-w-0">
            {sarRun ? (
              <AgentReviewPanel runId={sarRun?.run?.run_id} onViewTrace={() => setTraceOpen(true)} />
            ) : (
              <p className="text-sm text-ink-subtle">No SAR draft run yet. Drafts are evidence-grounded and require authorized human review.</p>
            )}
          </div>
        </div>
      </Card>

      <Card
        title="Linked Alerts"
        icon={Link2}
        bodyClassName="p-0"
        actions={
          <form onSubmit={handleLinkAlert} className="flex gap-2">
            <input
              value={linkAlertId}
              onChange={e => setLinkAlertId(e.target.value)}
              placeholder="Alert ID"
              type="number"
              className="w-24 bg-surface border border-border rounded-lg px-2.5 py-1.5 text-xs text-ink focus:outline-none focus:ring-2 focus:ring-brand/30"
            />
            <Button type="submit" size="sm" disabled={!linkAlertId.trim()} loading={linking}>Link</Button>
          </form>
        }
      >
        {linkError && <div className="p-4"><ErrorMessage message={linkError} /></div>}
        {caseData.alerts?.length ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-ink-subtle uppercase tracking-wide bg-surface-2/60">
                <th className="font-medium px-4 py-2">Severity</th>
                <th className="font-medium px-4 py-2">Alert</th>
                <th className="font-medium px-4 py-2">Rule</th>
                <th className="font-medium px-4 py-2 text-right">Amount</th>
                <th className="font-medium px-4 py-2">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {caseData.alerts.map(a => (
                <tr key={a.alert_id} className="hover:bg-surface-2">
                  <td className="px-4 py-2.5"><SeverityBadge severity={a.severity} /></td>
                  <td className="px-4 py-2.5"><Link to={`/alerts/${a.alert_id}`} className="text-brand hover:underline font-mono text-xs">#{a.alert_id}</Link></td>
                  <td className="px-4 py-2.5 text-ink-muted max-w-xs truncate">{a.rule_name}</td>
                  <td className="px-4 py-2.5 text-right tnum text-ink">{money(a.amount_usd)}</td>
                  <td className="px-4 py-2.5"><StatusBadge status={a.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="p-4"><EmptyState icon={Link2} title="No linked alerts" message="Link an alert to this case using the field above." /></div>
        )}
      </Card>
      <AgentTraceDrawer runId={sarRun?.run?.run_id} isOpen={traceOpen} onClose={() => setTraceOpen(false)} />
    </div>
  );
}
