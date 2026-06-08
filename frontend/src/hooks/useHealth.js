import { useEffect, useState } from 'react';
import { getHealth } from '../api/client';

export function useHealth(intervalMs = 15000) {
  const [status, setStatus] = useState('checking');

  useEffect(() => {
    let cancelled = false;

    const check = async () => {
      try {
        const r = await getHealth();
        if (!cancelled) setStatus(r.status === 'healthy' ? 'healthy' : 'degraded');
      } catch {
        if (!cancelled) setStatus('offline');
      }
    };

    check();
    const id = setInterval(check, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [intervalMs]);

  return status;
}
