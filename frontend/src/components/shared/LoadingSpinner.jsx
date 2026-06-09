import Spinner from '../ui/Spinner';

export default function LoadingSpinner({ size = 'md', label }) {
  return (
    <div className="py-6">
      <Spinner size={size === 'md' ? 'lg' : size} label={label} />
    </div>
  );
}
