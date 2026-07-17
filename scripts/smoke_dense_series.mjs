/**
 * cd frontend && npx vite-node ../scripts/smoke_dense_series.mjs
 */
import { isDenseYoYSeries } from '../frontend/src/lib/metrics.js';

const sparse = [
  { year: '2024', value: 1 },
  { year: '2025', value: 2 },
];
const dense = [
  { year: '2021', value: 1 },
  { year: '2022', value: 2 },
  { year: '2023', value: 3 },
  { year: '2024', value: 4 },
];
if (isDenseYoYSeries(sparse) !== false) throw new Error('sparse should fail');
if (isDenseYoYSeries(dense) !== true) throw new Error('dense should pass');
console.log('ok dense gate');
