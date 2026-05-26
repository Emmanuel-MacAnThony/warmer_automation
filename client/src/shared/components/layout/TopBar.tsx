import { WifiOff } from 'lucide-react'
import { useEffect, useState } from 'react'
// import { Button } from '@/shared/components/ui/button'  // re-enable with theme toggle below
import { api } from '@/shared/api/client'

interface TopBarProps {
  theme: 'dark' | 'light'
  onThemeToggle: () => void
}

export function TopBar(_props: TopBarProps) {
  const [online, setOnline] = useState<boolean | null>(null)

  useEffect(() => {
    let cancelled = false
    const check = async () => {
      try {
        await api.health()
        if (!cancelled) setOnline(true)
      } catch {
        if (!cancelled) setOnline(false)
      }
    }
    void check()
    const id = setInterval(() => void check(), 30_000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  return (
    <header className="flex h-12 items-center justify-end px-5 border-b border-border/60 bg-background/80 backdrop-blur-sm shrink-0 gap-2">
      {/* Backend status */}
      <span
        className={`flex items-center gap-1.5 font-mono text-xs px-2.5 py-1 rounded-md border transition-colors ${
          online === null
            ? 'border-border/50 text-muted-foreground/50'
            : online
            ? 'border-emerald-500/20 text-emerald-400/80 bg-emerald-500/5'
            : 'border-red-500/20 text-red-400/80 bg-red-500/5'
        }`}
      >
        {online === null ? (
          <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/40" />
        ) : online ? (
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
        ) : (
          <WifiOff size={11} />
        )}
        {online === null ? 'checking' : online ? 'connected' : 'offline'}
      </span>

      {/* Theme toggle — disabled while light mode is off
      <Button variant="ghost" size="icon-sm" onClick={onThemeToggle} aria-label="Toggle theme" className="text-muted-foreground/60 hover:text-foreground">
        {theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
      </Button> */}
    </header>
  )
}
