import React from 'react';

const STYLES = {
  critical: 'bg-red-500 text-white',
  high: 'bg-orange-500 text-white',
  medium: 'bg-yellow-500 text-black',
  low: 'bg-green-500 text-white',
};

const RiskBadge = ({ level }) => {
  if (!level) return null;
  const norm = String(level).toLowerCase();
  const style = STYLES[norm] || 'bg-slate-600 text-white';

  return (
    <span
      className={`px-2 py-1 text-xs font-semibold rounded-md ${style} tracking-wide uppercase shadow-sm transition`}
    >
      {level}
    </span>
  );
};

export default RiskBadge;
