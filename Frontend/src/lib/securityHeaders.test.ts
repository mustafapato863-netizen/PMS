import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { SECURITY_HEADERS } from './securityHeaders';

describe('frontend security headers', () => {
  it('publishes the same protections on every Vercel response and keeps hashed assets cached', () => {
    const vercel = JSON.parse(readFileSync(path.join(process.cwd(), 'vercel.json'), 'utf8')) as {
      headers: Array<{ source: string; headers: Array<{ key: string; value: string }> }>;
    };
    const document = vercel.headers.find((entry) => entry.source === '/(.*)');
    const assets = vercel.headers.find((entry) => entry.source === '/assets/(.*)');
    const published = Object.fromEntries((document?.headers ?? []).map((header) => [header.key, header.value]));

    for (const [key, value] of Object.entries(SECURITY_HEADERS)) {
      expect(published[key]).toBe(value);
    }
    expect(published['Strict-Transport-Security']).toBe('max-age=31536000; includeSubDomains');
    expect(published['Cache-Control']).toBe('no-cache');
    expect(assets?.headers).toContainEqual({
      key: 'Cache-Control',
      value: 'public, max-age=31536000, immutable',
    });
  });
});
