// Inference workload: llama-server OpenAI-compatible POST /v1/chat/completions.
// Verified 2026-09-03 against tools/server/README.md (master): the non-streaming
// response carries a `timings` object by default (prompt_n, prompt_ms,
// prompt_per_second, predicted_n, predicted_ms, predicted_per_second); no request
// field is needed. Each field lands in a custom metric so the summary JSON has
// tok/s per request (Trend) and total tokens (Counter -> aggregate tok/s = count/duration).
//
// Modes: MODE=fixed (constant-arrival-rate, plan Task 2) and MODE=saturate
// (constant-vus with VUS = server slots, closed loop): with --parallel N slots an
// open arrival rate either idles slots or piles requests in the server queue, so
// the saturating mode is the one that measures the silicon, the fixed one the SLO.
import http from 'k6/http';
import { check } from 'k6';
import { Counter, Trend } from 'k6/metrics';
import { MODE, TREND_STATS, baseUrl, buildOptions, env, num, reqTags } from './lib.js';

export { handleSummary } from './lib.js';

export const options =
  MODE === 'saturate'
    ? {
        scenarios: {
          saturate: { executor: 'constant-vus', vus: num('VUS', 4), duration: env('DURATION', '6m'), gracefulStop: '120s' },
        },
        summaryTrendStats: TREND_STATS,
        tags: { workload: 'inference', mode: MODE },
      }
    : buildOptions('inference', { discardResponseBodies: false });

const URL = `${baseUrl('http://localhost:8080')}/v1/chat/completions`;
const MAX_TOKENS = num('MAX_TOKENS', 128);
const PROMPT = env(
  'PROMPT',
  'Explica en un solo parrafo, sin listas, por que un procesador con mas nucleos fisicos a menor frecuencia puede rendir mejor que uno con menos nucleos e hyperthreading en un servidor web con alta concurrencia.',
);

const predictedTps = new Trend('llama_predicted_per_second');
const promptTps = new Trend('llama_prompt_per_second');
const promptMs = new Trend('llama_prompt_ms', true);
const predictedMs = new Trend('llama_predicted_ms', true);
const predictedTokens = new Counter('llama_predicted_tokens');
const promptTokens = new Counter('llama_prompt_tokens');

export default function () {
  const body = JSON.stringify({
    model: env('MODEL', 'default'),
    messages: [{ role: 'user', content: PROMPT }],
    max_tokens: MAX_TOKENS,
    temperature: 0,
    stream: false,
  });
  const res = http.post(URL, body, {
    headers: { 'Content-Type': 'application/json' },
    tags: reqTags({ name: 'chat/completions' }),
    timeout: '300s',
  });
  const ok = check(res, { 'status 200': (r) => r.status === 200 });
  if (!ok) return;
  const t = res.json('timings');
  if (!t) return;
  predictedTps.add(t.predicted_per_second);
  promptTps.add(t.prompt_per_second);
  promptMs.add(t.prompt_ms);
  predictedMs.add(t.predicted_ms);
  predictedTokens.add(t.predicted_n);
  promptTokens.add(t.prompt_n);
}
