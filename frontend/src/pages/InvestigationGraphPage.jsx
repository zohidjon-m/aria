import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Network } from 'lucide-react';
import { getCustomer, getCustomerTransactions } from '../api/client';
import PageHeader from '../components/ui/PageHeader';
import Card from '../components/ui/Card';
import { LoadingBlock } from '../components/ui/Spinner';

const FATF_BAD = new Set(['blacklist', 'greylist']);

function buildGraph(customer, txData) {
  const nodes = new Map();
  const edges = new Map();
  const custId = `customer-${customer.customer_id}`;
  nodes.set(custId, {
    id: custId, label: customer.full_name, type: 'customer',
    hasSanctions: customer.sanctions_matches?.length > 0,
    hasPep: customer.pep_matches?.length > 0,
  });
  for (const acc of customer.accounts || []) {
    const accId = `account-${acc.account_id}`;
    nodes.set(accId, { id: accId, label: acc.account_number, type: 'account', status: acc.status });
    edges.set(`${custId}__${accId}`, { from: custId, to: accId, amount: 0 });
  }
  for (const tx of txData?.items || []) {
    const fromId = `account-${tx.account_id || 'unknown'}`;
    const isBad = tx.destination_fatf_status && FATF_BAD.has(tx.destination_fatf_status);
    if (tx.counterparty_account_id) {
      const cpId = `counterparty-${tx.counterparty_account_id}`;
      if (!nodes.has(cpId)) nodes.set(cpId, { id: cpId, label: tx.counterparty_account_number || `Acc #${tx.counterparty_account_id}`, type: 'counterparty' });
      const eKey = `${fromId}__${cpId}`;
      const ex = edges.get(eKey) || { from: fromId, to: cpId, amount: 0, isBad: false };
      ex.amount += (tx.amount_usd || 0);
      ex.isBad = ex.isBad || isBad;
      edges.set(eKey, ex);
    }
  }
  return { nodes: Array.from(nodes.values()), edges: Array.from(edges.values()) };
}

function layout(nodes) {
  const pos = {};
  const center = { x: 400, y: 300 };
  const cust = nodes.find(n => n.type === 'customer');
  const rest = nodes.filter(n => n.type !== 'customer');
  if (cust) pos[cust.id] = center;
  rest.forEach((n, i) => {
    const angle = (2 * Math.PI * i) / rest.length;
    const r = Math.min(220, 90 + rest.length * 18);
    pos[n.id] = { x: center.x + r * Math.cos(angle), y: center.y + r * Math.sin(angle) };
  });
  return pos;
}

export default function InvestigationGraphPage() {
  const { id } = useParams();
  const [customer, setCustomer] = useState(null);
  const [txData, setTxData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    Promise.all([getCustomer(id), getCustomerTransactions(id, { limit: 200 })])
      .then(([c, t]) => { setCustomer(c); setTxData(t); })
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <LoadingBlock label="Building graph…" />;
  if (!customer) return null;

  const { nodes, edges } = buildGraph(customer, txData);
  const pos = layout(nodes);

  const nodeColor = (n) => {
    if (n.hasSanctions) return '#ef4444';
    if (n.hasPep) return '#f59e0b';
    if (n.type === 'customer') return '#4f46e5';
    if (n.type === 'account') return n.status === 'active' ? '#10b981' : '#94a3b8';
    return '#64748b';
  };

  const legend = [
    ['#4f46e5', 'Customer'], ['#10b981', 'Account (active)'], ['#64748b', 'Counterparty'], ['#ef4444', 'Sanctions hit'],
  ];

  return (
    <div>
      <PageHeader
        title="Investigation Graph"
        breadcrumb={<><Link to="/alerts" className="hover:text-brand">Alerts</Link> <span className="mx-1">/</span> <Link to={`/customers/${id}`} className="hover:text-brand">{customer.full_name}</Link> <span className="mx-1">/</span> Graph</>}
        subtitle="Counterparty money-flow network derived from recent transactions."
      />

      <div className="flex gap-6">
        <Card className="flex-1" bodyClassName="p-0" icon={Network} title="Network">
          <svg viewBox="0 0 800 600" className="w-full h-[600px]">
            {edges.map((e, i) => {
              const from = pos[e.from], to = pos[e.to];
              if (!from || !to) return null;
              const mx = (from.x + to.x) / 2, my = (from.y + to.y) / 2;
              return (
                <g key={i}>
                  <line x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke={e.isBad ? '#ef4444' : '#cbd5e1'} strokeWidth={e.isBad ? 2 : 1} strokeDasharray={e.isBad ? '5 3' : undefined} />
                  {e.amount > 0 && <text x={mx} y={my} textAnchor="middle" fontSize={9} fill="#64748b" dy={-4}>${Math.round(e.amount).toLocaleString()}</text>}
                </g>
              );
            })}
            {nodes.map(n => {
              const p = pos[n.id];
              if (!p) return null;
              const r = n.type === 'customer' ? 26 : n.type === 'account' ? 17 : 12;
              return (
                <g key={n.id} onClick={() => setSelected(selected?.id === n.id ? null : n)} style={{ cursor: 'pointer' }}>
                  <circle cx={p.x} cy={p.y} r={r} fill={nodeColor(n)} opacity={0.9} stroke={selected?.id === n.id ? '#0f172a' : '#fff'} strokeWidth={2} />
                  <text x={p.x} y={p.y + r + 13} textAnchor="middle" fontSize={9} fill="#475569">{(n.label || '').substring(0, 16)}</text>
                </g>
              );
            })}
          </svg>
        </Card>

        {selected && (
          <Card className="w-64 shrink-0" title="Node">
            <p className="text-xs font-semibold text-ink-subtle uppercase tracking-wide">{selected.type}</p>
            <p className="text-sm text-ink-muted font-mono break-all mt-1">{selected.label}</p>
            {selected.status && <p className="text-xs text-ink-subtle mt-1">Status: {selected.status}</p>}
            {selected.hasSanctions && <p className="text-xs text-red-600 font-semibold mt-2">SANCTIONS HIT</p>}
            {selected.hasPep && <p className="text-xs text-amber-600 font-semibold mt-1">PEP HIT</p>}
          </Card>
        )}
      </div>

      <div className="flex flex-wrap gap-4 mt-4 text-xs text-ink-subtle">
        {legend.map(([c, l]) => (
          <span key={l} className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full inline-block" style={{ background: c }} /> {l}</span>
        ))}
        <span className="flex items-center gap-1.5"><span className="w-6 border-b-2 border-dashed border-red-400 inline-block" /> FATF risk route</span>
      </div>
    </div>
  );
}
