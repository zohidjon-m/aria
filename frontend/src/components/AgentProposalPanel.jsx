import { ArrowRight, AlertTriangle, Cpu } from 'lucide-react';
import HumanReviewBanner from './shared/HumanReviewBanner';
import ConfidenceMeter from './shared/ConfidenceMeter';
import Badge from './ui/Badge';

const RECOMMENDATION = {
  escalate: { label: 'Escalate', tone: 'red' },
  needs_investigation: { label: 'Needs Investigation', tone: 'amber' },
  investigate: { label: 'Needs Investigation', tone: 'amber' },
  likely_false_positive: { label: 'Likely False Positive', tone: 'emerald' },
};

function formatRef(ref) {
  if (typeof ref === 'string') return ref;
  if (ref && typeof ref === 'object') {
    const base = [ref.table, ref.key].filter(Boolean).join('#');
    return base || JSON.stringify(ref);
  }
  return String(ref);
}

function SourceRefChip({ refValue }) {
  return (
    <span className="font-mono text-[11px] bg-surface-2 border border-border rounded px-1.5 py-0.5 text-ink-muted mr-1 mb-1 inline-block">
      {formatRef(refValue)}
    </span>
  );
}

function RuntimeDetail({ label, value }) {
  if (value === undefined || value === null || value === '') return null;
  return (
    <div className="flex gap-2 text-xs py-0.5">
      <span className="text-ink-subtle w-28 shrink-0">{label}</span>
      <span className="text-ink-muted font-mono break-all">{String(value)}</span>
    </div>
  );
}

export default function AgentProposalPanel({ run, onViewTrace }) {
  if (!run) return null;

  const output = run.output || {};
  const validation = run.validation || {};
  const details = output.details || {};
  const phase1Proposal = details.phase1_proposal || {};
  const reactRuntime = details.react_runtime || {};
  const runtimeVersion = details.runtime_version || {};
  const plannerMetadata = reactRuntime.planner_metadata || {};
  const runtimeEvents = phase1Proposal.runtime_events || reactRuntime.events || [];
  const terminalState = phase1Proposal.terminal_state || reactRuntime.terminal_state;
  const stopReason = phase1Proposal.stop_reason || reactRuntime.stop_reason;
  const modelVersion = phase1Proposal.model_version || runtimeVersion.model_id || plannerMetadata.model_id;
  const promptVersion = phase1Proposal.prompt_version || runtimeVersion.prompt_version || plannerMetadata.prompt_version;
  const toolRegistryVersion = phase1Proposal.tool_registry_version || runtimeVersion.tool_registry_version;
  const toolCallCount = phase1Proposal.tool_calls?.length ?? reactRuntime.tool_call_count;

  const recommendation = output.recommendation || output.action;
  const recMeta = RECOMMENDATION[recommendation] || { label: recommendation || 'Unknown', tone: 'slate' };

  const rawConfidence = output.confidence_score ?? output.confidence ?? null;
  const confidence = rawConfidence === null ? null : Math.round(rawConfidence <= 1 ? rawConfidence * 100 : rawConfidence);
  const claims = output.claims || output.factual_claims || [];
  const limitations = output.limitations || [];
  const validationStatus = validation.status || 'not_run';
  const unsupportedCount = validation.unsupported_count ?? validation.unsupported_claim_count ?? 0;
  const valTone = validationStatus === 'passed' ? 'emerald' : validationStatus === 'failed' ? 'red' : 'slate';

  const hasRuntime = terminalState || stopReason || modelVersion || promptVersion || toolRegistryVersion || runtimeEvents.length || toolCallCount !== undefined;

  return (
    <div className="space-y-3">
      <HumanReviewBanner />

      <div className="flex items-center justify-between gap-2">
        <Badge tone={recMeta.tone} dot className="text-xs px-2.5 py-1">{recMeta.label}</Badge>
        <Badge tone={valTone}>Validation: {validationStatus}</Badge>
      </div>

      {confidence !== null && (
        <div>
          <div className="flex items-center justify-between text-xs text-ink-subtle mb-1">
            <span>Confidence</span>
            <span className="tnum">{confidence}/100</span>
          </div>
          <ConfidenceMeter value={confidence} />
        </div>
      )}

      {output.summary && (
        <p className="text-sm text-ink-muted bg-surface-2 rounded-lg p-3 leading-relaxed">{output.summary}</p>
      )}

      {claims.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-ink-subtle uppercase tracking-wide mb-1.5">Grounded Claims</p>
          <div className="space-y-2">
            {claims.map((c, i) => {
              const refs = c.source_refs || c.evidence_refs || [];
              return (
                <div key={i} className="border-l-2 border-border pl-3">
                  <p className="text-sm text-ink mb-1">{c.statement || (typeof c === 'string' ? c : '')}</p>
                  {refs.length > 0 && <div className="flex flex-wrap">{refs.map((r, j) => <SourceRefChip key={j} refValue={r} />)}</div>}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {limitations.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-ink-subtle uppercase tracking-wide mb-1.5">Limitations</p>
          <div className="space-y-1">
            {limitations.map((l, i) => (
              <div key={i} className="flex gap-1.5 text-xs text-amber-700">
                <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                <span>{typeof l === 'string' ? l : l.description || JSON.stringify(l)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {unsupportedCount > 0 && (
        <p className="text-xs text-amber-700 flex items-center gap-1">
          <AlertTriangle className="w-3.5 h-3.5" /> {unsupportedCount} unsupported claim(s) flagged by validation.
        </p>
      )}

      {hasRuntime && (
        <details className="bg-surface-2 rounded-lg p-3">
          <summary className="text-xs font-semibold text-ink-subtle uppercase tracking-wide cursor-pointer flex items-center gap-1.5">
            <Cpu className="w-3.5 h-3.5" /> Runtime
          </summary>
          <div className="mt-2">
            <RuntimeDetail label="Terminal" value={terminalState} />
            <RuntimeDetail label="Stop Reason" value={stopReason} />
            <RuntimeDetail label="Model" value={modelVersion} />
            <RuntimeDetail label="Prompt" value={promptVersion} />
            <RuntimeDetail label="Tool Registry" value={toolRegistryVersion} />
            <RuntimeDetail label="Events" value={runtimeEvents.length || undefined} />
            <RuntimeDetail label="Tool Calls" value={toolCallCount} />
          </div>
        </details>
      )}

      <button onClick={onViewTrace} className="text-sm font-medium text-brand hover:underline inline-flex items-center gap-1">
        View full trace <ArrowRight className="w-4 h-4" />
      </button>
    </div>
  );
}
