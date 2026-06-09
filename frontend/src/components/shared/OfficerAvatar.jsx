
const BG_COLORS = [
  'bg-blue-700', 'bg-green-700', 'bg-purple-700', 'bg-orange-700',
  'bg-teal-700', 'bg-rose-700', 'bg-cyan-700', 'bg-indigo-700',
]

function hash(id) {
  return Math.abs((id || 0) * 2654435761) % BG_COLORS.length
}

export default function OfficerAvatar({ officerId, name, size = 'sm' }) {
  const initials = (name || '??')
    .split(' ')
    .slice(0, 2)
    .map(w => w[0] || '')
    .join('')
    .toUpperCase()
  const bg = BG_COLORS[hash(officerId)]
  const sz = size === 'sm' ? 'w-7 h-7 text-xs' : 'w-9 h-9 text-sm'
  return (
    <span
      title={name || `Officer #${officerId}`}
      className={`${bg} ${sz} rounded-full flex items-center justify-center font-semibold text-white shrink-0`}
    >
      {initials || '?'}
    </span>
  )
}
