import { useState, useEffect } from 'react';
import { X, Brain, Wrench, Eye, GitBranch, Flag, CheckCircle2 } from 'lucide-react';
import { getAgentTrace } from '../api/client';
import Spinner from './ui/Spinner';

const STEP_META = {
  planning: { icon: Brain, tone: 'blue' },
  tool_executed: { icon: Wrench, tone: 'violet' },
  observed: { icon: Wrench, tone: 'violet' },
  observing: { icon: Eye, tone: 'blue' },
  revising: { icon: GitBranch, tone: 'amber' },
  proposed: { icon: CheckCircle2, tone: 'emerald' },
  failed_safe: { icon: Flag, tone: 'red' },
};

function toneClass(tone) {
  return {
    blue: 'bg-blue-50 text-blue-600',
    violet: 'bg-violet-50 text-violet-600',
    amber: 'bg-amber-50 text-amber-600',
    emerald: 'bg-emerald-50 text-emerald-600',
    red: 'bg-red-50 text-red-600',
    slate: 'bg-slate-100 text-slate-500',
  }[tone];
}

function StepRow({ step }) {
  const [open, setOpen] = useState(false);
  const inner = step.step || {};
  const type = step.type || step.status || inner.status;
  const thought = step.thought || inner.thought;
  const hypothesisBefore = step.hypothesis_before || inner.hypothesis_before;
  const hypothesisAfter = step.hypothesis_after || step.hypothesis || inner.hypothesis_after || inner.hypothesis;
  const toolName = step.tool_name || inner.tool_name;
  const toolArgs = step.tool_args || inner.tool_args;
  const observation = step.observation || inner.observation;
  const meta = STEP_META[type] || { icon: Brain, tone: 'slate' };
  const Icon = meta.icon;

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <button onClick={() => setOpen(o => !o)} className="w-full flex items-start gap-2.5 p-3 text-left hover:bg-surface-2 transition-colors">
        <span className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${toneClass(meta.tone)}`}>
          <Icon className="w-4 h-4" />
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-xs font-semibold text-ink uppercase tracking-wide">{(type || 'step').replace(/_/g, ' ')}</div>
          {thought && <div className="text-sm text-ink-muted truncate mt-0.5">{thought}</div>}
        </div>
        <span className="text-ink-subtle text-xs mt-1">{open ? 'Close' : 'Open'}</span>
      </button>
      {open && (
        <div className="px-3 pb-3 pl-12 text-sm space-y-1.5">
          {thought && <p className="text-ink-muted leading-relaxed">{thought}</p>}
          {hypothesisBefore && <p className="text-xs"><span className="text-ink-subtle">Hypothesis before: </span><span className="text-ink-muted">{hypothesisBefore}</span></p>}
          {hypothesisAfter && <p className="text-xs"><span className="text-ink-subtle">Hypothesis after: </span><span className="text-amber-700">{hypothesisAfter}</span></p>}
          {toolName && <p className="text-xs"><span className="text-ink-subtle">Tool: </span><span className="text-violet-700 font-mono">{toolName}</span></p>}
          {toolArgs && <pre className="bg-surface-2 rounded-lg p-2 overflow-x-auto text-xs text-ink-muted font-mono">{JSON.stringify(toolArgs, null, 2)}</pre>}
          {observation && (
            <div className="bg-surface-2 rounded-lg p-2 text-xs text-ink-muted">
              {typeof observation === 'string' ? observation : JSON.stringify(observation)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div>
      <p className="text-xs font-semibold text-ink-subtle uppercase tracking-wide mb-2">{title}</p>
      <div className="space-y-2">{children}</div>
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
    getAgentTrace(runId).then(setTrace).catch(e => setError(e.response?.data?.detail || e.message)).finally(() => setLoading(false));
  }, [isOpen, runId]);

  useEffect(() => {
    function onKey(e) { if (e.key === 'Escape' && isOpen) onClose(); }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="fixed inset-0 bg-slate-900/30 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-2xl bg-canvas border-l border-border flex flex-col h-full overflow-hidden shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border bg-surface shrink-0">
          <div>
            <div className="text-sm font-semibold text-ink">Agent Reasoning Trace</div>
            {runId && <div className="text-xs text-ink-subtle font-mono">{runId}</div>}
          </div>
          <button onClick={onClose} className="text-ink-subtle hover:text-ink p-1 rounded-lg hover:bg-surface-2"><X className="w-5 h-5" /></button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {loading && <Spinner size="lg" label="Loading trace..." />}
          {error && <p className="text-sm text-red-600">{error}</p>}
          {trace && (
            <>
              {trace.runtime_events?.length > 0 && (
                <Section title={`Runtime Events (${trace.runtime_events.length})`}>
                  {trace.runtime_events.map((event, i) => (
                    <pre key={i} className="bg-surface border border-border rounded-lg p-2 overflow-x-auto text-xs text-ink-muted font-mono">{JSON.stringify(event, null, 2)}</pre>
                  ))}
                </Section>
              )}
              {trace.agent_steps?.length > 0 && (
                <Section title={`Agent Steps (${trace.agent_steps.length})`}>
                  {trace.agent_steps.map((s, i) => <StepRow key={i} step={s} />)}
                </Section>
              )}
              {trace.tool_calls?.length > 0 && (
                <Section title={`Tool Calls (${trace.tool_calls.length})`}>
                  {trace.tool_calls.map((t, i) => (
                    <div key={i} className="border border-border rounded-lg p-3">
                      <span className="text-xs font-mono text-violet-700 font-medium flex items-center gap-1.5"><Wrench className="w-3.5 h-3.5" /> {t.tool_name}</span>
                      <pre className="bg-surface-2 rounded-lg p-2 mt-2 overflow-x-auto text-xs text-ink-muted font-mono">{JSON.stringify(t.tool_args || t.args || t, null, 2)}</pre>
                    </div>
                  ))}
                </Section>
              )}
              {trace.baseline_snapshots?.length > 0 && (
                <Section title="Baseline Snapshots">
                  {trace.baseline_snapshots.map((s, i) => <pre key={i} className="bg-surface border border-border rounded-lg p-2 overflow-x-auto text-xs text-ink-muted font-mono">{JSON.stringify(s, null, 2)}</pre>)}
                </Section>
              )}
              {trace.money_flow_paths?.length > 0 && (
                <Section title="Money Flow Paths">
                  {trace.money_flow_paths.map((p, i) => <pre key={i} className="bg-surface border border-border rounded-lg p-2 overflow-x-auto text-xs text-ink-muted font-mono">{JSON.stringify(p, null, 2)}</pre>)}
                </Section>
              )}
              {trace.hypotheses?.length > 0 && (
                <Section title="Hypotheses">
                  {trace.hypotheses.map((h, i) => <div key={i} className="text-sm text-ink-muted border border-border rounded-lg p-2">{typeof h === 'string' ? h : h.hypothesis || JSON.stringify(h)}</div>)}
                </Section>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
