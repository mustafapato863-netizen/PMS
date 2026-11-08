import { createServer } from 'vite';

const server = await createServer({
  server: {
    port: 5173,
    strictPort: true,
  },
});

await server.listen();
server.printUrls();
