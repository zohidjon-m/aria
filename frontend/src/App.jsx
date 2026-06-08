import React, { useCallback, useState } from 'react';
import DataPanel from './components/DataPanel';
import ChatPanel from './components/ChatPanel';
import Toasts from './components/Toasts';
import { useChat } from './hooks/useChat';
import { useToast } from './hooks/useToast';

function App() {
  const [activeContext, setActiveContext] = useState(null);
  const { toasts, push, dismiss } = useToast();

  const handleError = useCallback((msg) => push(msg, { type: 'error' }), [push]);

  const { messages, isLoading, sendMessage, stop, clear } = useChat({
    onError: handleError,
  });

  const handleSendMessage = (msg) => {
    let contextDict = null;
    if (activeContext) {
      contextDict = {};
      if (activeContext.type === 'customer') contextDict.customer_id = activeContext.data.customer_id;
      if (activeContext.type === 'alert') contextDict.alert_id = activeContext.data.alert_id;
      if (activeContext.type === 'case') contextDict.case_id = activeContext.data.case_id;
    }
    sendMessage(msg, contextDict);
  };

  return (
    <div className="flex h-screen w-full overflow-hidden bg-dark-bg font-sans text-white">
      <div className="h-full w-[60%] shrink-0">
        <DataPanel
          activeContext={activeContext}
          onContextSelect={setActiveContext}
          onPreFillChat={handleSendMessage}
          onError={handleError}
        />
      </div>
      <div className="h-full w-[40%] shrink-0">
        <ChatPanel
          messages={messages}
          isLoading={isLoading}
          onSendMessage={handleSendMessage}
          onStop={stop}
          onClear={clear}
          activeContext={activeContext}
          onClearContext={() => setActiveContext(null)}
        />
      </div>
      <Toasts toasts={toasts} onDismiss={dismiss} />
    </div>
  );
}

export default App;
