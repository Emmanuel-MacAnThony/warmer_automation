import { Dialog } from '@base-ui/react/dialog'
import { X } from 'lucide-react'
import { cn } from '@/shared/lib/utils'
import { Button } from './button'

/* ── Confirm dialog ──────────────────────────────────────────────────────── */

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = 'Confirm',
  confirmVariant = 'destructive',
  onConfirm,
  loading,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: React.ReactNode
  description?: React.ReactNode
  confirmLabel?: string
  confirmVariant?: 'destructive' | 'default'
  onConfirm: () => void | Promise<void>
  loading?: boolean
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
      <Dialog.Backdrop className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm transition-opacity duration-200 data-starting-style:opacity-0 data-ending-style:opacity-0" />
      <Dialog.Popup className={cn(
        'fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2',
        'rounded-2xl border bg-background shadow-2xl outline-none',
        'transition-[opacity,transform] duration-200',
        'data-starting-style:opacity-0 data-starting-style:scale-95',
        'data-ending-style:opacity-0 data-ending-style:scale-95',
      )}>
        <div className="p-7 space-y-5">
          {/* Header */}
          <div className="flex items-start justify-between gap-4">
            <Dialog.Title className="text-base font-semibold leading-snug">
              {title}
            </Dialog.Title>
            <Dialog.Close
              className="h-7 w-7 rounded-lg flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-colors shrink-0 -mt-0.5"
              aria-label="Close"
            >
              <X size={15} />
            </Dialog.Close>
          </div>

          {description && (
            <Dialog.Description className="text-sm text-muted-foreground leading-relaxed">
              {description}
            </Dialog.Description>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-2.5 pt-1">
            <Dialog.Close
              className={cn(
                'inline-flex items-center justify-center rounded-lg border border-border bg-background px-3 h-7 text-[0.8rem] font-medium',
                'hover:bg-muted transition-colors disabled:opacity-50 disabled:pointer-events-none',
              )}
              disabled={loading}
            >
              Cancel
            </Dialog.Close>
            <Button
              variant={confirmVariant}
              size="sm"
              onClick={onConfirm}
              disabled={loading}
              className="gap-1.5"
            >
              {loading && (
                <svg className="animate-spin size-3.5" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                </svg>
              )}
              {confirmLabel}
            </Button>
          </div>
        </div>
      </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
