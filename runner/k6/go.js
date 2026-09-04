// Go baseline (apps/go): GET /api/echo?n=N -> {"n":N,"sum":...}. ECHO_N sets the
// per-request compute (loop of N adds); default 50000 keeps one request in the
// tens of microseconds so the knee is CPU-bound rather than a pure network echo.
import http from 'k6/http';
import { check } from 'k6';
import { baseUrl, buildOptions, num, reqTags } from './lib.js';

export { handleSummary } from './lib.js';
export const options = buildOptions('go');

const URL = `${baseUrl('http://localhost:8080')}/api/echo?n=${num('ECHO_N', 50000)}`;

export default function () {
  const res = http.get(URL, { tags: reqTags({ name: 'echo' }), timeout: '10s' });
  check(res, { 'status 200': (r) => r.status === 200 });
}
