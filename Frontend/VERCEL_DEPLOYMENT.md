# Deploying the frontend on Vercel

When importing the `PMS_DevOPS` repository, create a separate Vercel project
for the `Frontend` directory:

- **Root Directory:** `Frontend`
- **Framework Preset:** `Vite`
- **Build Command:** `npm run build`
- **Output Directory:** `dist`
- **Install Command:** `npm ci`

The checked-in `vercel.json` keeps BrowserRouter routes working after a direct
refresh and caches fingerprinted assets. Configure this environment variable
in Vercel for Production, Preview, and Development:

```text
VITE_API_BASE_URL=https://<your-deployed-backend-domain>
```

Do not use `localhost` in a deployed environment. Socket.IO is optional; Vercel
frontend hosting does not provide a persistent WebSocket server by itself.
