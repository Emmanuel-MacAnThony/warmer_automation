import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Briefcase, CheckCircle, Loader2, XCircle } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api, type Job } from '@/shared/api/client'
import { Card, CardContent } from '@/shared/components/ui/card'
import { StatusBadge } from '@/shared/components/ui/status-badge'
import { useJobConfig } from '@/shared/hooks/useJobConfig'
import { buttonVariants } from '@/shared/components/ui/button'
import { MaskedText } from '@/shared/components/ui/masked-id'

const container = {
  hidden: {},
  show: { transition: { staggerChildren: 0.06 } },
}
const item = {
  hidden: { opacity: 0, y: 10 },
  show:   { opacity: 1, y: 0, transition: { duration: 0.3 } },
}

interface StatCardProps {
  label: string
  value: number
  icon: React.ReactNode
  color: string
}

function StatCard({ label, value, icon, color }: StatCardProps) {
  return (
    <motion.div variants={item}>
      <Card className="hover:-translate-y-0.5 transition-transform duration-200">
        <CardContent className="pt-5 pb-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="font-mono text-[10px] text-muted-foreground/60 mb-2 tracking-widest uppercase">{label}</p>
              <p className={`text-3xl font-bold tabular-nums ${color}`}>{value}</p>
            </div>
            <div className={`p-2 rounded-lg bg-muted/60 border border-border/50 ${color} shrink-0`}>{icon}</div>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  )
}

export function Dashboard() {
  const { config, isConfigured } = useJobConfig()
  const [jobs,    setJobs]    = useState<Job[]>([])
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState<string | null>(null)

  useEffect(() => {
    if (!isConfigured) return
    setLoading(true)
    api.listJobs(config.baseId, config.tableId)
      .then(setJobs)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }, [config.baseId, config.tableId, isConfigured])

  const total      = jobs.length
  const running    = jobs.filter(j => j.status === 'running').length
  const completed  = jobs.filter(j => j.status === 'completed').length
  const failed     = jobs.filter(j => j.status === 'failed').length
  const activeJobs = jobs.filter(j => j.status === 'running' || j.status === 'pending')

  if (!isConfigured) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4 text-center p-8">
        <div className="p-4 rounded-full bg-muted">
          <Briefcase size={28} className="text-muted-foreground" />
        </div>
        <div>
          <p className="font-medium mb-1">No table configured</p>
          <p className="text-sm text-muted-foreground">Set your Airtable base and table ID to get started.</p>
        </div>
        <Link to="/jobs" className={buttonVariants({ variant: 'default', size: 'sm' })}>
          Configure
        </Link>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6 w-full">
      <div>
        <h1 className="text-xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-xs font-mono text-muted-foreground/50 mt-1 flex items-center gap-1.5">
          <MaskedText value={config.baseId} />
          <span>/</span>
          <MaskedText value={config.tableId} />
        </p>
      </div>

      {/* Enrichment stats */}
      <motion.div
        variants={container}
        initial="hidden"
        animate="show"
        className="grid grid-cols-2 lg:grid-cols-4 gap-4"
      >
        <StatCard label="Total Jobs"  value={total}     icon={<Briefcase   size={20} />} color="text-foreground" />
        <StatCard label="Running"     value={running}   icon={<Loader2     size={20} />} color="text-cyan-400" />
        <StatCard label="Completed"   value={completed} icon={<CheckCircle size={20} />} color="text-emerald-400" />
        <StatCard label="Failed"      value={failed}    icon={<XCircle     size={20} />} color="text-red-400" />
      </motion.div>

      {/* Active jobs */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <h2 className="font-mono text-[10px] font-semibold tracking-widest uppercase text-muted-foreground/60">
            Active Jobs
          </h2>
          <div className="flex-1 border-t border-border/40" />
        </div>

        {loading && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground p-4">
            <Loader2 size={14} className="animate-spin" /> Loading…
          </div>
        )}

        {error && <p className="text-sm text-red-400 p-4">{error}</p>}

        {!loading && !error && activeJobs.length === 0 && (
          <Card>
            <CardContent className="py-8 text-center space-y-2">
              <p className="text-sm text-muted-foreground">No active jobs</p>
              <Link to="/jobs" className={buttonVariants({ variant: 'outline', size: 'sm' })}>
                Go to Jobs
              </Link>
            </CardContent>
          </Card>
        )}

        <div className="space-y-2">
          {activeJobs.map(job => (
            <motion.div
              key={job.id}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25 }}
            >
              <Link to="/jobs" className="block group">
                <Card className="transition-all duration-150 group-hover:border-border group-hover:bg-muted/20 cursor-pointer">
                  <CardContent className="py-3 px-4">
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-xs text-muted-foreground/50 shrink-0">#{job.id}</span>
                      <StatusBadge status={job.status} />
                      {job.total_records != null && (
                        <span className="text-xs font-mono text-muted-foreground/60">
                          {job.total_records.toLocaleString()} records
                        </span>
                      )}
                      <span className="ml-auto text-[11px] font-mono text-muted-foreground/40 shrink-0">
                        {new Date(job.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  )
}
