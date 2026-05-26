import React from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'
import { Button } from './button'

interface State {
  error: Error | null
  errorInfo: React.ErrorInfo | null
}

interface Props {
  children: React.ReactNode
  fallback?: (error: Error, reset: () => void) => React.ReactNode
}

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null, errorInfo: null }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    this.setState({ errorInfo: info })
    console.error('[ErrorBoundary]', error, info)
  }

  reset = () => this.setState({ error: null, errorInfo: null })

  render() {
    const { error } = this.state
    if (!error) return this.props.children

    if (this.props.fallback) return this.props.fallback(error, this.reset)

    return (
      <div className="flex flex-col items-center justify-center h-full min-h-[200px] gap-4 p-8 text-center">
        <div className="p-3 rounded-full bg-red-500/10">
          <AlertTriangle size={24} className="text-red-400" />
        </div>
        <div className="space-y-1 max-w-sm">
          <p className="font-mono text-sm font-semibold text-foreground">Something went wrong</p>
          <p className="font-mono text-xs text-red-400 break-all">{error.message}</p>
        </div>
        <Button variant="outline" size="sm" onClick={this.reset}>
          <RefreshCw size={13} /> Try again
        </Button>
      </div>
    )
  }
}
