import { useState, useEffect } from 'react';
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
