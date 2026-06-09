
export default function ErrorMessage({ message, onRetry }) {
  return (
    <div className="flex flex-col items-start gap-2 bg-red-900/30 border border-red-700 rounded p-3">
      <p className="text-red-300 text-sm">⚠ {message || 'An error occurred'}</p>
      {onRetry && (
        <button onClick={onRetry} className="text-xs text-red-400 hover:text-red-200 underline">
          Retry
        </button>
      )}
    </div>
  )
}
