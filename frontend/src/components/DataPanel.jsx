import React, { useCallback, useEffect, useState } from 'react';
import {
  Users,
  AlertOctagon,
  Briefcase,
  Calendar,
  Activity,
  RefreshCw,
  Inbox,
  Filter,
} from 'lucide-react';
import { getCustomers, getAlerts, getCases } from '../api/client';
import RiskBadge from './RiskBadge';

const TABS = [
  { id: 'alerts', label: 'Alert Triage', icon: AlertOctagon },
  { id: 'customers', label: 'Customers', icon: Users },
  { id: 'cases', label: 'Open Cases', icon: Briefcase },
];

const SEVERITIES = ['critical', 'high', 'medium', 'low'];
const ALERT_STATUSES = ['open', 'under_review', 'dismissed', 'resolved'];
const RISK_LEVELS = ['critical', 'high', 'medium', 'low'];
const CASE_STATUSES = ['open', 'in_progress', 'closed', 'escalated'];

const DataPanel = ({ activeContext, onContextSelect, onPreFillChat, onError }) => {
  const [activeTab, setActiveTab] = useState('alerts');
  const [data, setData] = useState({ customers: [], alerts: [], cases: [] });
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({
    alerts: { severity: '', status: '' },
    customers: { risk_level: '' },
    cases: { status: '' },
  });

  const fetchData = useCallback(
    async (tab, tabFilters) => {
      setLoading(true);
      try {
        const params = Object.fromEntries(
          Object.entries(tabFilters || {}).filter(([, v]) => v)
        );
        if (tab === 'customers') {
          const res = await getCustomers(params);
          setData((prev) => ({ ...prev, customers: res.data || [] }));
        } else if (tab === 'alerts') {
          const res = await getAlerts(params);
          setData((prev) => ({ ...prev, alerts: res.data || [] }));
        } else if (tab === 'cases') {
          const res = await getCases(params);
          setData((prev) => ({ ...prev, cases: res.data || [] }));
        }
      } catch (error) {
        console.error(error);
        onError?.(`Failed to load ${tab}: ${error.message || 'network error'}`);
      } finally {
        setLoading(false);
      }
    },
    [onError]
  );

  useEffect(() => {
    fetchData(activeTab, filters[activeTab]);
  }, [activeTab, filters, fetchData]);

  const updateFilter = (tab, key, value) => {
    setFilters((prev) => ({ ...prev, [tab]: { ...prev[tab], [key]: value } }));
  };

  const currentList = data[activeTab] || [];

  return (
    <div className="flex h-full flex-col bg-dark-bg">
      {/* Header & Tabs */}
      <div className="border-b border-dark-border px-6 pt-6">
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-2xl font-bold tracking-tight text-white">Compliance Desk</h1>
          <button
            onClick={() => fetchData(activeTab, filters[activeTab])}
            disabled={loading}
            title="Refresh"
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800/60 px-3 py-1.5 text-xs font-medium text-slate-300 transition hover:border-slate-600 hover:bg-slate-700/80 disabled:opacity-50"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
        <div className="relative flex gap-6">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id)}
              className={`relative flex items-center gap-2 pb-4 font-medium transition duration-200 ${
                activeTab === t.id ? 'text-brand-primary' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <t.icon size={18} className={activeTab === t.id ? '' : 'opacity-70'} />
              {t.label}
              {activeTab === t.id && (
                <div className="absolute bottom-0 left-0 h-[3px] w-full rounded-t-sm bg-brand-primary" />
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Filter Row */}
      <div className="flex items-center gap-3 border-b border-dark-border bg-slate-900/30 px-6 py-3">
        <Filter size={14} className="text-slate-500" />
        {activeTab === 'alerts' && (
          <>
            <FilterSelect
              label="Severity"
              value={filters.alerts.severity}
              options={SEVERITIES}
              onChange={(v) => updateFilter('alerts', 'severity', v)}
            />
            <FilterSelect
              label="Status"
              value={filters.alerts.status}
              options={ALERT_STATUSES}
              onChange={(v) => updateFilter('alerts', 'status', v)}
            />
          </>
        )}
        {activeTab === 'customers' && (
          <FilterSelect
            label="Risk Level"
            value={filters.customers.risk_level}
            options={RISK_LEVELS}
            onChange={(v) => updateFilter('customers', 'risk_level', v)}
          />
        )}
        {activeTab === 'cases' && (
          <FilterSelect
            label="Status"
            value={filters.cases.status}
            options={CASE_STATUSES}
            onChange={(v) => updateFilter('cases', 'status', v)}
          />
        )}
        <span className="ml-auto text-xs text-slate-500">
          {loading ? 'Loading...' : `${currentList.length} result${currentList.length === 1 ? '' : 's'}`}
        </span>
      </div>

      {/* Content Area */}
      <div className="relative flex-1 overflow-y-auto bg-slate-900/40 p-6">
        {loading ? (
          <SkeletonList />
        ) : currentList.length === 0 ? (
          <EmptyState tab={activeTab} />
        ) : (
          <div className="grid gap-4">
            {activeTab === 'alerts' &&
              data.alerts.map((a) => (
                <AlertCard
                  key={a.alert_id}
                  alert={a}
                  active={activeContext?.data?.alert_id === a.alert_id}
                  onSelect={() => onContextSelect({ type: 'alert', data: a })}
                  onPreFillChat={onPreFillChat}
                />
              ))}

            {activeTab === 'customers' &&
              data.customers.map((c) => (
                <CustomerCard
                  key={c.customer_id}
                  customer={c}
                  active={activeContext?.data?.customer_id === c.customer_id}
                  onSelect={() => onContextSelect({ type: 'customer', data: c })}
                  onPreFillChat={onPreFillChat}
                />
              ))}

            {activeTab === 'cases' &&
              data.cases.map((c) => (
                <CaseCard
                  key={c.case_id}
                  caseItem={c}
                  active={activeContext?.data?.case_id === c.case_id}
                  onSelect={() => onContextSelect({ type: 'case', data: c })}
                  onPreFillChat={onPreFillChat}
                />
              ))}
          </div>
        )}
      </div>
    </div>
  );
};

const FilterSelect = ({ label, value, options, onChange }) => (
  <select
    value={value}
    onChange={(e) => onChange(e.target.value)}
    className="rounded-md border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-brand-primary focus:outline-none"
  >
    <option value="">{label}: any</option>
    {options.map((opt) => (
      <option key={opt} value={opt}>
        {opt.replace(/_/g, ' ')}
      </option>
    ))}
  </select>
);

const SkeletonList = () => (
  <div className="grid gap-4">
    {[0, 1, 2, 3].map((i) => (
      <div
        key={i}
        className="h-24 animate-pulse rounded-xl border border-dark-border bg-slate-800/40"
      />
    ))}
  </div>
);

const EmptyState = ({ tab }) => (
  <div className="flex h-64 flex-col items-center justify-center gap-3 text-slate-500">
    <Inbox size={48} className="opacity-40" />
    <p className="text-sm font-medium">No {tab} match your filters.</p>
    <p className="text-xs text-slate-600">Try clearing filters or refreshing.</p>
  </div>
);

const AlertCard = ({ alert: a, active, onSelect, onPreFillChat }) => (
  <div
    onClick={onSelect}
    className={`group cursor-pointer rounded-xl border bg-dark-panel p-5 shadow-sm transition hover:bg-slate-800/80 ${
      active ? 'border-brand-primary/60 ring-1 ring-brand-primary/20' : 'border-dark-border'
    }`}
  >
    <div className="mb-3 flex items-start justify-between">
      <div>
        <h3 className="flex items-center gap-2 text-lg font-semibold text-white">{a.rule_name}</h3>
        <p className="mt-1 text-sm text-slate-400">
          {a.customer_name} (ID: {a.customer_id})
        </p>
      </div>
      <RiskBadge level={a.severity} />
    </div>
    <div className="mt-4 flex flex-wrap gap-2 text-xs font-medium text-slate-500">
      <span className="flex items-center gap-1.5 rounded bg-slate-900/50 px-2 py-1">
        <Activity size={14} className="text-brand-accent" /> Status:{' '}
        <span className="capitalize text-slate-300">{(a.status || '').replace(/_/g, ' ')}</span>
      </span>
      <span className="flex items-center gap-1.5 rounded bg-slate-900/50 px-2 py-1">
        <Calendar size={14} /> {new Date(a.created_at).toLocaleDateString()}
      </span>
    </div>
    {active && (
      <div className="mt-5 flex justify-end border-t border-slate-700/50 pt-4">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onPreFillChat(`Triage alert ${a.alert_id}`);
          }}
          className="flex items-center gap-2 rounded-lg bg-brand-primary px-4 py-1.5 text-sm font-medium text-white shadow-md transition hover:bg-blue-600"
        >
          <AlertOctagon size={16} /> Ask ARIA to Triage
        </button>
      </div>
    )}
  </div>
);

const CustomerCard = ({ customer: c, active, onSelect, onPreFillChat }) => (
  <div
    onClick={onSelect}
    className={`cursor-pointer rounded-xl border bg-dark-panel p-5 transition hover:bg-slate-800 ${
      active ? 'border-brand-primary/60' : 'border-dark-border'
    }`}
  >
    <div className="flex items-center justify-between">
      <div>
        <h3 className="text-lg font-semibold text-white">{c.full_name}</h3>
        <p className="text-sm text-slate-400">
          Customer ID: {c.customer_id} • {c.nationality}
        </p>
      </div>
      <RiskBadge level={c.risk_level} />
    </div>
    {active && (
      <div className="mt-5 flex justify-end border-t border-slate-700 pt-4">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onPreFillChat(`Analyze customer ${c.customer_id}`);
          }}
          className="flex items-center gap-2 rounded-lg bg-brand-primary px-4 py-1.5 text-sm font-medium text-white transition hover:bg-blue-600"
        >
          <Users size={16} /> Analyze Risk Profile
        </button>
      </div>
    )}
  </div>
);

const CaseCard = ({ caseItem: c, active, onSelect, onPreFillChat }) => (
  <div
    onClick={onSelect}
    className={`cursor-pointer rounded-xl border bg-dark-panel p-5 transition hover:bg-slate-800 ${
      active ? 'border-brand-accent/60 ring-1 ring-brand-accent/20' : 'border-dark-border'
    }`}
  >
    <div className="mb-2 flex items-start justify-between">
      <h3 className="flex items-center gap-2 font-semibold text-white">
        Case #{c.case_id}
        <span className="rounded bg-slate-700 px-2 py-0.5 text-xs text-slate-300">{c.case_type}</span>
      </h3>
      <RiskBadge level={c.priority} />
    </div>
    <p className="text-sm text-slate-400">Subject: {c.customer_name}</p>
    {active && (
      <div className="mt-5 flex justify-end gap-3 border-t border-slate-700 pt-4">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onPreFillChat(`Draft investigation narrative for case ${c.case_id}`);
          }}
          className="rounded-lg bg-slate-700 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-slate-600"
        >
          Draft Narrative
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onPreFillChat(`Draft SAR report for case ${c.case_id}`);
          }}
          className="rounded-lg bg-brand-accent px-3 py-1.5 text-sm font-medium text-white transition hover:bg-violet-600"
        >
          Draft Full SAR
        </button>
      </div>
    )}
  </div>
);

export default DataPanel;
