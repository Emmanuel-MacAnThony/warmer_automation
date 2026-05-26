import { useTheme } from '@/shared/hooks/useTheme'
import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'

interface LayoutProps {
  children: React.ReactNode
}

export function Layout({ children }: LayoutProps) {
  const { theme, toggle } = useTheme()

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0">
        <TopBar theme={theme} onThemeToggle={toggle} />
        <main className="flex-1 h-0 overflow-y-auto bg-grid">
          {children}
        </main>
      </div>
    </div>
  )
}
