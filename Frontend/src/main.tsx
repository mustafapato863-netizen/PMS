import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from './lib/queryClient'
import { onCLS, onFCP, onINP, onLCP, onTTFB } from 'web-vitals'
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

onLCP(sendToAnalytics);
onFCP(sendToAnalytics);
onCLS(sendToAnalytics);
onINP(sendToAnalytics);
onTTFB(sendToAnalytics);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
