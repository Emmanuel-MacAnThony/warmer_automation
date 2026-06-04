import { motion } from 'framer-motion'

export type JobStatus = 'pending' | 'running' | 'paused' | 'completed' | 'failed'

const statusConfig: Record<JobStatus, { dot: string; label: string; bg: string; text: string }> = {
  pending:   { dot: 'bg-muted-foreground',  label: 'Pending',   bg: 'bg-muted',          text: 'text-muted-foreground' },
  running:   { dot: 'bg-cyan-500',           label: 'Running',   bg: 'bg-cyan-500/10',    text: 'text-cyan-400' },
  paused:    { dot: 'bg-amber-500',         label: 'Paused',    bg: 'bg-amber-500/10',   text: 'text-amber-400' },
  completed: { dot: 'bg-teal-300',       label: 'Completed', bg: 'bg-teal-300/10', text: 'text-teal-300' },
  failed:    { dot: 'bg-red-500',           label: 'Failed',    bg: 'bg-red-500/10',     text: 'text-red-400' },
}

export function StatusBadge({ status }: { status: JobStatus }) {
  const c = statusConfig[status]
  return (
    <motion.span
      layout
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium ${c.bg} ${c.text}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${c.dot} ${status === 'running' ? 'animate-pulse' : ''}`} />
      {c.label}
    </motion.span>
  )
}
