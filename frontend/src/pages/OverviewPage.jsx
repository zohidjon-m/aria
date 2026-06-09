import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  Bell, FolderOpen, ArrowUpRight, AlertOctagon, Flame, Layers, Activity, ChevronRight,
} from 'lucide-react';
import { getAlerts, getAuditLog } from '../api/client';
import PageHeader from '../components/ui/PageHeader';
import Card from '../components/ui/Card';
import StatTile from '../components/ui/StatTile';
import { LoadingBlock } from '../components/ui/Spinner';
import EmptyState from '../components/ui/EmptyState';
import SeverityBadge from '../components/shared/SeverityBadge';
import StatusBadge from '../components/shared/StatusBadge';
import OfficerAvatar from '../components/shared/OfficerAvatar';

function relTime(d) {
  const diff = Date.now() - new Date(d).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

const SEV_BAR = { critical: 'bg-red-500', high: 'bg-amber-500', medium: 'bg-yellow-400', low: 'bg-emerald-500' };

export default function OverviewPage() {
  const [kpis, setKpis] = useState(null);
  const [recent, setRecent] = useState([]);
  const [activity, setActivity] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const count = (params) => getAlerts({ ...params, limit: 1 }).then(r => r.total).catch(() => 0);
    Promise.all([
      count({}),
      count({ status: 'open' }),
      count({ status: 'under_review' }),
      count({ status: 'escalated' }),
      count({ severity: 'critical' }),
      count({ severity: 'high' }),
      count({ severity: 'medium' }),
      count({ severity: 'low' }),
      getAlerts({ sort_by: 'created_at', limit: 8 }).then(r => r.items).catch(() => []),
      getAuditLog({ limit: 8 }).then(r => r.items).catch(() => []),
    ]).then(([total, open, review, escalated, critical, high, medium, low, recentAlerts, acts]) => {
      setKpis({ total, open, review, escalated, critical, high, medium, low });
      setRecent(recentAlerts);
      setActivity(acts);
    }).finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingBlock label="Loading overview…" />;

  const sevTotal = (kpis.critical + kpis.high + kpis.medium + kpis.low) || 1;
  const sevRows = [
    { key: 'critical', label: 'Critical', n: kpis.critical },
    { key: 'high', label: 'High', n: kpis.high },
    { key: 'medium', label: 'Medium', n: kpis.medium },
    { key: 'low', label: 'Low', n: kpis.low },
  ];

  return (
    <div>
      <PageHeader
        title="Operations Overview"
        subtitle="Live snapshot of alert volume, escalations and recent activity across the program."
      />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <StatTile label="Total Alerts" value={kpis.total} icon={Bell} tone="indigo" />
        <StatTile label="Open" value={kpis.open} icon={FolderOpen} tone="blue" />
        <StatTile label="Under Review" value={kpis.review} icon={Activity} tone="amber" />
        <StatTile label="Escalated" value={kpis.escalated} icon={ArrowUpRight} tone="red" />
        <StatTile label="Critical" value={kpis.critical} icon={AlertOctagon} tone="red" />
        <StatTile label="High" value={kpis.high} icon={Flame} tone="amber" />
        <StatTile label="Medium" value={kpis.medium} icon={Layers} tone="violet" />
        <StatTile label="Low" value={kpis.low} icon={Layers} tone="emerald" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <Card
            title="Recent Alerts"
            icon={Bell}
            actions={<Link to="/alerts" className="text-xs font-medium text-brand hover:underline inline-flex items-center gap-0.5">View all <ChevronRight className="w-3.5 h-3.5" /></Link>}
            bodyClassName="p-0"
          >
            {recent.length === 0 ? (
              <div className="p-4"><EmptyState icon={Bell} title="No alerts" message="No alerts have been generated yet." /></div>
            ) : (
              <div className="divide-y divide-border">
                {recent.map(a => (
                  <Link
                    key={a.alert_id}
                    to={`/alerts/${a.alert_id}`}
                    className="flex items-center gap-3 px-4 py-3 hover:bg-surface-2 transition-colors"
                  >
                    <SeverityBadge severity={a.severity} />
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium text-ink truncate">{a.rule_name}</div>
                      <div className="text-xs text-ink-subtle truncate">{a.customer_name} · #{a.alert_id}</div>
                    </div>
                    <div className="text-sm font-semibold text-ink tnum hidden sm:block">
                      {a.amount_usd != null ? `$${Number(a.amount_usd).toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '—'}
                    </div>
                    <StatusBadge status={a.status} />
                    <span className="text-xs text-ink-subtle w-16 text-right hidden md:block">{relTime(a.created_at)}</span>
                  </Link>
                ))}
              </div>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <Card title="Severity Distribution" icon={Layers}>
            <div className="space-y-3">
              {sevRows.map(r => (
                <div key={r.key}>
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className="text-ink-muted font-medium">{r.label}</span>
                    <span className="text-ink-subtle tnum">{r.n}</span>
                  </div>
                  <div className="h-2 bg-surface-2 rounded-full overflow-hidden">
                    <div className={`h-full rounded-full ${SEV_BAR[r.key]}`} style={{ width: `${(r.n / sevTotal) * 100}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </Card>

          <Card
            title="Recent Activity"
            icon={Activity}
            actions={<Link to="/audit" className="text-xs font-medium text-brand hover:underline">Audit log</Link>}
            bodyClassName="p-0"
          >
            {activity.length === 0 ? (
              <div className="p-4"><EmptyState icon={Activity} title="No activity" message="No audited actions recorded yet." /></div>
            ) : (
              <div className="divide-y divide-border">
                {activity.map(ev => (
                  <div key={ev.log_id} className="flex items-center gap-2.5 px-4 py-2.5">
                    <OfficerAvatar name={ev.officer_name} officerId={ev.officer_id} />
                    <div className="min-w-0 flex-1">
                      <div className="text-xs text-ink">
                        <span className="font-medium">{ev.officer_name || 'System'}</span>{' '}
                        <span className="text-ink-muted">{(ev.action || '').replace(/_/g, ' ')}</span>{' '}
                        <span className="text-ink-subtle">{ev.entity_type} #{ev.entity_id}</span>
                      </div>
                      <div className="text-[10px] text-ink-subtle">{relTime(ev.action_at)}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
