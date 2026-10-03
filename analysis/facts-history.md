# Facts: history, methodology rulings and learnings (ARMed and Dangerous)

Internal working material, English. Compiled 2026-09-28 from repo sources only (no AWS, no cluster).
Every line carries its source. No speculation: where a source does not say why, this file says "not established".

**Citation keys**
- `P:n` = `.superpowers/sdd/2026-09-02-armed-and-dangerous/progress.md` line n (the SDD ledger).
- `SDD/<file>:n` = another file in that same folder.
- `G:<file>:n` = `results/profiler-gate.md` line n.
- `L:<dir>` = `results/<dir>/ledger.md` (runner cost ledger for that results date/dir).
- `cost.md:n` = `results/cost.md` line n.
- `spec:n` = `docs/superpowers/specs/2026-09-02-armed-and-dangerous-design.md` line n; `plan:n` = `docs/superpowers/plans/2026-09-02-armed-and-dangerous.md` line n.
- 7-hex hashes = commits on `main` (`git log`, read-only). Git dates are the committer's local date (Peru, UTC-5); ledger times are UTC ("Z"), so a commit can carry the previous calendar day (e.g. `b9207f3` is 2026-09-25 in git, ruling logged 2026-09-26 ~04:45Z, P:268).

Cell names: `arm-*` = m9g.4xlarge (Graviton5), `amd-*` = m8a.4xlarge (EPYC 9R45 Turin), `x86-*` = m8i.4xlarge (Xeon 6). "Knee" = highest load under the p99 SLO. "Fixed run" = run at 80 % of the knee.

---

## 1. Timeline (2026-09-02 → end of Task 7 day 3, 2026-09-28)

| Date (UTC unless noted) | What happened | Source |
|---|---|---|
| 2026-09-02 | Spec v1 and plan dated this day (docs only; v1 kept in git). | spec:1-5, plan:1 |
| 2026-09-03 | Repo skeleton `335333d`; v2 rules `9d4b98e` (Task 1). Spec v2: 4xlarge nodes, stress to breaking point, stock/tuned on both silicons, APerf, iperf3 scene, MNG scaled 0↔1 per cell. Speaker ruling: Terraform, not OpenTofu (`966831b`). SDD adopted mid-plan at the speaker's request. Task 2 apps (`15909e2`, fix `bf79b3a`). | P:3, P:23, P:31-42, spec:5-7 |
| 2026-09-04 (one long day) | Tasks 3-6 implemented and reviewed (`877302b`..`194e8b0`), Codex control points CP1-CP3 merged; whole-branch review (4 Critical, 9 Important) + fix wave (`32c5074`, `0144265`, `d4fe469`, `af7f1b1`); registry switch GHCR → private ECR (`592fd8d`..`b7a4b90`); VPC created in Terraform (`e8fdb74`, `f84e67a`). ~9 h overnight lost to a hung `codex exec` (open stdin). | P:44-133, P:69 |
| 2026-09-04 16:2x-17:2x | GATE DAY. First local `terraform apply` failed at 119/123 (EBS CSI policy ARN, Karpenter managed policy over 6144 chars); destroyed. Claude Code process restarted mid-apply (see §4). Speaker ruling: rebuild via GitHub Actions + OIDC + S3 backend (`a8c72c9`, `055a008`, `efdd0fd`, `b1f0592`). | P:134-143 |
| 2026-09-04 ~18:05-20:54 | CI apply 111/112 (Karpenter helm_release unreachable from the runner → Karpenter moved out of Terraform, `0e9c203`). Smoke gate (Task 6.5) ran 18:19-20:54: knobs read on Bottlerocket 1.64, Java/Mongo/net/inference exercised, loader c7i.4xlarge found to be the ceiling. Results `46e5058`; CI destroy 21:20, account clean 21:2x. Gate SUT cost $1.13, ledger total $6.51. | P:144-157, G:1-95, L:2026-09-04 |
| 2026-09-05 → 2026-09-23 | No commits (git log jumps from `0909c4f` 09-04 to `f4824d9` 09-24). The plan had scheduled the gate for 09-19 and Task 7 for 09-20/21, behind the Strands talk (priority until 09-12). | git log, plan:21 |
| 2026-09-24 (day) | Post-gate fixes batch (`f4824d9`): loader c7i.8xlarge, Java SLO 10 ms, drop rule as a rate > 0.1 %, profiler 0.160.0. Data-quality batch after a Codex CP4 review (`e3f00b3`, `f4ad213`, `af2b105`, `ec93f90`, fix round `52cd91a`, `9837fb7`, `2522f02`). Pushed; images rebuilt with the new Go sort workload (`884967d`). | P:158-173 |
| 2026-09-24 22:47Z → 09-25 ~07:40Z | CALIBRATION session (CI apply started 22:47Z, Bottlerocket now 1.66.0). CAL 1-13 on Java, Go, llama, net, Mongo; SG fix for API-server proxy (`16eb806`); SUT-saturation waiver (`addaa11`); tuned Java = best per chip (`9738034`); x86 inference -t 15 (`5679885`); KleidiAI build tested (`785d4f6`, `d541dd9`); Mongo 8.0.32 (`3ceab59`); two k6 generators (`dc3dd95`, `d1a0a8f`). Speaker: keep the cluster up overnight. | P:174-200, P:177 |
| 2026-09-25 early (UTC) | Speaker ruling: full AMD column (`6fea342`, `bcb5306`, `db6d017`, `7c578b7`); AMD apply; AMD calibration (Java, Go, llama); Mongo tickets diagnosis; Mongo 2-client check; multi-YCSB (`8dd4b8f`, `84e633d`); pytest-touched-live-cluster incident, guard `41a8870`. Nodes drained by hand at ~07:40Z; morning handoff. | P:201-221 |
| 2026-09-25 (morning) | Speaker rulings R1-R4 (loader c8i.16xlarge, add PostgreSQL, keep 0.1 % for now, Mongo tickets undecided). | P:223-228 |
| 2026-09-25 (day) | R1 commit `24b1ede`; CI apply failed 409/400 due to the hand drain; fixed by hand + re-apply, loader c8i.16xlarge Ready 15:2xZ. R2 PostgreSQL implemented and reviewed (`2d83fd0`, `330109e`, `5b1896e`, `7372fcb`, `1fbfbfd`, `cd0e10f`). PG calibration 15:3xZ-17:44Z on six cells; StatefulSet rollback bug fixed (`0be77c8`); closed-loop knee rule (`6288f82`). | P:229-248 |
| 2026-09-25 ~17:5xZ → 09-26 07:29Z | TASK 7 DAY 1 (Go 3 cells, Java 10 cells incl. vthreads and smtoff, n=3). Pyroscope read of PG → shmem THP work on a branch (`0c6979a`, `48b11b5`). x86-tuned failed 02:10Z (postgres pod squatting the node) → `14c19da`; SSO expired ~02:15Z, chain halted, resumed 02:4xZ. R3 ruling 0.25 % (`b9207f3`) ~04:45Z, day-1 runs re-judged. Day 1 complete 07:29Z; SUT $11.16, ledger total $30.25. | P:249-284, L:2026-09-25-task7-d1 |
| 2026-09-26 07:29-08:15Z | PG THP-for-shmem A/B on three tuned cells (+11.3 / +12.3 / +11.5 %); never-crossed bug fixed (`b3094f3`); speaker ruling PG tuned = shared_buffers 16GB + THP shmem (`0c96909`). | P:285-287 |
| 2026-09-26 12:08Z → 09-27 04:18Z | TASK 7 DAY 2 (net 6, Mongo 6, PostgreSQL 6, inference 7). Mongo arm-stock fixed runs EBS-bound → volume raised to 16000 IOPS / 1000 MiB/s (speaker). PG schedule lag recorded not judged (`40fe64c`); PG fixed-clients A/B (`4fb9e0c`) → 1x knee clients (`960d17a`); PG re-run at 1x. SSO re-login 20:33Z. Task 7 complete 04:18Z: 38/38 cells, every published fixed run valid. SUT $14.57, ledger total $33.66. | P:287-330, L:2026-09-26-task7-d2 |
| 2026-09-27 ~04:40Z | Handoff; speaker decision: full second lab day (day 3) on fresh nodes for headline cells. | P:332-362 |
| 2026-09-27 06:00Z → 09-28 00:49Z | TASK 7 DAY 3 (24 cells: Go, Java, inference, PostgreSQL). SSO auto-renew fired 16:57Z. 24/24 rc=0, no invalid runs. | P:364-376 |
| 2026-09-28 00:53-05:15Z | Day 3 MongoDB (all 6 cells). SSO token died 01:37Z, 80 min before the deadline; guard stopped cleanly between cells; guard patched to renew on sts failure; relaunched. Day 3 complete 05:15Z: 30/30 cells, 0 invalid runs. SUT $20.08, ledger total $39.17. | P:378-387, `results/chain-d3.out`, L:2026-09-27-task7-d3 |
| 2026-09-28 ~10:50-11:00Z | Cluster parked (speaker: "Scale to 0"): `fd07c5d` support node groups min 0, CI apply, CLI desiredSize 0 on loader+tools (first attempt failed silently on an expired token). Mongo volume reverted to gp3 defaults by the speaker. | P:389-395 |

---

## 2. Methodology decisions and speaker rulings

Format: rule — why / triggering evidence — commit — effect on results.

### 2.1 Pre-flight and build (2026-09-03/04)
- **Java Service port 9966**, not 8080 as plan T5 said — app contract wins. P:22.
- **Terraform (HCL) with terraform-aws-modules/eks 21.x, not OpenTofu; CDK rejected** (module exposes cpu_options, bootstrap args, Bottlerocket AMI types). Speaker, `966831b`. P:23, spec:7.
- **Java k6 mix read-only** — H2 in-memory growth over a 57-min cell would change the workload between runs. P:24.
- **Inference `MODE=saturate` (constant VUs = slots)** added next to constant-arrival-rate — open arrival against N slots either idles or queues. P:25.
- **Knee = ladder of held steps (ramp + hold, tagged rate:N)**, not one linear ramp — gives p99 at a held rate. P:26.
- **PetClinic pinned to a master SHA (Boot 4.1.1)**; `SPRING_JPA_SHOW_SQL=false` as an identical control. P:27-28.
- **No provenance/SBOM attestations** on image build (break the local OCI platform assertion). P:46.
- **SUT MNG max_size 2** (iperf3 client needs a second node of the same type; spec §3 said 1). P:55.
- **CPU pinning as a control on all SUT cells**: static CPU Manager, 1 vCPU reserved; Guaranteed pods get 15 exclusive CPUs (7 on smtoff). From Codex CP2. P:81-82. `kube-reserved` 250m, not 1000m, so a 15-CPU pod fits next to DaemonSets. P:87.
- **Inference `-t` = pod's exclusive vCPUs (15)**; overlay `x86-t16` renamed `x86-t15`. P:83.
- **C-states knob writes the C1 exit latency, not 0** (0 forces POLL; kernel cpuidle governor rule). Whole-branch review finding; `0144265`; spec §3.5 amended. P:107, SDD/final-fix-report.md:112-142.
- **Knee validity judged per step up to the crossing**; whole-run failed/dropped rule only for fixed runs (the old rule rejected any ladder that crossed). `32c5074`. P:108, SDD/final-fix-wave.md:6.
- **Uncrossed ladder is not a knee** (`ladder_never_crossed`). SDD/final-fix-wave.md:7.
- **Registry = private ECR in the sandbox, not GHCR** (speaker 2026-09-04): bare image names + `:UNSET` sentinel so no account ID enters git. `592fd8d`..`b7a4b90`. P:120, spec §4 note.
- **VPC created by Terraform**, one AZ for nodes, no NAT; every AWS CLI call pins `--region us-east-1` (the profile defaulted to another region). Budget ceiling $200 relaxed by the speaker, per-day gate kept at $80. `e8fdb74`. P:129, cost.md:37-45.
- **Infra applied/destroyed from GitHub Actions + OIDC + S3 backend** after the failed local apply (speaker, conditional ruling). P:136-138.
- **Karpenter chart out of Terraform**, installed from the laptop only on the arc/clip day (API endpoint allow-list is the laptop /32; CI cannot reach it). `0e9c203`. P:146.

### 2.2 Gate-driven (2026-09-04, applied 2026-09-24)
- **Java SLO p99 < 10 ms** (CMP333's 100 ms was for a heavier Groovy app; PetClinic reads ~0.1 ms CPU; with 100 ms the knee was out of reach of one loader). P:150, G:35-57.
- **Loader c7i.4xlarge → c7i.8xlarge** (gate: 4xlarge at 98 % CPU at 90-100k rps, ~60k rps at 80 %). `f4824d9`. P:150, P:163, G:48-57.
- **Fixed-run `dropped_iterations` becomes a share (> 0.1 %)**, not "any drop" (gate fixed runs at 0.05 % were flagged invalid). `f4824d9`. G:63, G:77, P:163.
- **Profiler pinned to 0.160.0** (0.147.0 fails to load on kernel 6.18). G:31, P:163.
- **Java ladder 10k→120k step 5k** (x86-tuned knee between 30k and 40k; 10k steps would round it down ~25 %); later step 10k with a per-run 2k fine ladder (data-quality batch item 4). P:159, SDD/data-quality-brief.md:31-33.
- **VU budget PREALLOC 2000 / MAX 16000** for ladder, warm-up and fixed runs. P:160, P:166.
- **Mongo knee operationcount 2M → 10M** (gate steps lasted 10-15 s, not ~60 s); threads 16..512. P:161.

### 2.3 Data-quality batch (2026-09-24, Codex CP4 + controller)
- **A knee must be a real crossing**: a step that under-delivers while latency is fine ends as `capacity_unresolved` (was being published as the SUT knee; "the loader's ceiling published as knee"). `f4ad213`. P:167, SDD/data-quality-brief.md:18-23.
- **Loader guard per step through the crossing** (the whole-ladder peak guard would have rejected every Java cell once the ladder runs to 120k). P:167, SDD/data-quality-brief.md:25-26. Vindicated at CAL 1: loader 50 % at the crossing, 97 % at 120k. P:175.
- **Fixed runs must meet the SLO and deliver ≥ 0.95 × target** (`fixed_over_slo`, `fixed_underdelivered`) — gate fixed run at 80 % of a 2.5 ms knee had p99 5.26 ms unflagged. SDD/data-quality-brief.md:28-29.
- **Per-run fine knee** before each Java/Go fixed run; capacity = median/min/max of run knees. SDD/data-quality-brief.md:31-33.
- **Java pools explicit controls** (Hikari 10, Tomcat 200 = Spring defaults) + `--app-env` + pool gauges; **Go workload = generate-and-sort** (not a dependent add chain); **llama system_info recorded**; Mongo throughput on TOTAL OPS; net CPU per direction with idle baseline (60 s, `9837fb7`). `af2b105`, `e3f00b3`, `ec93f90`. P:168-171.
- **Codex C4 (network congestion as SUT crossing) not adopted**: loader→SUT ~2-3 Gbps at 120k rps vs 12.5 Gbps loader NIC. P:170.

### 2.4 Calibration rulings (2026-09-24/25)
- **SG rule 8080/9966 from the cluster SG** (API-server service proxy timed out → actuator gauges "missing", Go cpuset check would fail). `16eb806`. P:176.
- **Hikari 10 / Tomcat 200 stay** — pools never the limit (pending 0 at every step). P:181.
- **SUT_SATURATED waiver (0.95)** for the crossing step only: loader guard waived when the SUT node is ≥ 0.95 × exclusive CPUs in that step (x86 cliff: k6 piles VUs on a collapsing SUT). CAL 7 re-judged valid. `addaa11` (matched by subject; ledger gives no hash). P:185.
- **Tuned Java = best per chip**: x86 tiered ON; arm CMP333 bundle; later amd CMP333 bundle. Speaker, `9738034`, `3fdc6df`. P:186-187, P:207. (Spec §3.5 still says "same flags on both architectures", spec:89 — see contradictions.)
- **x86-tuned inference = -t 15** (SMT helps: 57.5 vs 40.6 tok/s with -t 8); the -t 8 cell is `x86-t8`. Speaker, `5679885`. P:191-192.
- **arm-tuned inference keeps the official llama.cpp image** (KleidiAI build measured 105.2 vs 108.8 tok/s). P:194.
- **MongoDB stays on 8.0, bumped to 8.0.32** (no 9.0 server exists). Speaker, `3ceab59`. P:197, P:200.
- **Two k6 generators per Java/Go run**: one k6 adds ~0.8 ms (+13 %) to p99 at 70k rps; two deliver the same rps at lower p99. Speaker; `dc3dd95`, `d1a0a8f`. P:198-199, SDD/two-generators-brief.md:8-9.
- **N=2 go-ycsb clients per Mongo step**: one client 191.1k ops/s vs two 242.2k (+27 %). `8dd4b8f`, `84e633d`. P:209, SDD/multi-ycsb-brief.md:8-9.
- **Full AMD column** (m8a.4xlarge, 16 cores, no SMT, $0.97376/h) — anticipated Q&A objection "8 cores + SMT Intel vs 16 Graviton cores". Speaker 2026-09-25. `6fea342`, `bcb5306`, `db6d017`. P:201, spec:73.
- **Tuned cell requires its C-states knob Ready on the SUT node** (`check_cstates`). `7c578b7`. P:204.

### 2.5 Speaker rulings R1-R4 (2026-09-25 morning)
- **R1 loader → c8i.16xlarge** (64 vCPU, $2.99872/h): c7i.8xlarge read 71 % with two YCSB clients at 128 threads (guard 70 %). `24b1ede`. P:216, P:224, P:230. Full loader history: c7i.4xlarge (gate) → c7i.8xlarge (`f4824d9`) → c8i.16xlarge (`24b1ede`).
- **R2 add PostgreSQL + pgbench** so the DB story does not rest on Mongo's admission-control limits. `2d83fd0`, `330109e`, `5b1896e`; spec amendment spec:113-131. P:225, P:229.
- **R3 dropped-iterations: keep 0.1 % for now, judge with Task 7 data.** P:226.
- **R4 Mongo tickets: undecided; default = present "Mongo stops before the CPU"**. P:227.

### 2.6 PostgreSQL design rulings (2026-09-25/26)
- **Fixed runs judge service latency (`time - schedule_lag`), lag reported separately**; initially a fixed run was invalid on lag p99 > 1 ms (`fixed_generator_lagging`). `7372fcb`. P:233-234, SDD/postgres-fix-round-1.md:3.
- **pgbench pod guard fails closed** (2×16 threads = 50 % of 64 vCPU, node guard could never trip). `cd0e10f`. P:236-237.
- **DB cells scale their own StatefulSet to 0 and wait for the pod to be gone before applying the overlay** (StatefulSet forced-rollback trap). `0be77c8`. P:241.
- **Closed-loop knee = throughput peak under the SLO; walk ends on a step < 95 % of the best (`throughput_drop`), Mongo too.** Trigger: amd-stock peaked at 256 clients and fell at 512 without ever crossing 5 ms → `ladder_never_crossed`. `6288f82`; bug fix `b3094f3` (never-crossed only if the peak is the top step). P:242, P:285, spec:131.
- **Every cell parks every DB StatefulSet it does not measure** (postgres-0 left from calibration took 15 CPU/56Gi on x86-tuned). `14c19da`. P:264.
- **PG tuned = shared_buffers 16GB + THP for shmem** (runner-applied DaemonSet writes `shmem_enabled=always`; PG 18 does not madvise). Evidence: Pyroscope showed tuned cells spend 23-28 % of PG CPU on page faults/unmap with 4 KiB pages; A/B +11.3 % (arm), +12.3 % (amd), +11.5 % (x86); 93.6 % of the pool on 2 MiB pages. Speaker 2026-09-26, `0c96909`. P:250, P:285-287, SDD/pg-hugepages-brief.md:8-13, spec:129.
- **Schedule lag recorded, not judged** (`pg_max_lag_p99_ms None`): arm-stock fixed run at 2x clients had lag p99 547-968 ms while service p99 was 3.66-4.19 ms. Speaker, `40fe64c`. P:299.
- **PG fixed runs at 1x knee clients (was 2x)**: at 2x the SUT ran 14.2-14.4/15 cores with 5.8-9.2 backends in `LWLock:BufferMapping`; at 1x 12.8-13.2 cores and 1.6-1.7 waiters at the same ~230k tps → the 2x rule was harness-induced load. `4fb9e0c` (A/B flag), `960d17a`. P:300-302. Effect: PG arm-stock/arm-tuned 2x results set aside in `task7-d2/postgres-2x/`; PG x6 re-run at 1x, 18/18 fixed runs valid. P:302, P:312-318.
- **Report PG throughput, not the knee's client count** (arm-stock plateau 128-256; which step peaks is noise, 277-290k ±4 %). P:312.

### 2.7 Task 7 rulings
- **R3 final: fixed-run dropped_iterations 0.1 % → 0.25 %.** Day-1 Java fixed runs fell between 0.048 and 0.124 %, rising with rps not latency; amd-stock run-1 was invalid at 0.10 % and arm-tuned-vthreads runs 1-3 at 0.106-0.124 %. Speaker ~04:45Z 2026-09-26, `b9207f3`. Saved metas re-judged, originals kept as `invalid_before_rejudge`; day 1 became 30/30 valid at that point. P:261, P:268-269, `runner/README.md:410`.
- **Mongo volume raised to 16000 IOPS / 1000 MiB/s** (speaker): the 125 MiB/s gp3 cap was saturated for the whole fixed run (VolumeWriteBytes flat at ~131 MB/s); knee unchanged (242.7k → 239.8k) but fixed runs went from invalid (~134k delivered of 194.2k, READ p99 ~23 ms) to valid (191.8k delivered, p99 3.39-3.48 ms). Not Terraform-managed. P:295-297, P:310, P:337.
- **Keep n=3 on every cell, x86-t8 stays; day 2 right after day 1.** Speaker 21:43Z. P:258.
- **Chains stop before the SSO deadline** (deadline file, later auto-renew). P:266, P:353, P:366.
- **Second full lab day (day 3) on fresh nodes** for two independent instances/days per cell. Speaker 2026-09-27. P:333.
- **Show AMD wins honestly** (AMD leads PostgreSQL raw and per $). Speaker agreed. P:349.
- **Cluster not destroyed between Task 7 days** (overrides CLAUDE.md "down between lab days"); parked at 0 on 09-28 with `fd07c5d`. P:177, P:249, P:389-390.

---

## 3. Calibration findings (n=1 each)

| Dir (`results/…`) | Tested | Result / conclusion | Source |
|---|---|---|---|
| `2026-09-24-cal-j-arm-h10` | CAL 1: Java arm-tuned, **Hikari pool 10** / Tomcat 200 ("h" = Hikari, not heap: cell.json `app_env` of h32 = `SPRING_DATASOURCE_HIKARI_MAXIMUMPOOLSIZE: 32`) | knee 80k (crossing 90k at 15.7 ms); loader 50 % at crossing, 97 % at 120k → per-step guard vindicated; knobs on Bottlerocket 1.66 match gate | P:175 |
| `2026-09-24-cal-j-x86-h10` | CAL 2: Java x86-tuned, CMP333 flags, Hikari 10 | knee 40k (50k at 10.10 ms); past it p99 193-665 ms, loader 96-98 % correctly ignored | P:178 |
| `2026-09-24-cal-j-arm-tiered` | CAL 3: arm-tuned tiered ON, no code-cache flags | knee 70k vs 80k with CMP333 bundle → keep CMP333 on arm | P:179 |
| `2026-09-24-cal-j-arm-h32` | CAL 4: Hikari 32 | knee 70k (80k at 10.09 ms, boundary noise); pools never the limit (pending 0, active ≤ 7, Tomcat busy ≤ 15/200) → defaults stay; the 10k step straddles the SLO, fine ladder + n=3 resolves it | P:180-181 |
| `2026-09-24-cal-go-arm`, `-go-x86` | CAL 5/6: Go sort ECHO_N 1e4 | arm 35k, x86 20k; both CPU-bound (14.7-15.0 cores); Graviton 1.75x; ECHO_N 10000 stays | P:183 |
| `2026-09-24-cal-j-x86-tiered` | CAL 7: x86-tuned tiered ON | knee 50k (6.25 ms at 50k vs 10.10 with CMP333), first rejected by loader 98 % at crossing with SUT at 15.1/15 → SUT_SATURATED waiver, re-judged valid | P:185-186 |
| `2026-09-24-cal-llama-arm` | CAL 8: llama arm-tuned official image | 108.8 tok/s (gate 114.7); system_info shows NEON, i8mm, SVE, DOTPROD, REPACK, no KLEIDIAI | P:188 |
| `2026-09-24-cal-llama-x86` | CAL 9: llama x86-tuned (-t 8) | system_info AVX512 (+VNNI, BF16), AMX_INT8: official image carries Xeon's best path but not Graviton's (KleidiAI) — fairness asymmetry | P:189 |
| `2026-09-24-cal-llama-x86t15` | CAL 10: x86 -t 15 | 57.5 tok/s vs 40.6 with -t 8: SMT helps x86 inference by 42 % → tuned x86 = -t 15 | P:191-192 |
| `2026-09-24-cal-llama-kleidiai` | CAL 11: own KleidiAI arm64 build | 105.2 vs 108.8 tok/s: no gain on cached-prompt decode (bandwidth-bound; KleidiAI targets matmul/prefill); kept as evidence, not in Task 7 | P:193-194 |
| `2026-09-24-cal-net-arm` | CAL 12: net arm-tuned | 16.89 Gbps both ways; baseline 0.048 cores, fwd 1.007, rev 0.536; 60 s baseline OK | P:195 |
| `2026-09-24-cal-mongo-arm` | CAL 13: Mongo arm-stock 10M ops/step | knee 128 threads (~203k ops/s, READ p99 2.94 ms); NOT CPU-bound (8.7/15 cores), throughput falls past the knee | P:196 |
| `2026-09-24-cal-loadercheck` | 1 vs 2 k6 at fixed 70k | 1 k6: p99 6.59 ms, 0.22 % dropped, loader 37 %; 2 k6: p99 5.73/5.77 ms, loader 41 % → two generators | P:198, loadercheck.json |
| `2026-09-24-cal-loadercheck-vu8000` | 1 k6 with PREALLOC 8000 | p99 47 ms, 0.32 % dropped → worse; PREALLOC stays 2000; drops look SUT-side | P:198 |
| `2026-09-24-cal-mongo-tickets` | Mongo 8.0.29 tickets polled every 5 s | read tickets 24-41 (dynamic), in-use ≤ 8 through 256 threads; queued time 12.9 s @128, 163 s @256, 742 s @512 → admission control explains the collapse past the knee, not the plateau; hot-key hypothesis rejected (uniform distribution) | P:203 |
| `2026-09-25-cal-mongo2client` | 1 vs 2 go-ycsb at 128 threads | 191.1k → 242.2k ops/s (+27 %), p99 2.71 → 1.68/1.70 ms, loader 54 → 71 % → the plateau was largely the single client | P:209, mongo2client.json |
| `2026-09-25-cal-j-amd-tuned` | Java amd-tuned (tiered on) | knee 90k (100k at 28.9 ms); per $/h n=1: Graviton 102k, AMD 92k, Xeon 59k | P:206 |
| `2026-09-25-cal-j-amd-cmp333` | Java amd-tuned CMP333 | knee 90k too, lower p99 at 50-90k → amd-tuned = CMP333 (`3fdc6df`) | P:207 |
| `2026-09-25-cal-go-amd` | Go amd-stock | 30k, 14.8 cores (CPU-bound); vs Graviton 35k / Xeon 20k | P:208 |
| `2026-09-25-cal-llama-amd` | llama amd-tuned -t 15 | 78.1 tok/s; AVX512+VNNI+BF16, no AMX; $3.46/Mtok vs Graviton $2.00 / Xeon $4.09; no thread sweep run | P:208 |
| `2026-09-25-cal-pg-arm/-amd/-x86` | PostgreSQL 18.6, scale 1000 (15.7 GB), select-only, stock + tuned (shared_buffers 16GB, no THP) | stock knees: arm 289.6k, amd 498.7k, x86 273.8k tps; tuned +4.6 / +5.4 / +9.5 %; harness clean (loader ≤ 13 %); open: arm-stock plateau at 12.7 cores | P:240-248 |
| `2026-09-26-cal-pg-thp` | PG tuned + THP for shmem | arm 337.2k (+11.3 %), amd 590.3k (+12.3 %), x86 334.2k (+11.5 %); 93.6-93.7 % shmem on 2 MiB pages; wait events at 256 clients: ~241 of 256 backends in ClientRead (closed-loop round-trip bound, no lock waits) | P:285-287 |
| `2026-09-26-ab-pg-clients` | PG arm-stock fixed runs at 1x vs 2x knee clients | 1x: SUT 12.8-13.2 cores, BufferMapping 1.6-1.7 vs 14.2-14.4 and 5.8-9.2 at 2x; run-2 still had one stall (lag 2.86 s) attributed to stock PG itself → 1x adopted | P:302 |

Calibration summary line, all n=1: P:219-220.

---

## 4. Incidents and what they taught

| Incident | What happened | Lesson / fix | Source |
|---|---|---|---|
| Hung `codex exec` | Session lost ~9 h overnight: codex waited on open stdin in a background shell | Pipe the prompt via stdin | P:69 |
| Process restart mid-apply | Claude Code restarted during the first `terraform apply`; the apply survived. Controller wrongly ran force-unlock and deleted the lock info + plan file (harmless) | Check `pgrep -f "terraform apply"` before any recovery step | P:135 |
| First apply failed 119/123 | EBS CSI policy ARN spliced wrong (`service-role/` + `V2`); Karpenter managed policy > 6144 chars (quota not adjustable) → inline policy | The controller's own diagnosis was also wrong: V2 exists at a different path; implementer corrected it. Fact sheets are a head start, not a substitute | P:137, P:140, SDD/gha-oidc-report.md:25-60 |
| CI could not reach EKS API | helm_release.karpenter timed out: endpoint allow-list = laptop /32 | CI must never need the k8s API; Karpenter moved to a laptop step | P:145-146 |
| Vacuous loader guard | `kubectl top node` accepts one name; sampler passed two, failed silently, loader peak read 0 in both gate ladders | Fixed `28817fa`; later fail-closed on missing telemetry (`52cd91a`, `2522f02`) | G:40, P:149, P:169-171 |
| Leak check would block destroy | Root disks matched the Project tag; check now filters status=available | `25a57b3` | P:154 |
| Teardown hang | `--teardown-day` hung on the PVC protection finalizer while Pyroscope still mounted it | Uninstall Pyroscope before deleting PVCs (`f4824d9`) | P:154, P:163 |
| API-server proxy timeouts | Node SG admitted only 443/10250/webhooks from the cluster SG → actuator/cpuset checks failed | `16eb806` | P:176 |
| Session restart mid-CAL3 | Scratchpad lost; the runner process survived, results intact | Runner outlives the agent session | P:182 |
| pytest touched the live cluster (2026-09-25) | An implementer's pytest run (before its mock fix) applied two YCSB **Jobs** to the live cluster (not infra); found Pending and deleted | `conftest` guard: no test may run kubectl/aws/helm/terraform for real (`41a8870`) | P:210 |
| Hand drain → CI apply 409/400 | Loader/tools scaled to 0 by hand overnight; next CI apply failed: MNG replaced create-before-destroy collides on the fixed name (409), tools min 1 > desired 0 (400); agent's node-group ops blocked by the auto-mode classifier, speaker approved the manual fix | "Do not drain loader/tools by hand again"; final parking done with `fd07c5d` (min 0) | P:210, P:232, P:238, P:336, P:390 |
| StatefulSet forced rollback | After the arm node scaled away, postgres-0 recreated from the OLD revision (Pending) and RollingUpdate never replaces a non-Ready pod; PG amd-stock calibration timed out | DB cells scale their sts to 0 and wait before applying (`0be77c8`) | P:241 |
| x86-tuned Java cell failed (day 1) | postgres-0 (selector x86-tuned, left by calibration) scheduled first on the SUT node and took 15 CPU/56Gi; Java deploy exceeded its progress deadline ($0.20 lost) | Every cell parks every DB sts it does not measure (`14c19da`); cell re-run | P:264, P:270 |
| SSO expiry #1 (day 1, ~02:15Z) | java/x86-smtoff failed mid-knee; cleanup failed without credentials; node group probably left at desired=1 | Deadline file; chain refuses new cells past it | P:265-266 |
| SSO expiry #2 (day 3, 01:37Z) | Token died 80 min before the deadline; the 16:57Z auto-renew did not extend it. Guard stopped cleanly between cells (no stranded node) | Guard also renews when `sts` fails | P:381 |
| SSO expiry #3 (09-28) | First desiredSize=0 attempt failed silently on an expired token | Sessions shorter than the assumed 12 h: check creds before every AWS step | P:390, P:394 |
| Invalid runs re-judged | amd-stock run-1 (0.10 %) and arm-tuned-vthreads runs 1-3 invalid under 0.1 %; amd-tuned-vthreads ran on old code | Re-judged under 0.25 %, originals kept as `invalid_before_rejudge` | P:261, P:268-269 |
| Never-crossed bug | `6288f82` compared the knee with itself → PG THP cells flagged `ladder_never_crossed` | `b3094f3`; knee.json/cell.json re-judged | P:285-286 |
| Mongo EBS-bound fixed runs (day 2) | gp3 125 MiB/s saturated; knee steps (~45 s) ended before it showed; chain stopped with SIGINT (finally scaled arm-tuned to 0); runs set aside in `mongo-ebs125/` | Volume raised; knee held; fixed runs valid | P:295-297, P:310 |
| Inference arm-tuned day 2 | 101.8 / 100.0 / 95.0 tok/s, falling run over run (cal 108.8); stock very stable. Cause **not established** in the sources; flagged as outlier-pass candidate. Day 3: 108.0 (= calibration) | Second day resolved it | P:304, P:345, P:373 |
| eBPF profiles without user stacks | PostgreSQL (Debian binary stripped), mongod and llama.cpp profiles show kernel frames only (no frame pointers); Java profiles full (~4200 CPU-s, real frames) | Only Java flame graphs are slide material as-is | P:250, P:295, P:393 |
| uv console script loses its .pth | macOS UF_HIDDEN on `.pth`; `cell` entry point breaks | Run `uv run --no-sync python cell.py` | P:92, P:239, P:359 |
| rtk hook truncates tool output | grep/wc/helm/git log output silently truncated for agents | Use `rtk proxy` or python for exact output | P:79, SDD/karpenter-helm-out-report.md:25 |

---

## 5. Learnings for the audience ("benchmarking CPUs on Kubernetes")

1. **Your load generator is a suspect until proven otherwise.** Gate: c7i.4xlarge hit 98 % CPU at 90-100k rps while the SUT was still under SLO (G:48-57). One k6 process added ~0.8 ms (+13 %) to p99 at 70k rps (P:198). One go-ycsb client capped Mongo at 191k; two gave 242k (+27 %) (P:209). Loader went c7i.4xlarge → c7i.8xlarge → c8i.16xlarge (P:150, P:224).
2. **A guard that fails silently is worse than no guard.** The loader guard read 0 % for a whole gate day because of a CLI argument quirk (G:40); fixed to fail closed (P:169). The pgbench pod guard had to fail closed too (P:236).
3. **Define "knee" before you look at the data, and fix the definition when the data breaks it.** Open-loop (k6) knee = last step under the SLO, judged per step (P:108, P:167). Closed-loop DBs can peak and fall without crossing the SLO (AMD PG 487.7k → 419.4k tps), so the knee became the throughput peak under the SLO (P:242).
4. **Tail latency drops need a rate threshold, set with data.** "Any drop invalidates" failed at the gate (0.05 %, G:63); 0.1 % failed on day 1 (0.048-0.124 %, rising with rps, not latency); 0.25 % adopted and every run re-judged with the originals kept (P:268).
5. **Pin CPUs and park everything else.** Static CPU Manager, 15 exclusive CPUs, cpuset verified per run (P:82, G:34). A forgotten postgres pod silently took a Java node (P:264).
6. **Stock is not "untuned"; tuning is not always a gain.** PG shared_buffers 16 GB alone gained only 4.6-9.5 % because 4 KiB pages cost 23-28 % of PG CPU; THP for shmem made it +20-22 % (P:248, P:250, P:318-321). The network "tuning" (runbook latency advice) doubled send-side CPU on arm/amd at identical Gbps, because iperf3 measures throughput, not latency (P:290-294). Mongo THP gave nothing measurable (P:323).
7. **"Best flags" differ per chip.** Tiered compilation ON won on x86 (50k vs 40k), the CMP333 bundle won on arm (80k vs 70k) and AMD (P:186-187, P:207). Inference: SMT helped x86 by 42 % (P:191); KleidiAI gave no decode gain (P:194).
8. **Check what the official image actually dispatched.** llama.cpp's official image had AMX for Xeon but no KleidiAI for Graviton (P:188-189).
9. **Storage can hide inside a "CPU" benchmark.** Mongo's knee was right but 8-minute fixed runs were gp3-throughput-bound (131 MB/s flat); short knee steps did not show it (P:295, P:310).
10. **Your harness can create the contention you measure.** PG fixed runs with 2x clients produced BufferMapping waits and multi-second schedule lag that vanished at 1x (P:300-302).
11. **Some databases stop before the CPU.** Mongo ran 8.7/15 cores at its knee; admission-control tickets explain the collapse past it (P:196, P:203, P:209).
12. **One day, one node is not enough for near-ties.** Calibration vs Task 7 moved 0-8 % (P:350); PG tuned arm vs x86 flipped between days (d2 arm +0.7 %, d3 x86 +3.9 %) (P:376); arm-tuned inference was noisy on day 2 and clean on day 3 (P:373).
13. **Credentials expire mid-benchmark; design for it.** Three SSO expiries (P:265, P:381, P:394); a deadline guard that stops between cells avoided stranded nodes (P:381).
14. **Tests must not reach production... or the lab.** A pytest run applied Jobs to the live cluster (P:210).
15. **Show the losses.** AMD leads PostgreSQL raw and per $ (P:349); Graviton leads Mongo by ~28 % (P:384).

---

## 6. Honest caveats and threats to validity (as recorded)

- **Single region and AZ**: us-east-1, one nodes subnet/AZ for every node group (spec:58, P:129).
- **On-demand prices only**, captured from the pricing API on given dates (cost.md:28-35). Per-$ claims use on-demand us-east-1 (P:349).
- **One node per cell per day**; two days per cell only for the day-3 set (P:342, P:333, P:370-386). Net, x86-smtoff and x86-t8 have one day only (P:358 list excludes them).
- **Day-to-day drift 0-8 %** between calibration and Task 7 (P:350); near-ties need "within noise" labels (P:361, P:376).
- **Calibration numbers are n=1** and are not headline material (P:219, G:78).
- **Loader limits**: guard at 70 %; waiver only at the crossing step when the SUT is saturated (P:185); fixed runs still judged whole-run.
- **Mongo** is not CPU-bound at the knee (P:196); results depend on 2 YCSB clients (P:209) and on the raised EBS volume (16000 IOPS / 1000 MiB/s), which is outside Terraform and was reverted on 2026-09-28 (P:297, P:337, P:395). Mongo is meant to run in cache (spec:28).
- **PostgreSQL** is select-only, scale 1000, closed-loop round-trip bound at the knee (~241 of 256 backends waiting on the client) (P:248, P:285). Knee client count is noise; report tps (P:312). Huge pages stay `try`/off; THP shmem is the tuned mechanism (P:285).
- **Network** throughput is the instance cap on every run (m9g 16.89, m8a/m8i 14.89 Gbps); the silicon metric is CPU per Gbps; the tuned knob's latency benefit was not measured (P:294, spec:106).
- **Inference** fairness asymmetry: official image has AMX for Xeon but no KleidiAI for Graviton (P:189); arm stock oversubscribes by one thread (default 16 threads on 15 exclusive CPUs) (P:303).
- **Profiles**: eBPF has no user stacks for llama.cpp, PostgreSQL, mongod (P:393). APerf on Intel exposes PMU only partially (L2/L3/TLB, backend stalls read 0) (G:76).
- **4xlarge slice**: memory bandwidth of 16 cores, not the full socket (spec:105).
- **Tuned Java flags differ per chip by ruling** (P:187); "same flags" in spec §3.5 is stale.

---

## 7. Cost history

Rates (cost.md:28-35): m8i.4xlarge $0.84672, m8a.4xlarge $0.97376, m9g.4xlarge $0.78272, c8i.16xlarge $2.99872, m7g.large $0.0816, EKS control plane $0.10/h; per-day gate `estimate_per_day_usd` 80 (cost.md:37). c7i.8xlarge was $1.428/h (P:163).

**Runner ledgers** (SUT = sum of cell rows; "total" adds a modeled fixed line of `fixed_hours_per_day: 6` × loader+tools+control plane, cost.md:38, 53-58):

| Results dir | Spent on | SUT USD | Ledger total USD |
|---|---|---|---|
| 2026-09-04 | Smoke gate: inference, Java arm/x86, Mongo, net (loader c7i.4xlarge) | 1.13 | 6.51 |
| 2026-09-24-cal-* (13 dirs) | Java/Go/llama/net/Mongo calibration (loader c7i.8xlarge) | 0.18-0.36 each | ~9.9 each |
| 2026-09-25-cal-{go,j-amd-*,llama}-amd (4 dirs) | AMD calibration | 0.25-0.42 each | ~10.0 each |
| 2026-09-25-cal-pg-{arm,amd,x86} | PG calibration (loader c8i.16xlarge) | 0.41-0.49 each | ~19.5 each |
| 2026-09-25-task7-d1 | Go 3 + Java 10 cells | 11.16 | 30.25 |
| 2026-09-26-cal-pg-thp | PG THP A/B | 0.66 | 19.74 |
| 2026-09-26-ab-pg-clients | PG 1x vs 2x clients | 0.41 | 19.50 |
| 2026-09-26-task7-d2 | net 6, Mongo 6 (+ EBS-bound arm-stock and interrupted arm-tuned), PG 6 at 1x (+ 2 at 2x), inference 7 | 14.57 | 33.66 |
| 2026-09-27-task7-d3 | Go 3, Java 9, inference 6, PG 6, Mongo 6 | 20.08 | 39.17 |

(SUT sums computed from the ledger rows; every ledger shows "OK" against $80.)

**Recorded real-cost figures**
- Cost Explorer posted $113.74 through 2026-09-26 (lagging); controller's estimate ~$175 incl. overnight idle; "Task 7 ≈ $185" (P:340). No later total is recorded.
- Idle cluster cost: loader c8i.16xlarge + tools + control plane ~$3.18/h (P:330, P:336); earlier ~$1.6/h with c7i.8xlarge (P:177), ~$3.2/h (P:248).
- Parked (09-28): control plane $0.10/h (~$2.4/day), raised Mongo volume, PG volume, ECR storage (P:391).
- Lost cell: x86-tuned first attempt $0.20 (P:264).
- Plan estimate was ~$40-70 total (spec:26) and Task 7 "~$25-35" (plan:263); project $200 ceiling relaxed 2026-09-04 (P:129).

---

## 8. Open and deferred items

- **Analysis (checklist item 3)**: combine d1/d2 with d3 per cell, per-chip ratios with bootstrap intervals, "within noise" labels for near-ties (Java tuned arm~amd, vthreads arm=amd, PG tuned arm vs x86, Mongo x86 vs amd) (P:361, P:376, P:384).
- **Task 7 step 3-5 not done**: outlier pass, APerf stock-vs-tuned reports, real cost breakdown, results commit (plan:263-269). Results are local only and untracked (P:339, `git status`); backups in `charlas/_backups/` (P:386).
- **Sanitize-check real (Task 10 step 2)**: `demo/sanitize-check.sh` is still the stub; must be real before committing any result (P:339, plan:283-285).
- **Task 8 generational arc** m5→m8i / m6g→m9g via Karpenter, on-demand, single run each (plan:271-275, spec:155-157). Not started.
- **Task 9 DaemonSet blocker scene + Karpenter scale-from-zero clip** (plan:277-281). Not started; Karpenter is installed from the laptop only that day (P:146).
- **Task 11 slides / Task 12 README** (plan:287-300). Flame graph renderer `scripts/fg2svg.py`; Java arm/x86-tuned SVG+PNG exist in `results/2026-09-27-task7-d3/flamegraphs/` (P:393).
- **Before any new lab run**: restore loader/tools desiredSize=1; re-raise the Mongo volume ≥ 6 h after the 09-28 revert (EBS allows one modify per 6 h) (P:392, P:395).
- **Decisions still open**: R4 Mongo tickets A/B (optional) (P:227); arm-stock PG 12.7-core plateau explained only partially (wait events: closed-loop bound) (P:248, P:285); not yet on a real node at handoff time: x86-smtoff and amd-stock snapshots (P:221).
- **Deferred minors** (SDD/deferred-minors.txt:1-22, P:33-103): lib.js `env()` treats "" as unset; Go `http.Error` content type; redundant Go USER; ycsb full clone; missing Go boundary test; inference prompt without diacritics; `stageRates()` guard; build TAG recomputed per invocation; no image-name validation; README wording; endpoint public CIDR default; /28 control-plane subnet; control-plane log retention cost; helm_release depends_on (now moot, release removed); ManagedBy tag on arc nodes; README accents; root README "Pyroscope 2.3.0" (chart is 2.2.1, fix in Task 12); ethtool apk pin; Mongo 40 GiB cache vs 56 GiB limit; completed Jobs cleanup and knee invalid_reasons (partly addressed by final wave item #98, SDD/final-fix-wave.md:30); finally-block order; dead stats code. Also deferred: imagetools inspect called twice (P:124), GHA minors 6-8 (P:141), karpenter dnsPolicy/README inconsistencies (P:148), parked items P:114-117.

---

## Contradictions and stale text found between sources

1. **Spec PG fixed-run text is stale**: spec:122 still says fixed runs use "el doble de clientes que el knee" and judge schedule lag against a 1 ms budget; superseded by `960d17a` (1x) and `40fe64c` (lag recorded, not judged). `manifests/workloads/postgres/README.md:158-166` is updated.
2. **Spec §3.5 JVM** (spec:89) says the same flags on both architectures; ruling `9738034` made tuned = best per chip (x86 tiered on).
3. **Spec §3 table and plan architecture** still list loader `c7i.4xlarge` and MNG `max=1` (spec:58-72, plan:7); actual c8i.16xlarge (`24b1ede`) and max 2 (P:55). Spec/plan say Pyroscope 2.3.0; the deployed chart is 2.2.1 (P:78, G:30).
4. **Cluster lifecycle**: CLAUDE.md, spec:26 and plan:18 say the cluster is destroyed between lab days; it stayed up 2026-09-24 → 09-28 by speaker override (P:177, P:249) and was parked, not destroyed (P:389).
5. **Ledger fixed line vs reality**: every runner ledger charges a modeled 6 h fixed line (cost.md:38) per results dir, so calibration dirs each repeat ~$9.7-19 of "fixed" cost that did not happen 13+ times over, while the real cluster ran ~84 h continuously. Summing ledger totals is not the project cost; the only real figures are P:340.
6. **Mongo volume extra cost**: "~+$1.5/day" (P:297) vs "~$3.3/day above gp3 base" (P:391).
7. **Day 2 start time**: P:287 says ~08:3xZ; corrected in P:288 to 12:08Z.
8. **SSO session length**: P:338 assumes ~12 h; P:381 and P:394 show tokens dying earlier.
9. **R3 run count**: `runner/README.md:410` says "27 corridas fijas de Java del día 1"; the ledger at ruling time (P:268) lists the drop range but not a count, and only ~7-8 Java cells had finished by then (P:259-268). Not verified.
10. **Caller's brief vs sources**: "h10/h32" are Hikari pool sizes, not Java heap sizes (P:175, P:181, h32 cell.json). The 2026-09-25 pytest incident applied Kubernetes Jobs to the live cluster, not Terraform infra (P:210). Loader history is c7i.4xlarge → c7i.8xlarge → c8i.16xlarge, not directly c7i → c8i (P:150, P:224). The arm-tuned inference noise on day 2 is recorded as unexplained, not attributed to a noisy node (P:304).
11. **Git dates vs ledger dates** differ by the UTC-5 offset (e.g. `b9207f3`, `14c19da` dated 2026-09-25 in git, events logged 2026-09-26 Z).

## Update 2026-09-29

- §8 items closed: Task 8 generational arc (2026-09-28, 9 families incl. m8a, m8g on 2 nodes), Task 9 (Karpenter clip: m6g.4xlarge Ready in 30 s; DaemonSet scene: amd64-only agent Running on an m6i.4xlarge, `exec format error` on both arm64 nodes), bootstrap analysis (stats.md), real sanitize-check, IaC destroyed 2026-09-28 (127 resources).
- Corrections to this file: the net knob on x86 costs 1.2x CPU/Gbps (stats.md), not "~1.3x"; the llama.cpp `-t 15` gain on x86 is +18 % in Task 7 (+42 % was calibration n=1).
