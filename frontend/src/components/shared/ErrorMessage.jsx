import { AlertTriangle } from 'lucide-react';

export default function ErrorMessage({ message, onRetry }) {
  return (
    <div className="flex items-start gap-2.5 bg-red-50 border border-red-200 rounded-lg p-3">
      <AlertTriangle className="w-5 h-5 text-red-500 shrink-0 mt-0.5" />
      <div>
        <p className="text-red-700 text-sm font-medium">{message || 'An error occurred'}</p>
        {onRetry && (
          <button onClick={onRetry} className="text-xs text-red-600 hover:text-red-800 underline mt-1">
            Retry
          </button>
        )}
      </div>
    </div>
  );
}
