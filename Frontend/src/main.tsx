import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from './lib/queryClient'
import './index.css'
import App from './App.tsx'

function sendToAnalytics(metric: { name: string; value: number; id: string }) {
  const endpoint = import.meta.env.VITE_VITALS_ENDPOINT?.trim();
  if (!import.meta.env.PROD || !endpoint) {
    return;
  }

  const body = JSON.stringify({ name: metric.name, value: metric.value, id: metric.id, href: location.href });
  try {
    if (navigator.sendBeacon) {
      navigator.sendBeacon(endpoint, body);
      return;
    }

    fetch(endpoint, { body, method: 'POST', keepalive: true }).catch(() => {});
  } catch {
    // ponytail: vitals are best-effort only; never block the app shell
  }
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)

// Telemetry is useful after the application is interactive, but it should not
// compete with the first render. Keep web-vitals out of the initial chunk and
// only load it when production telemetry has been configured.
if (import.meta.env.PROD && import.meta.env.VITE_VITALS_ENDPOINT?.trim()) {
  window.setTimeout(() => {
    void import('web-vitals').then(({ onCLS, onFCP, onINP, onLCP, onTTFB }) => {
      onLCP(sendToAnalytics);
      onFCP(sendToAnalytics);
      onCLS(sendToAnalytics);
      onINP(sendToAnalytics);
      onTTFB(sendToAnalytics);
    }).catch(() => {
      // Telemetry is best-effort and must never affect the application shell.
    });
  }, 2000);
}
