import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

beforeEach(() => {
  vi.resetModules();
  vi.stubEnv('DEV', true);
  vi.stubEnv('PROD', false);
  vi.stubEnv('VITE_API_BASE_URL', 'http://127.0.0.1:8000');
  vi.stubEnv('VITE_SOCKET_URL', 'ws://127.0.0.1:8000');
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

function useBrowserHost(hostname: string) {
  vi.stubGlobal('window', {
    location: { hostname, origin: `http://${hostname}:5173` },
  });
}

describe('local authentication service addresses', () => {
  it.each([
    { hostname: 'localhost', configuredHostname: '127.0.0.1' },
    { hostname: '127.0.0.1', configuredHostname: 'localhost' },
    { hostname: '[::1]', configuredHostname: '127.0.0.1' },
  ])(
    'uses the page hostname $hostname so refresh cookies stay on the same site',
    async ({ hostname, configuredHostname }) => {
      useBrowserHost(hostname);
      vi.stubEnv('VITE_API_BASE_URL', `http://${configuredHostname}:8000`);
      vi.stubEnv('VITE_SOCKET_URL', `ws://${configuredHostname}:8000`);
      const config = await import('./config');

      expect(config.API_BASE).toBe(`http://${hostname}:8000`);
      expect(config.SOCKET_URL).toBe(`ws://${hostname}:8000`);
    },
  );

  it('aligns the default local services when no URLs are configured', async () => {
    useBrowserHost('localhost');
    vi.stubEnv('VITE_API_BASE_URL', undefined);
    vi.stubEnv('VITE_API_URL', undefined);
    vi.stubEnv('VITE_SOCKET_URL', undefined);
    const config = await import('./config');

    expect(config.API_BASE).toBe('http://localhost:8000');
    expect(config.SOCKET_URL).toBe('ws://localhost:8000');
  });

  it('preserves remote endpoints, ports, paths, and socket protocols', async () => {
    useBrowserHost('localhost');
    vi.stubEnv('VITE_API_BASE_URL', 'https://api.example.com:8443/pms/');
    vi.stubEnv('VITE_SOCKET_URL', 'http://127.0.0.1:9000/socket.io?transport=polling');
    const config = await import('./config');

    expect(config.API_BASE).toBe('https://api.example.com:8443/pms');
    expect(config.SOCKET_URL).toBe('http://localhost:9000/socket.io?transport=polling');
  });

  it('preserves explicitly configured production endpoints', async () => {
    useBrowserHost('localhost');
    vi.stubEnv('DEV', false);
    vi.stubEnv('PROD', true);
    const config = await import('./config');

    expect(config.API_BASE).toBe('http://127.0.0.1:8000');
    expect(config.SOCKET_URL).toBe('ws://127.0.0.1:8000');
  });
});
