export type ToastType = 'success' | 'error' | 'info' | 'warning'

export interface ToastItem {
  id: string
  type: ToastType
  message: string
}

type Listener = (item: ToastItem) => void
let _listeners: Listener[] = []

export function toast(message: string, type: ToastType = 'info') {
  const item: ToastItem = { id: `${Date.now()}-${Math.random().toString(36).slice(2)}`, type, message }
  _listeners.forEach(l => l(item))
}

export function _subscribe(listener: Listener): () => void {
  _listeners.push(listener)
  return () => { _listeners = _listeners.filter(l => l !== listener) }
}

// Convenience shorthands
toast.success = (msg: string) => toast(msg, 'success')
toast.error   = (msg: string) => toast(msg, 'error')
toast.info    = (msg: string) => toast(msg, 'info')
toast.warn    = (msg: string) => toast(msg, 'warning')
