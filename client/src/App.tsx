import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { TooltipProvider } from '@/shared/components/ui/tooltip'
import { Toaster } from '@/shared/components/ui/toaster'
import { ErrorBoundary } from '@/shared/components/ui/error-boundary'
import { Layout } from '@/shared/components/layout/Layout'
import { Dashboard } from '@/features/dashboard'
import { Jobs } from '@/features/jobs'
// import { Mappings } from '@/features/mappings'
import { Outreach } from '@/features/outreach'

export default function App() {
  return (
    <BrowserRouter>
      <TooltipProvider delay={300}>
        <ErrorBoundary>
          <Layout>
            <Routes>
              <Route path="/" element={
                <ErrorBoundary>
                  <Dashboard />
                </ErrorBoundary>
              } />
              <Route path="/jobs" element={
                <ErrorBoundary>
                  <Jobs />
                </ErrorBoundary>
              } />
              {/* <Route path="/mappings" element={
                <ErrorBoundary>
                  <Mappings />
                </ErrorBoundary>
              } /> */}
              <Route path="/outreach/*" element={
                <ErrorBoundary>
                  <Outreach />
                </ErrorBoundary>
              } />
            </Routes>
          </Layout>
        </ErrorBoundary>
        <Toaster />
      </TooltipProvider>
    </BrowserRouter>
  )
}
