import { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { getOfficers, getHealth } from '../api/client';

export default function Nav() {
  const location = useLocation();
  const [officers, setOfficers] = useState([]);
  const [officerId, setOfficerId] = useState(localStorage.getItem('officerId') || '1');
  const [healthy, setHealthy] = useState(null);

  useEffect(() => {
    getOfficers().then(d => setOfficers(d)).catch(() => {});
    getHealth().then(() => setHealthy(true)).catch(() => setHealthy(false));
  }, []);

  function handleOfficerChange(e) {
    setOfficerId(e.target.value);
    localStorage.setItem('officerId', e.target.value);
    window.location.reload();
  }

  const navLink = (to, label) => (
    <Link
      to={to}
      className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
        location.pathname.startsWith(to)
          ? 'bg-brand-primary text-white'
          : 'text-gray-400 hover:text-white'
      }`}
    >
      {label}
    </Link>
  );

  return (
    <nav className="fixed top-0 left-0 right-0 z-40 h-12 bg-dark-panel border-b border-dark-border flex items-center px-4 gap-4">
      <span className="text-brand-primary font-bold text-sm tracking-wide mr-2">AML WORKBENCH</span>
      {navLink('/alerts', 'Alerts')}
      <div className="flex-1" />
      <select
        value={officerId}
        onChange={handleOfficerChange}
        className="bg-dark-bg border border-dark-border text-gray-300 text-xs rounded px-2 py-1"
      >
        {officers.length === 0 && <option value={officerId}>Officer #{officerId}</option>}
        {officers.map(o => (
          <option key={o.officer_id} value={String(o.officer_id)}>
            {o.full_name} ({o.role_name})
          </option>
        ))}
      </select>
      <span
        title={healthy === null ? 'Checking...' : healthy ? 'API healthy' : 'API unreachable'}
        className={`w-2 h-2 rounded-full ${
          healthy === null ? 'bg-gray-500' : healthy ? 'bg-green-500' : 'bg-red-500'
        }`}
      />
    </nav>
  );
}
