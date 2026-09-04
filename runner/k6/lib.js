// Shared k6 v2.2.0 plumbing for the ARMed and Dangerous load scripts.
// Verified 2026-09-03 against https://grafana.com/docs/k6/latest/ and the v2.2.0 source:
//   - executors ramping-arrival-rate / constant-arrival-rate (startRate, timeUnit, preAllocatedVUs, maxVUs, stages, rate, duration)
//   - k6/execution: exec.scenario.startTime is ms since epoch
//   - handleSummary(data): legacy shape by default in v2.2.0 (data.metrics[name].values / .thresholds[expr].ok);
//     p(99) only appears in values if listed in summaryTrendStats
//   - a failed threshold makes k6 exit 99 (errext/exitcodes: ThresholdsHaveFailed = 99) unless abortOnFail;
//     thresholds here are report-only, so the runner MUST treat exit 99 as a completed run
//   - dropped_iterations is emitted when maxVUs is exhausted: read it as a knee signal too
//
// Env contract (spec §4 / plan Task 2):
//   TARGET_URL      base URL of the SUT service (script-specific default)
//   MODE            knee | fixed (default fixed)
//   SLO_MS          p99 breaking latency in ms (default 100, CMP333 acceptance rule)
//   knee:  RATE_START RATE_STEP RATE_MAX STAGE_SECONDS  (ladder; each step = RAMP_SECONDS ramp + hold)
//   fixed: RATE DURATION
//   PREALLOC_VUS MAX_VUS  VU budget for the arrival-rate executors
//   SUMMARY_PATH    where handleSummary writes the JSON (default summary.json)
import exec from 'k6/execution';

export const env = (k, d) => (__ENV[k] !== undefined && __ENV[k] !== '' ? __ENV[k] : d);
export const num = (k, d) => Number(env(k, d));

export const MODE = env('MODE', 'fixed');
export const SLO_MS = num('SLO_MS', 100);
const RATE_START = num('RATE_START', 200);
const RATE_STEP = num('RATE_STEP', 400);
const RATE_MAX = num('RATE_MAX', 3000);
const STAGE_SECONDS = num('STAGE_SECONDS', 60);
const RAMP_SECONDS = num('RAMP_SECONDS', 5); // linear ramp into each step; samples in it are tagged rate:ramp
const RATE = num('RATE', 500);
const DURATION = env('DURATION', '8m');
const PREALLOC_VUS = num('PREALLOC_VUS', 200);
const MAX_VUS = num('MAX_VUS', 4000);

export const TREND_STATS = ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'p(99.9)', 'max'];

export function baseUrl(def) {
  return env('TARGET_URL', def).replace(/\/+$/, '');
}

export function stageRates() {
  const rates = [];
  for (let r = RATE_START; r <= RATE_MAX; r += RATE_STEP) rates.push(r);
  return rates;
}

// Knee = a ladder, not a slope: hold each rate for STAGE_SECONDS so the p99 of
// a step is the p99 AT that rate. ramping-arrival-rate interpolates linearly
// between targets, hence the short ramp stage followed by a hold stage.
export function buildOptions(workload, overrides = {}) {
  const scenarios = {};
  const thresholds = {};
  if (MODE === 'knee') {
    const stages = [];
    for (const r of stageRates()) {
      stages.push({ target: r, duration: `${RAMP_SECONDS}s` });
      stages.push({ target: r, duration: `${STAGE_SECONDS - RAMP_SECONDS}s` });
      // A threshold on a tagged sub-metric is what makes k6 report that sub-metric
      // in the summary: this yields the (rate -> p99) series the runner reads.
      thresholds[`http_req_duration{rate:${r}}`] = [`p(99)<${SLO_MS}`];
    }
    scenarios.knee = {
      executor: 'ramping-arrival-rate',
      startRate: RATE_START,
      timeUnit: '1s',
      preAllocatedVUs: PREALLOC_VUS,
      maxVUs: MAX_VUS,
      stages,
      gracefulStop: '10s',
    };
  } else {
    scenarios.fixed = {
      executor: 'constant-arrival-rate',
      rate: RATE,
      timeUnit: '1s',
      duration: DURATION,
      preAllocatedVUs: PREALLOC_VUS,
      maxVUs: MAX_VUS,
      gracefulStop: '10s',
    };
    thresholds.http_req_duration = [`p(99)<${SLO_MS}`];
  }
  return Object.assign(
    {
      scenarios,
      thresholds,
      summaryTrendStats: TREND_STATS,
      discardResponseBodies: true,
      tags: { workload, mode: MODE },
    },
    overrides,
  );
}

// Tags for one request: the held rate of the current knee step (or 'ramp').
export function reqTags(extra = {}) {
  if (MODE !== 'knee') return extra;
  const elapsedMs = Date.now() - exec.scenario.startTime;
  const stepMs = STAGE_SECONDS * 1000;
  const step = Math.floor(elapsedMs / stepMs);
  const inRamp = elapsedMs - step * stepMs < RAMP_SECONDS * 1000;
  const rates = stageRates();
  const rate = inRamp || step >= rates.length ? 'ramp' : String(rates[step]);
  return Object.assign({ rate }, extra);
}

export function handleSummary(data) {
  const out = {};
  out[env('SUMMARY_PATH', 'summary.json')] = JSON.stringify(data, null, 1);
  const d = data.metrics.http_req_duration ? data.metrics.http_req_duration.values : {};
  const reqs = data.metrics.http_reqs ? data.metrics.http_reqs.values : {};
  const failed = data.metrics.http_req_failed ? data.metrics.http_req_failed.values.rate : 0;
  const dropped = data.metrics.dropped_iterations ? data.metrics.dropped_iterations.values.count : 0;
  const lines = [
    `mode=${MODE} reqs=${reqs.count || 0} rps=${(reqs.rate || 0).toFixed(1)} failed=${((failed || 0) * 100).toFixed(2)}% dropped=${dropped}`,
    `http_req_duration ms: med=${fmt(d.med)} p95=${fmt(d['p(95)'])} p99=${fmt(d['p(99)'])} max=${fmt(d.max)} (SLO p99<${SLO_MS})`,
  ];
  if (MODE === 'knee') {
    for (const r of stageRates()) {
      const m = data.metrics[`http_req_duration{rate:${r}}`];
      if (m) lines.push(`  rate=${r} p99=${fmt(m.values['p(99)'])} ok=${Object.values(m.thresholds || {}).every((t) => t.ok)}`);
    }
  }
  out.stdout = lines.join('\n') + '\n';
  return out;
}

function fmt(v) {
  return v === undefined ? 'n/a' : v.toFixed(1);
}
