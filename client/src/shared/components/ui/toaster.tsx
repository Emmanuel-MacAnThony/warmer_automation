import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { CheckCircle, XCircle, Info, AlertTriangle, X } from 'lucide-react'
import { _subscribe, type ToastItem, type ToastType } from '@/shared/lib/toast'
import { cn } from '@/shared/lib/utils'

const DURATION = 4500

const icons: Record<ToastType, React.ReactNode> = {
  success: <CheckCircle size={16} />,
  error:   <XCircle    size={16} />,
  info:    <Info        size={16} />,
  warning: <AlertTriangle size={16} />,
}

// Dark background + light text per type. The /85 alpha keeps the panel readable
// against any underlying content; the lighter text colour gives high contrast
// against that dark fill. (The previous `bg-*-300/80 text-*-300` was light-on-
// light — the text disappeared into the background.)
const styles: Record<ToastType, string> = {
  success: 'border-teal-400/40    bg-teal-950/85    text-teal-100',
  error:   'border-red-500/40     bg-red-950/85     text-red-100',
  info:    'border-blue-500/40    bg-blue-950/85    text-blue-100',
  warning: 'border-yellow-500/40  bg-yellow-950/85  text-yellow-100',
}

function ToastCard({ item, onDismiss }: { item: ToastItem; onDismiss: () => void }) {
  useEffect(() => {
    const t = setTimeout(onDismiss, DURATION)
    return () => clearTimeout(t)
  }, [onDismiss])

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 24, scale: 0.95 }}
      animate={{ opacity: 1, y: 0,  scale: 1 }}
      exit={{    opacity: 0, y: 8,  scale: 0.95 }}
      transition={{ duration: 0.2, ease: [0.4, 0, 0.2, 1] }}
      className={cn(
        'flex items-start gap-2.5 px-4 py-3 rounded-lg border shadow-lg backdrop-blur-sm font-mono text-sm max-w-sm pointer-events-auto',
        styles[item.type]
      )}
    >
      <span className="shrink-0 pt-0.5">{icons[item.type]}</span>
      <span className="flex-1 leading-snug">{item.message}</span>
      <button onClick={onDismiss} className="shrink-0 opacity-60 hover:opacity-100 transition-opacity pt-0.5">
        <X size={14} />
      </button>
    </motion.div>
  )
}

export function Toaster() {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  useEffect(() => {
    return _subscribe(item => {
      setToasts(prev => [...prev, item])
    })
  }, [])

  const dismiss = (id: string) => setToasts(prev => prev.filter(t => t.id !== id))

  return (
    <div className="fixed bottom-4 right-4 z-[9999] flex flex-col gap-2 pointer-events-none">
      <AnimatePresence mode="popLayout">
        {toasts.map(t => (
          <ToastCard key={t.id} item={t} onDismiss={() => dismiss(t.id)} />
        ))}
      </AnimatePresence>
    </div>
  )
}
