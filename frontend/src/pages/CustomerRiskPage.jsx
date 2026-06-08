import { useState, useEffect } from 'react';
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
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    getCustomer(id)
      .then(setCustomer)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    if (tab !== 'Transactions') return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setTxLoading(true);
    const params = { page: txPage, limit: 50 };
    if (isFlagged !== null) params.is_flagged = isFlagged;
    getCustomerTransactions(id, params)
      .then(setTxData)
      .finally(() => setTxLoading(false));
  }, [id, tab, txPage, isFlagged]);

  useEffect(() => {
    if (tab !== 'Cases') return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
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
