// Go baseline (apps/go): GET /api/echo?n=N -> {"n":N,"median":M}. Each request
// fills N uint64 from an LCG, sorts them (slices.Sort) and returns the median,
// so ECHO_N sets the per-request work: an allocation, N memory writes and a
// data-dependent sort, not a one-instruction add loop.
// ECHO_N 10000 is an estimate, not a measurement: `go test -bench Median` in
// apps/go (golang:1.27.1 in Docker on an Apple M-series laptop, 2026-09-24)
// gave 0.18 ms per call; a server core is slower than that laptop core, so on
// m8i/m9g it should land at ~0.2-0.3 ms of CPU, which puts 15 vCPUs near
// 50k rps, inside the ladder (runner/config.py) and under the loader's ceiling.
import http from 'k6/http';
import { check } from 'k6';
import { baseUrl, buildOptions, num, reqTags } from './lib.js';

export { handleSummary } from './lib.js';
export const options = buildOptions('go');

const URL = `${baseUrl('http://localhost:8080')}/api/echo?n=${num('ECHO_N', 10000)}`; // calibrated on the calibration day

export default function () {
  const res = http.get(URL, { tags: reqTags({ name: 'echo' }), timeout: '10s' });
  check(res, { 'status 200': (r) => r.status === 200 });
}
