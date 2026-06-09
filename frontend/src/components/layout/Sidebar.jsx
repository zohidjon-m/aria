import { NavLink } from 'react-router-dom';
import { LayoutDashboard, Bell, ScrollText, ShieldCheck } from 'lucide-react';

const NAV = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/alerts', label: 'Alerts', icon: Bell },
  { to: '/audit', label: 'Audit Log', icon: ScrollText },
];

export default function Sidebar() {
  return (
    <aside className="w-60 shrink-0 bg-surface border-r border-border flex flex-col h-screen sticky top-0">
      <div className="h-16 flex items-center gap-2.5 px-5 border-b border-border">
        <div className="w-9 h-9 rounded-lg bg-brand flex items-center justify-center shadow-sm">
          <ShieldCheck className="w-5 h-5 text-white" />
        </div>
        <div className="leading-tight">
          <div className="text-sm font-bold text-ink tracking-tight">Aria</div>
          <div className="text-[10px] text-ink-subtle font-medium uppercase tracking-wide">Risk Intelligence</div>
        </div>
      </div>

      <nav className="flex-1 p-3 space-y-1">
        <p className="px-3 py-2 text-[10px] font-semibold text-ink-subtle uppercase tracking-wider">Operations</p>
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-brand-soft text-brand'
                  : 'text-ink-muted hover:bg-surface-2 hover:text-ink'
              }`
            }
          >
            {Icon && <Icon className="w-[18px] h-[18px]" />}
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="p-3 border-t border-border">
        <div className="rounded-lg bg-surface-2 px-3 py-2.5">
          <p className="text-[11px] text-ink-subtle leading-relaxed">
            Agent outputs are <span className="font-semibold text-ink-muted">advisory</span>. Officers make all final decisions.
          </p>
        </div>
      </div>
    </aside>
  );
}
