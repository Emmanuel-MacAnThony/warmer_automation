import { useState } from 'react'

export interface JobConfig {
  baseId: string
  tableId: string
}

const STORAGE_KEY = 'job-config'

export function useJobConfig() {
  const [config, setConfig] = useState<JobConfig>(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    return stored ? (JSON.parse(stored) as JobConfig) : { baseId: '', tableId: '' }
  })

  const updateConfig = (next: JobConfig) => {
    setConfig(next)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  }

  const isConfigured = Boolean(config.baseId && config.tableId)

  return { config, updateConfig, isConfigured }
}
