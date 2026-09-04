// Java workload: spring-petclinic-rest (apps/java). Read-only mix so the H2
// in-memory dataset does not drift between runs (n>=3 must stay comparable).
// Endpoints and ids from the project's openapi.yml and db/h2/data.sql
// (10 owners, 13 pets, 6 vets); verified 2026-09-03, see apps/java/README.md.
import http from 'k6/http';
import { check } from 'k6';
import { baseUrl, buildOptions, reqTags } from './lib.js';

export { handleSummary } from './lib.js';
export const options = buildOptions('java');

const BASE = baseUrl('http://localhost:9966');
const API = `${BASE}/petclinic/api`;

function pick() {
  const r = Math.random();
  if (r < 0.4) return { name: 'owners/{id}', url: `${API}/owners/${1 + Math.floor(Math.random() * 10)}` };
  if (r < 0.7) return { name: 'pets/{id}', url: `${API}/pets/${1 + Math.floor(Math.random() * 13)}` };
  if (r < 0.85) return { name: 'owners', url: `${API}/owners` };
  if (r < 0.95) return { name: 'vets', url: `${API}/vets` };
  return { name: 'pettypes', url: `${API}/pettypes` };
}

export default function () {
  const req = pick();
  const res = http.get(req.url, { tags: reqTags({ name: req.name }), timeout: '10s' });
  check(res, { 'status 200': (r) => r.status === 200 });
}
