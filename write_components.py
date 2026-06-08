import pathlib

COMPONENTS = pathlib.Path("D:/sejong_major/projects/compliance-agent/frontend/src/components")

# ── AgentProposalPanel.jsx ────────────────────────────────────────────────────
(COMPONENTS / "AgentProposalPanel.jsx").write_text(r"""import HumanReviewBanner from './shared/HumanReviewBanner';
import ConfidenceMeter from './shared/ConfidenceMeter';

const RECOMMENDATION_LABELS = {
  escalate: { label: 'ESCALATE', cls: 'bg-red-900 text-red-300 border border-red-700' },
  needs_investigation: { label: 'NEEDS INVESTIGATION', cls: 'bg-amber-900 text-amber-300 border border-amber-700' },
  investigate: { label: 'NEEDS INVESTIGATION', cls: 'bg-amber-900 text-amber-300 border border-amber-700' },
  likely_false_positive: { label: 'LIKELY FALSE POSITIVE', cls: 'bg-green-900 text-green-300 border border-green-700' },
};

function SourceRefChip({ ref: refStr }) {
  return (
    <span className="font-mono text-xs bg-dark-bg border border-dark-border rounded px-1 py-0.5 text-gray-400 mr-1 inline-block">
      {refStr}
    </span>
  );
}

export default function AgentProposalPanel({ run, onViewTrace }) {
  if (!run) return null;

  const output = run.output || {};
  const validation = run.validation || {};

  const recommendation = output.recommendation || output.action;
  const recMeta = RECOMMENDATION_LABELS[recommendation] || {
    label: recommendation || 'UNKNOWN',
    cls: 'bg-gray-800 text-gray-300 border border-gray-600',
  };

  const confidence = output.confidence_score ?? output.confidence ?? null;
  const claims = output.factual_claims || [];
  const limitations = output.limitations || [];
  const validationStatus = validation.status || 'not_run';
  const unsupportedCount = validation.unsupported_claim_count ?? 0;

  return (
    <div>
      <HumanReviewBanner />
      <div className="mt-3">
        <div className="flex items-center gap-3 mb-3">
          <span className={`text-xs font-bold px-2 py-1 rounded uppercase tracking-wide ${recMeta.cls}`}>
            {recMeta.label}
          </span>
          {confidence !== null && (
            <div className="flex-1">
              <ConfidenceMeter score={confidence} />
            </div>
          )}
        </div>

        {confidence !== null && (
          <div className="text-xs text-gray-500 mb-3">Confidence: {confidence}/100</div>
        )}

        {output.summary && (
          <div className="text-xs text-gray-300 bg-dark-bg rounded p-2 mb-3 leading-relaxed">
            {output.summary}
          </div>
        )}

        {claims.length > 0 && (
          <div className="mb-3">
            <div className="text-xs uppercase tracking-wide text-gray-500 mb-1 font-semibold">Factual Claims</div>
            {claims.map((c, i) => (
              <div key={i} className="mb-2">
                <div className="text-xs text-gray-300 mb-0.5">{c.statement || c}</div>
                {c.evidence_refs?.length > 0 && (
                  <div>
                    {c.evidence_refs.map((r, j) => <SourceRefChip key={j} ref={r} />)}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {limitations.length > 0 && (
          <div className="mb-3">
            <div className="text-xs uppercase tracking-wide text-gray-500 mb-1 font-semibold">Limitations</div>
            {limitations.map((l, i) => (
              <div key={i} className="flex gap-1 text-xs text-amber-400 mb-0.5">
                <span>&#9888;</span>
                <span>{typeof l === 'string' ? l : l.description || JSON.stringify(l)}</span>
              </div>
            ))}
          </div>
        )}

        <div className="flex items-center gap-2 mb-3">
          <span className="text-xs text-gray-500">Validation:</span>
          <span className={`text-xs font-semibold px-1 py-0.5 rounded ${
            validationStatus === 'passed' ? 'bg-green-900 text-green-300' :
            validationStatus === 'failed' ? 'bg-red-900 text-red-300' :
            'bg-gray-800 text-gray-400'
          }`}>
            {validationStatus.toUpperCase()}
          </span>
          {unsupportedCount > 0 && (
            <span className="text-xs text-amber-400">{unsupportedCount} unsupported claim(s)</span>
          )}
        </div>

        <button
          onClick={onViewTrace}
          className="text-xs text-brand-primary hover:underline"
        >
          View Full Trace &rarr;
        </button>
      </div>
    </div>
  );
}
""", encoding="utf-8")

# ── AgentTraceDrawer.jsx ──────────────────────────────────────────────────────
(COMPONENTS / "AgentTraceDrawer.jsx").write_text(r"""import { useState, useEffect } from 'react';
import { getAgentTrace } from '../api/client';
import LoadingSpinner from './shared/LoadingSpinner';

const STEP_ICONS = {
  planning: 'P',
  tool_executed: 'T',
  observing: 'O',
  revising: 'R',
  proposed: 'F',
  failed_safe: '!',
};

const STEP_COLORS = {
  planning: 'text-blue-400',
  tool_executed: 'text-purple-400',
  observing: 'text-cyan-400',
  revising: 'text-yellow-400',
  proposed: 'text-green-400',
  failed_safe: 'text-red-400',
};

function StepRow({ step }) {
  const [open, setOpen] = useState(false);
  const icon = STEP_ICONS[step.type] || '?';
  const color = STEP_COLORS[step.type] || 'text-gray-400';

  return (
    <div className="border-b border-dark-border last:border-0">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-start gap-2 py-2 text-left hover:bg-dark-bg transition-colors"
      >
        <span className={`w-5 h-5 flex items-center justify-center rounded text-xs font-bold shrink-0 mt-0.5 ${color} border border-current`}>
          {icon}
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-xs font-semibold text-gray-300 uppercase tracking-wide">{step.type}</div>
          {step.thought && (
            <div className="text-xs text-gray-400 truncate mt-0.5">{step.thought}</div>
          )}
        </div>
        <span className="text-gray-600 text-xs">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="pl-7 pb-2 text-xs space-y-1">
          {step.thought && (
            <div className="text-gray-300 leading-relaxed">{step.thought}</div>
          )}
          {step.hypothesis_before && (
            <div>
              <span className="text-gray-500">Hypothesis before: </span>
              <span className="text-gray-400">{step.hypothesis_before}</span>
            </div>
          )}
          {step.hypothesis_after && (
            <div>
              <span className="text-gray-500">Hypothesis after: </span>
              <span className="text-amber-300">{step.hypothesis_after}</span>
            </div>
          )}
          {step.tool_name && (
            <div>
              <span className="text-gray-500">Tool: </span>
              <span className="text-purple-300 font-mono">{step.tool_name}</span>
            </div>
          )}
          {step.tool_args && (
            <pre className="bg-dark-bg rounded p-2 overflow-x-auto text-gray-400 text-xs mt-1">
              {JSON.stringify(step.tool_args, null, 2)}
            </pre>
          )}
          {step.observation && (
            <div className="bg-dark-bg rounded p-2 text-gray-400 mt-1">{step.observation}</div>
          )}
        </div>
      )}
    </div>
  );
}

export default function AgentTraceDrawer({ runId, isOpen, onClose }) {
  const [trace, setTrace] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!isOpen || !runId) return;
    setLoading(true);
    setError(null);
    getAgentTrace(runId)
      .then(setTrace)
      .catch(e => setError(e.response?.data?.detail || e.message))
      .finally(() => setLoading(false));
  }, [isOpen, runId]);

  useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === 'Escape' && isOpen) onClose();
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="fixed inset-0 bg-black/40" onClick={onClose} />
      <div className="relative w-full max-w-2xl bg-dark-panel border-l border-dark-border flex flex-col h-full overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-dark-border shrink-0">
          <div>
            <div className="text-sm font-semibold text-gray-200">Agent Trace</div>
            {runId && <div className="text-xs text-gray-500 font-mono">{runId}</div>}
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white text-lg leading-none">&#x2715;</button>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-3">
          {loading && <LoadingSpinner />}
          {error && <div className="text-xs text-red-400">{error}</div>}
          {trace && (
            <div className="space-y-4">
              {trace.agent_steps?.length > 0 && (
                <div>
                  <div className="text-xs uppercase tracking-wide text-gray-500 font-semibold mb-2">Agent Steps</div>
                  {trace.agent_steps.map((s, i) => <StepRow key={i} step={s} />)}
                </div>
              )}

              {trace.tool_calls?.length > 0 && (
                <div>
                  <div className="text-xs uppercase tracking-wide text-gray-500 font-semibold mb-2">Tool Calls</div>
                  {trace.tool_calls.map((t, i) => (
                    <div key={i} className="mb-2 text-xs">
                      <span className="text-purple-400 font-mono">{t.tool_name}</span>
                      <pre className="bg-dark-bg rounded p-2 overflow-x-auto text-gray-400 mt-1 text-xs">
                        {JSON.stringify(t.args || t, null, 2)}
                      </pre>
                    </div>
                  ))}
                </div>
              )}

              {trace.baseline_snapshots?.length > 0 && (
                <div>
                  <div className="text-xs uppercase tracking-wide text-gray-500 font-semibold mb-2">Baseline Snapshots</div>
                  {trace.baseline_snapshots.map((s, i) => (
                    <pre key={i} className="bg-dark-bg rounded p-2 overflow-x-auto text-gray-400 text-xs mb-2">
                      {JSON.stringify(s, null, 2)}
                    </pre>
                  ))}
                </div>
              )}

              {trace.money_flow_paths?.length > 0 && (
                <div>
                  <div className="text-xs uppercase tracking-wide text-gray-500 font-semibold mb-2">Money Flow Paths</div>
                  {trace.money_flow_paths.map((p, i) => (
                    <pre key={i} className="bg-dark-bg rounded p-2 overflow-x-auto text-gray-400 text-xs mb-2">
                      {JSON.stringify(p, null, 2)}
                    </pre>
                  ))}
                </div>
              )}

              {trace.hypotheses?.length > 0 && (
                <div>
                  <div className="text-xs uppercase tracking-wide text-gray-500 font-semibold mb-2">Hypotheses</div>
                  {trace.hypotheses.map((h, i) => (
                    <div key={i} className="text-xs text-gray-300 py-1 border-b border-dark-border last:border-0">{h}</div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
""", encoding="utf-8")

# ── DispositionControls.jsx ───────────────────────────────────────────────────
(COMPONENTS / "DispositionControls.jsx").write_text(r"""import { useState } from 'react';
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
""", encoding="utf-8")

print("AgentProposalPanel, AgentTraceDrawer, DispositionControls written successfully.")
