import { useState } from 'react'
import { Eye, EyeOff } from 'lucide-react'
import { cn } from '@/shared/lib/utils'

function mask(value: string): string {
  if (!value) return ''
  // Keep first 3 chars (e.g. "app" or "tbl") + bullet chars
  const prefix = value.slice(0, 3)
  return prefix + '•'.repeat(Math.max(4, value.length - 3))
}

/* ── Inline display (Dashboard header etc.) ─────────────────────────── */
interface MaskedTextProps {
  value: string
  className?: string
}

export function MaskedText({ value, className }: MaskedTextProps) {
  const [show, setShow] = useState(false)
  return (
    <span className={cn('inline-flex items-center gap-1.5', className)}>
      <span className="font-mono">{show ? value : mask(value)}</span>
      <button
        onClick={() => setShow(s => !s)}
        className="text-muted-foreground hover:text-foreground transition-colors"
        tabIndex={-1}
        aria-label={show ? 'Hide ID' : 'Show ID'}
      >
        {show ? <EyeOff size={12} /> : <Eye size={12} />}
      </button>
    </span>
  )
}

/* ── Input field with built-in mask toggle ──────────────────────────── */
// Uses type="text" always — avoids browser password manager overlays.
// When hidden: shows masked placeholder overlay; real value edits normally on focus.
interface MaskedInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  value: string
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void
}

export function MaskedInput({ value, onChange, className, placeholder, onKeyDown, ...props }: MaskedInputProps) {
  const [show, setShow]       = useState(false)
  const [focused, setFocused] = useState(false)

  const displayValue = (!show && !focused && value) ? mask(value) : value

  return (
    <div className="relative">
      <input
        {...props}
        type="text"
        autoComplete="off"
        data-1p-ignore   // 1Password
        data-lpignore    // LastPass
        value={displayValue}
        placeholder={placeholder}
        onKeyDown={onKeyDown}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        onChange={e => {
          // If user edited while showing masked, clear first — send the real typed value
          if (!show && !focused) return
          onChange(e)
        }}
        className={cn(
          'w-full px-3 py-2 pr-9 text-sm rounded-lg bg-muted border border-border',
          'focus:outline-none focus:ring-1 focus:ring-ring font-mono',
          className,
        )}
      />
      <button
        type="button"
        onClick={() => setShow(s => !s)}
        className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
        tabIndex={-1}
        aria-label={show ? 'Hide' : 'Show'}
      >
        {show ? <EyeOff size={14} /> : <Eye size={14} />}
      </button>
    </div>
  )
}
