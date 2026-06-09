import { useState, useEffect, useCallback } from 'react';
import { ScrollText } from 'lucide-react';
import { getAuditLog, getOfficers } from '../api/client';
import PageHeader from '../components/ui/PageHeader';
import Card from '../components/ui/Card';
import Button from '../components/ui/Button';
import { LoadingBlock } from '../components/ui/Spinner';
import EmptyState from '../components/ui/EmptyState';
import Badge from '../components/ui/Badge';
import OfficerAvatar from '../components/shared/OfficerAvatar';

const ENTITY_TONE = { alert: 'blue', case: 'violet', customer: 'emerald' };

export default function AuditLogPage() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [officers, setOfficers] = useState([]);
  const [filters, setFilters] = useState({ officer_id: '', entity_type: '' });
  const limit = 25;

  const load = useCallback(() => {
    setLoading(true);
    const params = { page, limit, ...filters };
    Object.keys(params).forEach(k => params[k] === '' && delete params[k]);
    getAuditLog(params)
      .then(d => { setItems(d.items); setTotal(d.total); })
      .finally(() => setLoading(false));
  }, [page, filters]);

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { load(); }, [load]);
  useEffect(() => { getOfficers().then(setOfficers).catch(() => {}); }, []);

  const setFilter = (k, v) => { setFilters(f => ({ ...f, [k]: v })); setPage(1); };
  const start = (page - 1) * limit + 1;
  const end = Math.min(page * limit, total);

  return (
    <div>
      <PageHeader title="Audit Log" subtitle="Immutable record of every officer action across the platform." />

      <Card bodyClassName="p-0">
        <div className="flex flex-wrap items-center gap-2 px-4 py-3 border-b border-border">
          <select
            value={filters.officer_id}
            onChange={e => setFilter('officer_id', e.target.value)}
            className="bg-surface border border-border rounded-lg px-3 py-1.5 text-xs text-ink focus:outline-none focus:ring-2 focus:ring-brand/30"
          >
            <option value="">All officers</option>
            {officers.map(o => <option key={o.officer_id} value={o.officer_id}>{o.full_name}</option>)}
          </select>
          <select
            value={filters.entity_type}
            onChange={e => setFilter('entity_type', e.target.value)}
            className="bg-surface border border-border rounded-lg px-3 py-1.5 text-xs text-ink focus:outline-none focus:ring-2 focus:ring-brand/30"
          >
            <option value="">All entities</option>
            <option value="alert">Alert</option>
            <option value="case">Case</option>
            <option value="customer">Customer</option>
          </select>
          <div className="ml-auto text-xs text-ink-subtle">{total > 0 ? `${start}–${end} of ${total}` : '0 records'}</div>
        </div>

        {loading ? (
          <LoadingBlock />
        ) : items.length === 0 ? (
          <div className="p-4"><EmptyState icon={ScrollText} title="No audit records" message="No actions match the current filters." /></div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-ink-subtle uppercase tracking-wide bg-surface-2/60">
                <th className="font-medium px-4 py-2.5">Officer</th>
                <th className="font-medium px-4 py-2.5">Action</th>
                <th className="font-medium px-4 py-2.5">Entity</th>
                <th className="font-medium px-4 py-2.5">Details</th>
                <th className="font-medium px-4 py-2.5 text-right">When</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {items.map(ev => (
                <tr key={ev.log_id} className="hover:bg-surface-2 transition-colors">
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <OfficerAvatar name={ev.officer_name} officerId={ev.officer_id} />
                      <span className="text-ink text-xs font-medium">{ev.officer_name || 'System'}</span>
                    </div>
                  </td>
                  <td className="px-4 py-2.5 text-ink-muted">{(ev.action || '').replace(/_/g, ' ')}</td>
                  <td className="px-4 py-2.5">
                    <Badge tone={ENTITY_TONE[ev.entity_type] || 'slate'}>{ev.entity_type} #{ev.entity_id}</Badge>
                  </td>
                  <td className="px-4 py-2.5 text-xs text-ink-subtle max-w-xs truncate font-mono">
                    {ev.details ? (typeof ev.details === 'string' ? ev.details : JSON.stringify(ev.details)) : '—'}
                  </td>
                  <td className="px-4 py-2.5 text-right text-xs text-ink-subtle whitespace-nowrap">
                    {new Date(ev.action_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-border">
          <Button variant="secondary" size="sm" disabled={page === 1} onClick={() => setPage(p => p - 1)}>Prev</Button>
          <Button variant="secondary" size="sm" disabled={end >= total} onClick={() => setPage(p => p + 1)}>Next</Button>
        </div>
      </Card>
    </div>
  );
}
