import { useCallback, useRef, useState } from 'react';
import { API_BASE_URL } from '../api/client';

export function useChat({ onError } = {}) {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const abortRef = useRef(null);

  const sendMessage = useCallback(
    async (message, context) => {
      const userMsg = { role: 'user', content: message, timestamp: Date.now() };

      // Capture history snapshot BEFORE adding the new user message
      let historySnapshot;
      setMessages((prev) => {
        historySnapshot = prev;
        return [
          ...prev,
          userMsg,
          { role: 'assistant', content: '', tool_calls: [], timestamp: Date.now() },
        ];
      });

      setIsLoading(true);
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const response = await fetch(`${API_BASE_URL}/api/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message, history: historySnapshot, context }),
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error(`Chat API returned ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            const dataStr = line.slice(6).trim();
            if (!dataStr) continue;

            let data;
            try {
              data = JSON.parse(dataStr);
            } catch (e) {
              console.error('Parse error', e);
              continue;
            }

            setMessages((prev) => {
              const last = prev[prev.length - 1];
              if (!last || last.role !== 'assistant') return prev;

              let updatedLast = last;
              if (data.type === 'content_block_delta') {
                updatedLast = { ...last, content: last.content + data.delta.text };
              } else if (data.type === 'tool_call') {
                updatedLast = {
                  ...last,
                  tool_calls: [...(last.tool_calls || []), data.tool_call.name],
                };
              } else {
                return prev;
              }

              return [...prev.slice(0, -1), updatedLast];
            });
          }
        }
      } catch (error) {
        if (error.name === 'AbortError') {
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (!last || last.role !== 'assistant') return prev;
            return [
              ...prev.slice(0, -1),
              { ...last, content: last.content + '\n\n_[Stopped by user]_' },
            ];
          });
        } else {
          console.error(error);
          onError?.(error.message || 'Failed to reach ARIA');
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (!last || last.role !== 'assistant') return prev;
            return [
              ...prev.slice(0, -1),
              {
                ...last,
                content:
                  last.content ||
                  '🚨 **Error:** Could not connect to ARIA. Check that the backend is running.',
              },
            ];
          });
        }
      } finally {
        setIsLoading(false);
        abortRef.current = null;
      }
    },
    [onError]
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const clear = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
  }, []);

  return { messages, isLoading, sendMessage, stop, clear };
}
