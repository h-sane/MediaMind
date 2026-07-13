import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import { ErrorBoundary } from './ErrorBoundary'
import { logDevError } from './stores/devLog'
import './assets/main.css'

window.addEventListener('error', (event) => {
  logDevError('window', event.error?.stack ?? event.message)
})

window.addEventListener('unhandledrejection', (event) => {
  const reason = event.reason
  logDevError(
    'unhandledrejection',
    reason instanceof Error ? (reason.stack ?? reason.message) : String(reason)
  )
})

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { refetchOnWindowFocus: false }
  }
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </ErrorBoundary>
  </React.StrictMode>
)
