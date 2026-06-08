import { useState } from 'react';
import { postAlertDisposition } from '../api/client';

const STATUSES = [
  { value: 'dismissed', label: 'Dismiss', cls: 'bg-gray-700 hover:bg-gray-600 text-gray-200' },
  { value: 'escalated', label: 'Escalate', cls: 'bg-red-900 hover:bg-red-800 text-red-200 border border-red-700' },
  { value: 'resolved', label: 'Mark Reviewed', cls: 'bg-blue-900 hover:bg-blue-800 text-blue-200 border border-blue-700' },
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
    <div>
      <textarea
        value={notes}
        onChange={e => setNotes(e.target.value)}
        placeholder="Disposition notes (required)..."
        rows={3}
        className="w-full bg-dark-bg border border-dark-border rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-brand-primary resize-none mb-2"
      />
      <div className="flex gap-2 mb-2">
        {STATUSES.map(s => (
          <button
            key={s.value}
            onClick={() => setSelected(v => v === s.value ? '' : s.value)}
            className={`px-3 py-1 text-xs rounded font-medium transition-all ${s.cls} ${
              selected === s.value ? 'ring-2 ring-white/40' : ''
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>
      {error && <div className="text-xs text-red-400 mb-2">{error}</div>}
      {success && <div className="text-xs text-green-400 mb-2">Disposition saved.</div>}
      <button
        onClick={handleSubmit}
        disabled={!canSubmit}
        className="px-4 py-1.5 text-xs bg-brand-primary rounded font-semibold disabled:opacity-30 hover:opacity-90 transition-opacity"
      >
        {submitting ? 'Saving...' : 'Submit Disposition'}
      </button>
      {!selected && <span className="ml-2 text-xs text-gray-600">Select a status above</span>}
    </div>
  );
}
