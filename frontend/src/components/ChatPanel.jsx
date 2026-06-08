import React, { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import {
  Send,
  Bot,
  Sparkles,
  Loader2,
  Search,
  Trash2,
  Square,
} from 'lucide-react';
import HealthIndicator from './HealthIndicator';
import ContextBanner from './ContextBanner';
import { useHealth } from '../hooks/useHealth';

const QUICK_ACTIONS = [
  'Triage top alert',
  'High risk customers',
  'Open cases summary',
  "This week's activity",
];

const TOOL_LABELS = {
  query_database: 'Querying database',
  analyze_customer: 'Analyzing customer',
  triage_alert: 'Triaging alert',
  draft_case_narrative: 'Drafting narrative',
  draft_sar_report: 'Drafting SAR',
};

const formatTime = (ts) =>
  ts
    ? new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : '';

const ChatPanel = ({
  messages,
  isLoading,
  onSendMessage,
  onStop,
  onClear,
  activeContext,
  onClearContext,
}) => {
  const [input, setInput] = useState('');
  const endRef = useRef(null);
  const health = useHealth();

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = (e) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;
    onSendMessage(input);
    setInput('');
  };

  const lastMsg = messages[messages.length - 1];
  const isStreaming = isLoading && lastMsg?.role === 'assistant';

  return (
    <div className="relative flex h-full flex-col overflow-hidden border-l border-dark-border bg-dark-panel shadow-xl">
      {/* Glow effect */}
      <div className="pointer-events-none absolute right-[-100px] top-[-100px] h-[300px] w-[300px] rounded-full bg-brand-accent/20 blur-[100px]" />

      {/* Header */}
      <div className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-dark-border bg-dark-panel/90 p-5 shadow-sm backdrop-blur-md">
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-brand-primary p-2 shadow-lg">
            <Bot className="relative z-10 text-white" size={24} />
          </div>
          <div>
            <h2 className="text-xl font-bold tracking-tight text-white">ARIA</h2>
            <p className="text-xs font-medium uppercase tracking-wider text-brand-primary">
              AML Risk Intelligence Agent
            </p>
          </div>
        </div>
        <div className="flex flex-col items-end gap-2">
          <HealthIndicator status={health} />
          {messages.length > 0 && (
            <button
              onClick={onClear}
              title="Clear conversation"
              className="flex items-center gap-1 rounded px-2 py-0.5 text-xs text-slate-500 transition hover:bg-slate-800 hover:text-slate-200"
            >
              <Trash2 size={12} /> Clear
            </button>
          )}
        </div>
      </div>

      <ContextBanner context={activeContext} onClear={onClearContext} />

      {/* Messages */}
      <div className="flex-1 space-y-6 overflow-y-auto p-4">
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center space-y-6 text-slate-400">
            <Bot size={64} className="mb-2 text-slate-600 opacity-50" />
            <h3 className="text-2xl font-semibold text-slate-300">
              How can I help you investigate?
            </h3>
            <div className="flex max-w-md flex-wrap justify-center gap-2">
              {QUICK_ACTIONS.map((action) => (
                <button
                  key={action}
                  onClick={() => onSendMessage(action)}
                  className="rounded-full border border-slate-700 bg-slate-800 px-4 py-2 text-sm transition hover:bg-slate-700 hover:text-white"
                >
                  <Sparkles size={14} className="mr-2 inline text-brand-accent" />
                  {action}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((msg, i) => {
            const isLast = i === messages.length - 1;
            const showCursor = isStreaming && isLast && msg.role === 'assistant';
            return (
              <div
                key={i}
                className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : ''}`}
              >
                {msg.role === 'assistant' && (
                  <div className="mt-1 flex-shrink-0">
                    <div className="rounded-full border border-brand-accent/30 bg-brand-accent bg-opacity-20 p-1.5 shadow-md">
                      <Bot size={18} className="text-brand-accent" />
                    </div>
                  </div>
                )}

                <div className="flex max-w-[85%] flex-col">
                  <div
                    className={`rounded-2xl p-4 ${
                      msg.role === 'user'
                        ? 'ml-auto rounded-tr-sm bg-brand-primary text-white shadow-md'
                        : 'rounded-tl-sm border border-slate-700 bg-slate-800 text-slate-200 shadow-sm'
                    }`}
                  >
                    {msg.role === 'user' ? (
                      <p className="whitespace-pre-wrap text-[15px] leading-relaxed">
                        {msg.content}
                      </p>
                    ) : (
                      <div className="prose prose-invert max-w-none text-[15px] leading-relaxed prose-p:my-1 prose-a:text-brand-primary">
                        {msg.tool_calls && msg.tool_calls.length > 0 && (
                          <div className="mb-3 flex flex-wrap gap-2">
                            {msg.tool_calls.map((tc, idx) => (
                              <div
                                key={idx}
                                className="flex items-center gap-1.5 rounded-md border border-slate-600/50 bg-slate-700/50 px-2.5 py-1 text-xs text-slate-300"
                              >
                                {tc === 'query_database' ? (
                                  <Search size={12} />
                                ) : (
                                  <Sparkles size={12} />
                                )}
                                <span className="font-mono text-[10px] uppercase tracking-wider">
                                  {TOOL_LABELS[tc] || tc.replace(/_/g, ' ')}
                                </span>
                              </div>
                            ))}
                          </div>
                        )}
                        <ReactMarkdown>{msg.content}</ReactMarkdown>
                        {showCursor && (
                          <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-brand-primary align-middle" />
                        )}
                      </div>
                    )}
                  </div>
                  {msg.timestamp && (
                    <span
                      className={`mt-1 text-[10px] text-slate-500 ${
                        msg.role === 'user' ? 'text-right' : ''
                      }`}
                    >
                      {formatTime(msg.timestamp)}
                    </span>
                  )}
                </div>
              </div>
            );
          })
        )}

        {isLoading && lastMsg?.role === 'assistant' && !lastMsg.content && (
          <div className="flex items-center gap-2 p-2 text-slate-400">
            <Loader2 className="animate-spin text-brand-primary" size={16} />
            <span className="animate-pulse text-sm font-medium">Analyzing...</span>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {/* Input area */}
      <div className="border-t border-dark-border bg-dark-panel/90 p-4 backdrop-blur-sm">
        <form onSubmit={handleSend} className="group relative">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={isLoading}
            placeholder="Ask ARIA to investigate..."
            className="w-full rounded-xl border border-slate-700 bg-slate-900/50 px-5 py-4 pr-14 text-white placeholder-slate-500 shadow-inner transition focus:border-brand-primary/50 focus:outline-none focus:ring-2 focus:ring-brand-primary/50 disabled:opacity-50"
          />
          {isLoading ? (
            <button
              type="button"
              onClick={onStop}
              title="Stop generating"
              className="absolute bottom-2 right-2 top-2 flex items-center justify-center rounded-lg bg-red-600 px-3 text-white transition hover:bg-red-500"
            >
              <Square size={18} />
            </button>
          ) : (
            <button
              type="submit"
              disabled={!input.trim()}
              className="absolute bottom-2 right-2 top-2 flex items-center justify-center rounded-lg bg-brand-primary px-3 text-white transition hover:bg-blue-600 disabled:bg-slate-700 disabled:opacity-50"
            >
              <Send size={20} />
            </button>
          )}
        </form>
      </div>
    </div>
  );
};

export default ChatPanel;
