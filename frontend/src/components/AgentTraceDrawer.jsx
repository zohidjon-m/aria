import { useState, useEffect } from 'react';
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
    // eslint-disable-next-line react-hooks/set-state-in-effect
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
