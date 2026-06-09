const BG = [
  'bg-blue-500', 'bg-emerald-500', 'bg-violet-500', 'bg-orange-500',
  'bg-teal-500', 'bg-rose-500', 'bg-cyan-600', 'bg-indigo-500',
];

function hashStr(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h) % BG.length;
}

export default function OfficerAvatar({ officerId, name, size = 'sm' }) {
  const initials = (name || '??')
    .split(' ')
    .slice(0, 2)
    .map(w => w[0] || '')
    .join('')
    .toUpperCase() || '?';
  const key = name || (officerId != null ? String(officerId) : '?');
  const bg = BG[hashStr(key)];
  const sz = size === 'sm' ? 'w-7 h-7 text-[11px]' : 'w-9 h-9 text-sm';
  return (
    <span
      title={name || `Officer #${officerId}`}
      className={`${bg} ${sz} rounded-full flex items-center justify-center font-semibold text-white shrink-0 ring-2 ring-white shadow-sm`}
    >
      {initials}
    </span>
  );
}
