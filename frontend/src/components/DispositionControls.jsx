import { useState } from 'react';
import { Check, XCircle, ArrowUpRight } from 'lucide-react';
import { postAlertDisposition } from '../api/client';
import Button from './ui/Button';

const STATUSES = [
  { value: 'dismissed', label: 'Dismiss', icon: XCircle, variant: 'secondary' },
  { value: 'escalated', label: 'Escalate', icon: ArrowUpRight, variant: 'danger' },
  { value: 'resolved', label: 'Mark Reviewed', icon: Check, variant: 'primary' },
];

export default function DispositionControls({ alertId, onSuccess }) {
  const [notes, setNotes] = useState('');
  const [selected, setSelected] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);

  const canSubmit = selected && notes.trim().length > 0 && !submitting;

  async function handleSubmit() {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      await postAlertDisposition(alertId, { status: selected, notes: notes.trim() });
      setSuccess(true);
      setNotes('');
      setSelected('');
      onSuccess?.();
      setTimeout(() => setSuccess(false), 3000);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-3">
      <textarea
        value={notes}
        onChange={e => setNotes(e.target.value)}
        placeholder="Disposition notes (required)…"
        rows={3}
        className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-sm text-ink placeholder:text-ink-subtle resize-none focus:outline-none focus:ring-2 focus:ring-brand/30"
      />
      <div className="grid grid-cols-3 gap-2">
        {STATUSES.map(s => (
          <button
            key={s.value}
            onClick={() => setSelected(v => (v === s.value ? '' : s.value))}
            className={`flex flex-col items-center gap-1 py-2.5 rounded-lg border text-xs font-medium transition-all ${
              selected === s.value
                ? 'border-brand bg-brand-soft text-brand ring-1 ring-brand/30'
                : 'border-border text-ink-muted hover:border-border-strong hover:bg-surface-2'
            }`}
          >
            <s.icon className="w-4 h-4" />
            {s.label}
          </button>
        ))}
      </div>
      {error && <p className="text-xs text-red-600">{error}</p>}
      {success && <p className="text-xs text-emerald-600 flex items-center gap-1"><Check className="w-3.5 h-3.5" /> Disposition saved.</p>}
      <div className="flex items-center gap-2">
        <Button onClick={handleSubmit} disabled={!canSubmit} loading={submitting}>Submit Disposition</Button>
        {!selected && <span className="text-xs text-ink-subtle">Select a status above</span>}
      </div>
    </div>
  );
}
