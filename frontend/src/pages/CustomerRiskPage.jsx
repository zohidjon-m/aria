import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Network, ShieldCheck, ShieldAlert, Wallet, Gauge, Sparkles } from 'lucide-react';
import { getCustomer, getCustomerTransactions, getCustomerCases, getAgentRun, postLiveMcpWorkflow } from '../api/client';
import PageHeader from '../components/ui/PageHeader';
import Card from '../components/ui/Card';
import Button from '../components/ui/Button';
import Badge from '../components/ui/Badge';
import { LoadingBlock } from '../components/ui/Spinner';
import EmptyState from '../components/ui/EmptyState';
import ErrorMessage from '../components/shared/ErrorMessage';
import StatusBadge from '../components/shared/StatusBadge';
import AgentReviewPanel from '../components/AgentReviewPanel';
import AgentTraceDrawer from '../components/AgentTraceDrawer';

const TABS = ['Overview', 'Transactions', 'Cases'];
const RISK_TONE = { critical: 'red', high: 'amber', medium: 'violet', low: 'emerald' };

function Field({ label, value }) {
  return (
    <div className="flex gap-3 text-sm py-1">
      <span className="text-ink-subtle w-36 shrink-0">{label}</span>
      <span className="text-ink break-words">{value ?? '—'}</span>
    </div>
  );
}
function money(v) {
  return v != null ? `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—';
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
  const [riskRun, setRiskRun] = useState(null);
  const [riskRunning, setRiskRunning] = useState(false);
  const [riskError, setRiskError] = useState(null);
  const [traceOpen, setTraceOpen] = useState(false);

  useEffect(() => {
    setLoading(true);
    getCustomer(id).then(setCustomer).catch(e => setError(e.message)).finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    if (tab !== 'Transactions') return;
    setTxLoading(true);
    const params = { page: txPage, limit: 50 };
    if (isFlagged !== null) params.is_flagged = isFlagged;
    getCustomerTransactions(id, params).then(setTxData).finally(() => setTxLoading(false));
  }, [id, tab, txPage, isFlagged]);

  useEffect(() => {
    if (tab !== 'Cases') return;
    setCasesLoading(true);
    getCustomerCases(id).then(setCases).finally(() => setCasesLoading(false));
  }, [id, tab]);

  if (loading) return <LoadingBlock label="Loading customer…" />;
  if (error) return <ErrorMessage message={error} />;
  if (!customer) return null;

  const hasSanctions = customer.sanctions_matches?.length > 0;
  const hasPep = customer.pep_matches?.length > 0;

  async function handleRiskScore() {
    setRiskRunning(true);
    setRiskError(null);
    try {
      const result = await postLiveMcpWorkflow({ workflow: 'risk_scoring', customer_id: Number(id) });
      const run = await getAgentRun(result.run_id);
      setRiskRun(run);
    } catch (e) {
      setRiskError(e.response?.data?.detail || e.message);
    } finally {
      setRiskRunning(false);
    }
  }

  return (
    <div>
      <PageHeader
        title={customer.full_name}
        breadcrumb={<><Link to="/alerts" className="hover:text-brand">Alerts</Link> <span className="mx-1">/</span> Customer</>}
        subtitle={`Customer #${customer.customer_id}`}
        actions={
          <div className="flex items-center gap-2">
            <Badge tone={RISK_TONE[customer.risk_level] || 'slate'} dot>{customer.risk_level} risk</Badge>
            <Link to={`/customers/${id}/graph`}><Button variant="secondary" size="sm" icon={Network}>Graph</Button></Link>
          </div>
        }
      />

      <div className="flex gap-1 mb-5 border-b border-border">
        {TABS.map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === t ? 'border-brand text-brand' : 'border-transparent text-ink-subtle hover:text-ink'
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === 'Overview' && (
        <Card
          title="Agent Risk Review"
          subtitle="Live risk scoring output and officer decision trail"
          icon={Sparkles}
          className="mb-6"
          actions={<Button size="sm" icon={Sparkles} onClick={handleRiskScore} loading={riskRunning}>Run Risk Score</Button>}
        >
          {riskError && <div className="mb-3"><ErrorMessage message={riskError} /></div>}
          {riskRun ? (
            <AgentReviewPanel runId={riskRun?.run?.run_id} onViewTrace={() => setTraceOpen(true)} />
          ) : (
            <p className="text-sm text-ink-subtle">No live risk scoring run yet. The final numeric score is computed by deterministic policy.</p>
          )}
        </Card>
      )}

      {tab === 'Overview' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="space-y-6">
            <Card title="KYC Profile" icon={ShieldCheck}>
              <Field label="Customer ID" value={customer.customer_id} />
              <Field label="Date of Birth" value={customer.date_of_birth} />
              <Field label="Nationality" value={`${customer.nationality_name || ''} (${customer.nationality || '—'})`} />
              <Field label="KYC Status" value={customer.kyc_status} />
              <Field label="Verified At" value={customer.kyc_verified_at ? new Date(customer.kyc_verified_at).toLocaleDateString() : null} />
              <Field label="Customer Since" value={customer.customer_since ? new Date(customer.customer_since).toLocaleDateString() : null} />
              <Field label="Branch" value={customer.branch_name} />
              <Field label="Email" value={customer.email} />
              <Field label="Phone" value={customer.phone} />
            </Card>

            <Card title="Sanctions / PEP Screening" icon={hasSanctions || hasPep ? ShieldAlert : ShieldCheck}>
              {!hasSanctions && !hasPep ? (
                <div className="flex items-center gap-2 text-sm text-emerald-700"><ShieldCheck className="w-4 h-4" /> No active sanctions or PEP matches.</div>
              ) : (
                <div className="space-y-3">
                  {hasSanctions && (
                    <div>
                      <p className="text-xs font-semibold text-red-700 uppercase tracking-wide mb-1">Sanctions Hits</p>
                      {customer.sanctions_matches.map((m, i) => (
                        <div key={i} className="text-sm text-ink-muted py-0.5">{m.matched_name} — {m.entity_type} — {m.sanction_type} ({m.listed_by})</div>
                      ))}
                    </div>
                  )}
                  {hasPep && (
                    <div>
                      <p className="text-xs font-semibold text-amber-700 uppercase tracking-wide mb-1">PEP Hits</p>
                      {customer.pep_matches.map((m, i) => (
                        <div key={i} className="text-sm text-ink-muted py-0.5">{m.matched_name} — {m.position} — {m.pep_level} ({m.country_code})</div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </Card>
          </div>

          <div className="space-y-6">
            <Card title="Accounts" icon={Wallet} bodyClassName="p-0">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-ink-subtle uppercase tracking-wide bg-surface-2/60">
                    <th className="font-medium px-4 py-2">Account</th>
                    <th className="font-medium px-4 py-2">Type</th>
                    <th className="font-medium px-4 py-2 text-right">Balance</th>
                    <th className="font-medium px-4 py-2">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {customer.accounts?.map(a => (
                    <tr key={a.account_id} className="hover:bg-surface-2">
                      <td className="px-4 py-2 font-mono text-xs text-ink-muted">{a.account_number}</td>
                      <td className="px-4 py-2 text-ink-muted">{a.account_type}</td>
                      <td className="px-4 py-2 text-right tnum text-ink">{money(a.current_balance)}</td>
                      <td className="px-4 py-2"><StatusBadge status={a.status} /></td>
                    </tr>
                  ))}
                  {!customer.accounts?.length && <tr><td colSpan={4} className="px-4 py-4 text-ink-subtle text-center">No accounts.</td></tr>}
                </tbody>
              </table>
            </Card>

            {customer.baseline && (
              <Card title="Transaction Baseline" icon={Gauge}>
                <Field label="Avg Transaction" value={money(customer.baseline.avg_transaction)} />
                <Field label="Max Transaction" value={money(customer.baseline.max_transaction)} />
                <Field label="Monthly Volume" value={money(customer.baseline.monthly_volume)} />
                <Field label="International %" value={customer.baseline.international_pct != null ? `${customer.baseline.international_pct}%` : null} />
                <Field label="Cash %" value={customer.baseline.cash_pct != null ? `${customer.baseline.cash_pct}%` : null} />
                <Field label="Typical Countries" value={customer.baseline.typical_countries?.join(', ')} />
              </Card>
            )}

            {customer.latest_risk_score && (
              <Card title="Latest Risk Score" icon={Gauge}>
                <Field label="Score" value={`${customer.latest_risk_score.score} / 100`} />
                <Field label="Level" value={<Badge tone={RISK_TONE[customer.latest_risk_score.score_level] || 'slate'} dot>{customer.latest_risk_score.score_level}</Badge>} />
                <Field label="Computed By" value={customer.latest_risk_score.computed_by} />
                {customer.latest_risk_score.reasoning && (
                  <p className="mt-2 text-sm text-ink-muted bg-surface-2 rounded-lg p-3">{customer.latest_risk_score.reasoning}</p>
                )}
              </Card>
            )}
          </div>
        </div>
      )}

      {tab === 'Transactions' && (
        <Card bodyClassName="p-0">
          <div className="flex gap-2 px-4 py-3 border-b border-border">
            {[null, true, false].map(v => (
              <button
                key={String(v)}
                onClick={() => { setIsFlagged(v); setTxPage(1); }}
                className={`px-2.5 py-1 rounded-full text-xs font-medium border transition-colors ${
                  isFlagged === v ? 'bg-brand text-white border-brand' : 'bg-surface text-ink-muted border-border hover:border-border-strong'
                }`}
              >
                {v === null ? 'All' : v ? 'Flagged' : 'Not Flagged'}
              </button>
            ))}
          </div>
          {txLoading ? <LoadingBlock /> : txData && (
            <>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-ink-subtle uppercase tracking-wide bg-surface-2/60">
                    <th className="font-medium px-4 py-2">Date</th>
                    <th className="font-medium px-4 py-2">Type</th>
                    <th className="font-medium px-4 py-2 text-right">Amount</th>
                    <th className="font-medium px-4 py-2">Country</th>
                    <th className="font-medium px-4 py-2">Account</th>
                    <th className="font-medium px-4 py-2 text-center">Flag</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {txData.items.map(t => (
                    <tr key={t.transaction_id} className="hover:bg-surface-2">
                      <td className="px-4 py-2 text-xs text-ink-subtle">{new Date(t.created_at).toLocaleDateString()}</td>
                      <td className="px-4 py-2 text-ink-muted">{t.transaction_type}</td>
                      <td className="px-4 py-2 text-right tnum text-ink">{money(t.amount_usd)}</td>
                      <td className="px-4 py-2 text-ink-muted">{t.destination_country_name || t.destination_country || '—'}</td>
                      <td className="px-4 py-2 font-mono text-xs text-ink-subtle">{t.account_number}</td>
                      <td className="px-4 py-2 text-center">{t.is_flagged ? <span className="text-red-500 font-bold">!</span> : ''}</td>
                    </tr>
                  ))}
                  {txData.items.length === 0 && <tr><td colSpan={6} className="px-4 py-6 text-center text-ink-subtle">No transactions.</td></tr>}
                </tbody>
              </table>
              <div className="flex items-center justify-between px-4 py-3 border-t border-border">
                <span className="text-xs text-ink-subtle">{txData.total} total</span>
                <div className="flex gap-2">
                  <Button variant="secondary" size="sm" disabled={txPage === 1} onClick={() => setTxPage(p => p - 1)}>Prev</Button>
                  <Button variant="secondary" size="sm" disabled={txData.items.length < 50} onClick={() => setTxPage(p => p + 1)}>Next</Button>
                </div>
              </div>
            </>
          )}
        </Card>
      )}

      {tab === 'Cases' && (
        <Card bodyClassName="p-0">
          {casesLoading ? <LoadingBlock /> : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-ink-subtle uppercase tracking-wide bg-surface-2/60">
                  <th className="font-medium px-4 py-2">Case</th>
                  <th className="font-medium px-4 py-2">Type</th>
                  <th className="font-medium px-4 py-2">Priority</th>
                  <th className="font-medium px-4 py-2">Status</th>
                  <th className="font-medium px-4 py-2">Officer</th>
                  <th className="font-medium px-4 py-2 text-right">Alerts</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {(cases || []).map(c => (
                  <tr key={c.case_id} className="hover:bg-surface-2">
                    <td className="px-4 py-2"><Link to={`/cases/${c.case_id}`} className="text-brand hover:underline font-mono text-xs">#{c.case_id}</Link></td>
                    <td className="px-4 py-2 text-ink-muted">{c.case_type}</td>
                    <td className="px-4 py-2 text-ink-muted capitalize">{c.priority}</td>
                    <td className="px-4 py-2"><StatusBadge status={c.status} /></td>
                    <td className="px-4 py-2 text-ink-muted">{c.officer_name || '—'}</td>
                    <td className="px-4 py-2 text-right text-ink-muted tnum">{c.linked_alert_count}</td>
                  </tr>
                ))}
                {!cases?.length && <tr><td colSpan={6} className="px-4 py-6 text-center text-ink-subtle">No cases.</td></tr>}
              </tbody>
            </table>
          )}
        </Card>
      )}
      <AgentTraceDrawer runId={riskRun?.run?.run_id} isOpen={traceOpen} onClose={() => setTraceOpen(false)} />
    </div>
  );
}
