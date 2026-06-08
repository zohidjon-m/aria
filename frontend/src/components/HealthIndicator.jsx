import React from 'react';

const COLORS = {
  healthy: 'bg-green-500',
  degraded: 'bg-yellow-500',
  offline: 'bg-red-500',
  checking: 'bg-slate-500',
};

const LABELS = {
  healthy: 'Online',
  degraded: 'Degraded',
  offline: 'Offline',
  checking: 'Checking...',
};

const HealthIndicator = ({ status }) => {
  const color = COLORS[status] || COLORS.checking;
  const label = LABELS[status] || 'Unknown';

  return (
    <div
      className="flex items-center gap-1.5 text-xs text-slate-400"
      title={`Backend status: ${label}`}
    >
      <span className="relative flex h-2 w-2">
        {status === 'healthy' && (
          <span className={`absolute inline-flex h-full w-full animate-ping rounded-full ${color} opacity-60`} />
        )}
        <span className={`relative inline-flex h-2 w-2 rounded-full ${color}`} />
      </span>
      <span className="font-medium">{label}</span>
    </div>
  );
};

export default HealthIndicator;
