import { gzipSync } from 'node:zlib';
import { readdir, readFile } from 'node:fs/promises';
import { join } from 'node:path';

const assetsDir = join(process.cwd(), 'dist', 'assets');
const budgets = [
  {
    name: 'charts runtime',
    patterns: [
      /^charts-.*\.js$/,
      /^CartesianChart-.*\.js$/,
      /^BarChart-.*\.js$/,
      /^LineChart-.*\.js$/,
      /^GradeDistributionChart-.*\.js$/,
    ],
    rawKb: 450,
    gzipKb: 130,
  },
  { name: 'animation', pattern: /^animation-.*\.js$/, rawKb: 160, gzipKb: 50 },
  { name: 'team dashboard route', pattern: /^TeamDashboardView-.*\.js$/, rawKb: 220, gzipKb: 60 },
];

const files = await readdir(assetsDir);
const failures = [];

for (const budget of budgets) {
  const matchingFiles = budget.patterns
    ? files.filter((candidate) => budget.patterns.some((pattern) => pattern.test(candidate)))
    : files.filter((candidate) => budget.pattern.test(candidate));

  if (!matchingFiles.length) {
    failures.push(`${budget.name}: expected chunk was not emitted`);
    continue;
  }

  let rawBytes = 0;
  let gzipBytes = 0;
  for (const filename of matchingFiles) {
    const content = await readFile(join(assetsDir, filename));
    const compressed = gzipSync(content, { level: 9 });
    rawBytes += content.byteLength;
    gzipBytes += compressed.byteLength;
    console.log(`${filename}: ${(content.byteLength / 1024).toFixed(2)} kB raw / ${(compressed.byteLength / 1024).toFixed(2)} kB gzip`);
  }

  const rawKb = rawBytes / 1024;
  const gzipKb = gzipBytes / 1024;
  if (matchingFiles.length > 1) {
    console.log(`${budget.name} aggregate: ${rawKb.toFixed(2)} kB raw / ${gzipKb.toFixed(2)} kB gzip`);
  }

  if (rawKb > budget.rawKb || gzipKb > budget.gzipKb) {
    failures.push(
      `${budget.name}: ${rawKb.toFixed(2)} kB raw / ${gzipKb.toFixed(2)} kB gzip ` +
      `(budgets ${budget.rawKb} / ${budget.gzipKb})`,
    );
  }
}

if (failures.length) {
  console.error('\nBundle budget failed:');
  failures.forEach((failure) => console.error(`- ${failure}`));
  process.exitCode = 1;
} else {
  console.log('Bundle budgets passed.');
}
