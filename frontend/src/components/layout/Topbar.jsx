import { useState, useEffect, useRef } from 'react';
import { Search, ChevronDown, Check } from 'lucide-react';
import { getOfficers, getHealth } from '../../api/client';
import OfficerAvatar from '../shared/OfficerAvatar';

export default function Topbar() {
  const [officers, setOfficers] = useState([]);
  const [officerId, setOfficerId] = useState(localStorage.getItem('officerId') || '1');
  const [healthy, setHealthy] = useState(null);
  const [open, setOpen] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    getOfficers().then(setOfficers).catch(() => {});
    getHealth().then(() => setHealthy(true)).catch(() => setHealthy(false));
  }, []);

  useEffect(() => {
    function onClick(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  function selectOfficer(id) {
    localStorage.setItem('officerId', String(id));
    setOfficerId(String(id));
    window.location.reload();
  }

  const current = officers.find(o => String(o.officer_id) === String(officerId));

  return (
    <header className="h-16 shrink-0 bg-surface/80 backdrop-blur border-b border-border sticky top-0 z-30 flex items-center gap-4 px-6">
      <div className="relative max-w-md w-full hidden md:block">
        <Search className="w-4 h-4 text-ink-subtle absolute left-3 top-1/2 -translate-y-1/2" />
        <input
          placeholder="Search alerts, customers, cases…"
          className="w-full bg-surface-2 border border-border rounded-lg pl-9 pr-3 py-2 text-sm text-ink
            placeholder:text-ink-subtle focus:outline-none focus:ring-2 focus:ring-brand/30 focus:bg-surface"
        />
      </div>

      <div className="flex-1" />

      <div className="flex items-center gap-1.5 text-xs">
        <span className={`w-2 h-2 rounded-full ${healthy === null ? 'bg-slate-300' : healthy ? 'bg-emerald-500' : 'bg-red-500'}`} />
        <span className="text-ink-subtle hidden sm:inline">{healthy === null ? 'Checking' : healthy ? 'Connected' : 'Offline'}</span>
      </div>

      <div className="relative" ref={menuRef}>
        <button
          onClick={() => setOpen(o => !o)}
          className="flex items-center gap-2 pl-1.5 pr-2 py-1.5 rounded-lg hover:bg-surface-2 transition-colors"
        >
          <OfficerAvatar name={current?.full_name} officerId={current?.officer_id} />
          <div className="text-left hidden sm:block leading-tight">
            <div className="text-xs font-semibold text-ink">{current?.full_name || `Officer #${officerId}`}</div>
            <div className="text-[10px] text-ink-subtle">{current?.role_name || 'officer'}</div>
          </div>
          <ChevronDown className="w-4 h-4 text-ink-subtle" />
        </button>

        {open && (
          <div className="absolute right-0 mt-2 w-64 bg-surface border border-border rounded-xl shadow-lg py-1.5 z-40 max-h-96 overflow-y-auto">
            <p className="px-3 py-1.5 text-[10px] font-semibold text-ink-subtle uppercase tracking-wider">Switch officer</p>
            {officers.map(o => (
              <button
                key={o.officer_id}
                onClick={() => selectOfficer(o.officer_id)}
                className="w-full flex items-center gap-2.5 px-3 py-2 hover:bg-surface-2 text-left"
              >
                <OfficerAvatar name={o.full_name} officerId={o.officer_id} />
                <div className="flex-1 min-w-0 leading-tight">
                  <div className="text-xs font-medium text-ink truncate">{o.full_name}</div>
                  <div className="text-[10px] text-ink-subtle">{o.role_name}</div>
                </div>
                {String(o.officer_id) === String(officerId) && <Check className="w-4 h-4 text-brand" />}
              </button>
            ))}
          </div>
        )}
      </div>
    </header>
  );
}
