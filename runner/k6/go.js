// Go baseline (apps/go): GET /api/echo?n=N -> {"n":N,"sum":...}. ECHO_N sets the
// per-request compute (loop of N adds); default 1000000 is ~0.3 ms of CPU, so the
// knee is CPU-bound and inside the ladder (runner/config.py) rather than past
// what the loader can offer.
import http from 'k6/http';
import { check } from 'k6';
import { baseUrl, buildOptions, num, reqTags } from './lib.js';

export { handleSummary } from './lib.js';
export const options = buildOptions('go');

const URL = `${baseUrl('http://localhost:8080')}/api/echo?n=${num('ECHO_N', 1000000)}`;

export default function () {
  const res = http.get(URL, { tags: reqTags({ name: 'echo' }), timeout: '10s' });
  check(res, { 'status 200': (r) => r.status === 200 });
}
