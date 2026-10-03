# Decision guide: "I run X today, what do I gain?"

For a room with different stacks, not one answer. Each path says **when it fits**, **what it
gains** and **where it loses**, with every number tagged:

- **[M7]** measured, Task 7: 2 independent days × 3 fixed runs, best-settings per chip
  (`headline.md`, `stats.md`).
- **[M8]** measured, Task 8 arc: Java stock, 1 fixed run per family (m8g: 2 nodes, identical).
  Same scale as Task 7 (arc m9g 80k = Task 7 80k; arc m8a 90k = Task 7 88–90k; arc m8i 48k
  vs Task 7 46k).
- **[E]** estimated, formula shown. Not measured; say "estimate" on stage.

All sizes .4xlarge (16 vCPU) unless said; on-demand us-east-1 prices from `results/cost.md`
(Pricing API); no Savings Plans / Spot. Workload for the arc: Spring REST on JDK 25, stock JVM.

## The five questions (routing)

1. **Can my stack run on arm64?** Multi-arch images, every DaemonSet/agent too (Task 9 scene:
   an amd64-only agent crash-loops on Graviton with `exec format error`), no x86-only native
   libs, and vendor certification (example: Red Hat JBoss EAP 7.4 supported configurations list
   x86_64 only). No → paths 0, A, B. Yes → also C.
2. **What is my workload class?** Java/web, Go/network services, relational DB, document DB,
   CPU inference, network-heavy. The winner changes by class (table below).
3. **Where am I today?** Old Intel (m5, t3, t2), mid (m6i/m6g), recent.
4. **Runtime version?** JDK 8 leaves performance on the table on any new CPU, most of all on
   arm64; JDK 17+ first (EAP 7.4 supports 17 from Update 7).
5. **What do I optimize?** Cost per unit of work (per $) or headroom (raw throughput: fewer
   nodes, more burst, lower latency at the same load).

## Path 0: tune where you are (no migration) [M7]

Gain per chip, tuned ÷ stock, same node (stats.md; "clear" unless marked):

| workload | knob | arm (m9g) | amd (m8a) | x86 (m8i) |
|---|---|---|---|---|
| PostgreSQL | shared_buffers 16 GB + THP for shared memory | ~1.20x | ~1.20x | ~1.20x |
| Java | best JVM flags per chip | 1.10x | 1.01x (noise) | 1.15x |
| Java | + virtual threads (JDK 21+) | 1.24x over tuned | 1.21x | 1.06x |
| Inference (llama.cpp) | threads = pod vCPUs (`-t 15`) | 1.07x (lean) | 1.20x | 1.29x |
| MongoDB | THP | 1.00x (noise) | 1.00x (noise) | 1.03x |
| Network | "latency" knobs (IRQ pinning, adaptive-rx off) | **costs** ~2.2x CPU/Gbps | ~2.1x | ~1.2x |

Lesson: measure the knob on your workload; the network "tuning" from a latency runbook made
throughput work more expensive on every chip.

## Path A: newer Intel (stay x86, lowest-risk change) [M8]

From m5.4xlarge, Java stock:

| to | raw | per $ |
|---|---|---|
| m6i | 1.33x | 1.33x |
| m7i | 1.50x | 1.43x |
| m8i (Xeon 6) | 2.00x | 1.81x |

Fits: vendor-certified x86 stacks, JDK 8 that cannot move yet, zero-change migrations.
Loses to: m8a on raw everywhere except MongoDB (tie); to m9g per $ on 5 of 6 classes.
Why: at 4xlarge, m8i is 8 cores + SMT; m8a and m9g are 16 physical cores (`facts-setup.md` §1).

## Path B: AMD m8a (x86_64, drop-in, top raw throughput)

From m5, Java stock [M8]: **3.75x raw, 2.96x per $.**
Against m8i by workload class [M7] (raw / per $):

| Go | Java tuned | Java vthreads | Inference | PostgreSQL | MongoDB |
|---|---|---|---|---|---|
| 1.45x / 1.26x | 1.70x / 1.48x | 1.95x / 1.69x | 1.35x / 1.17x | **1.75x / 1.52x** | 0.97x (tie) / 0.84x |

Fits: must stay x86_64 (certified stacks, x86-only agents) and wants the biggest raw jump;
**the clear winner for PostgreSQL** (raw and per $, both days). Loses: MongoDB per $ (same
throughput as m8i at a higher price); per $ against m9g everywhere except PostgreSQL.

**On Spot the picture shifts toward AMD** [M7 × Spot]: with the weekly median in us-east-1
(2026-09-22..30: m9g $0.346, m8a $0.359, m8i $0.370 — m8a is cheaper than m8i on Spot, the
reverse of on-demand), per $ vs m8i becomes: Java stock m8a 1.99x vs m9g 1.86x, Java tuned
1.75x vs 1.77x (tie), PostgreSQL 1.80x vs 1.05x; Go, inference and MongoDB still favour m9g
(`headline.md`, Spot section). Spot varies a lot by AZ; quote it as a weekly median.

## Path C: Graviton5 m9g (multi-arch stacks, best per $)

From m5, Java stock [M8]: **3.33x raw, 3.27x per $.**
Against m8i and m8a by workload class [M7] (per $; raw in brackets):

| | Go | Java tuned | Java vthreads | Inference | PostgreSQL | MongoDB |
|---|---|---|---|---|---|---|
| vs m8i | 1.97x (1.82) | 1.80x (1.66) | 2.11x (1.95) | 1.96x (1.81) | 1.06x (0.98, tie) | 1.36x (1.26) |
| vs m8a | 1.57x (1.26) | 1.22x (0.98, tie) | 1.24x (1.00, tie) | 1.67x (1.34) | **0.70x (0.56)** | 1.61x (1.30) |

Fits: images and agents are (or can be) multi-arch, JDK 17+, cost per unit of work matters.
Loses: PostgreSQL (AMD is ~1.8x raw); in Java raw it ties m8a (the per-$ win is the price gap:
"same speed, cheaper", not "faster").

The Graviton line itself [M8] (from m5, raw / per $): m6g 0.92x / 1.14x · m7g 1.08x / 1.27x ·
m8g 1.67x / 1.78x (2 nodes, 40k both) · **m9g 3.33x / 3.27x**.
- m9g ≈ 2.0x m8g on this Java workload, reproduced on 2 m8g nodes. Broad suites report
  +25–36 % (AWS "up to 25 %", Phoronix +30 % geomean, Honeycomb production 11–26 % less CPU).
  Say both: "on our workload 2x; across suites ~30 %; your workload decides."
- Karpenter picks by price: the Task 9 clip got **m6g** (cheapest; Graviton2, GA 2020) for a pod with no
  constraints. Without pinning families you get 0.92x m5 raw, not 3.33x.

## Burstable today (t3, t2) [E]

Formula: per-vCPU performance relative to m5 = CPU factor × (1 while bursting, or the
baseline when out of credits). t3 and m5 share the processor generation (AWS: "Skylake-SP or
Cascade Lake"; the EC2 table lists both as Skylake P-8175) → factor 1.00. t2.xlarge/2xlarge run
Broadwell E5-2686 v4. AWS put m5 at +14 % price/performance per core over m4 (m4.4xlarge =
Haswell E5-2676 v3) → +9.4 % raw at m5's price → **t2 factor 0.91, a lower bound** (Broadwell
is one step newer than that Haswell base). Baselines per vCPU from the EC2 credit table:
t3 large 30 %, xlarge/2xlarge 40 %; t2 large 30 %, xlarge 22.5 %, 2xlarge 17 %.
Targets use the measured per-vCPU throughput of the arc [M8]. Linear per-vCPU scaling is
assumed (a 2xlarge is treated as half a 4xlarge).

Which row are you? Check `CPUCreditBalance` in CloudWatch: stays high → **bursting** row;
sits near 0 (or unlimited mode keeps billing surplus credits) → **sustained** row.

| from | to m8i: raw / per $ | to m8a: raw / per $ | to m9g: raw / per $ |
|---|---|---|---|
| t3 (bursting) | 2.0x / 1.6x | 3.8x / 2.6x | 3.3x / 2.8x |
| t3.xlarge–2xlarge (out of credits, 40 %) | 5.0x / 3.9x | 9.4x / 6.4x | 8.3x / 7.1x |
| t2 (bursting) | 2.2x / 1.9x | 4.1x / 3.1x | 3.7x / 3.5x |
| t2.2xlarge (out of credits, 17 %) | 12.9x / 11.3x | 24.1x / 18.4x | 21.5x / 20.4x |

Read the sustained rows as "you are on the wrong instance class", not as a benchmark result.
If average CPU stays under the baseline, a t-series is still the cheapest place to idle.

## Example routes (the sentences for the room)

- **x86-certified Java (e.g. EAP 7 on m5), must stay x86** → JDK 17 first, then m8a:
  ~3.75x raw, ~3x per $ [M8]; m8i if you want the smallest change: 2x raw, 1.8x per $ [M8].
- **Multi-arch Java/Go microservices on m5** → m9g: ~3.3x raw and per $ [M8]; Go at the knee
  1.8x m8i raw [M7]. Pin the instance family in Karpenter.
- **PostgreSQL on x86** → m8a, then tune (THP for shared memory + shared_buffers): 1.75x m8i
  raw [M7] × ~1.2x tuning [M7].
- **Document DB (MongoDB-like)** → m9g: 1.26x raw, 1.36x per $ vs m8i [M7]; AMD and Intel
  tie there.
- **CPU inference (llama.cpp-class)** → m9g: 1.81x raw, 1.96x per $ vs m8i [M7]; set threads
  to the pod's vCPUs on every chip (+7–29 %). The metric is generation throughput; for prompt processing x86 wins big (AMX /
  AVX-512: Spare Cores has m8a/m8i ~2.5x m9g), so long-prompt RAG leans x86.
- **Microservices on t3/t2 that mostly idle** → stay burstable or move to t4g; if
  `CPUCreditBalance` sits at 0, you are paying for the wrong class (sustained rows above) [E].

## Caveats to say out loud

- One region/AZ, on-demand prices, one node per cell per day (Task 7) or one run per family
  (Task 8). Day-to-day drift 0–8 %.
- The arc is Java stock only; other workload classes come from Task 7 (m8i/m8a/m9g only).
- llama.cpp image (b10775): AMX kernels on Xeon; on Graviton the Arm i8mm repack kernels are
  on and only the KleidiAI path is off. "No Arm optimization" would be false.
- MongoDB is not CPU-bound at the knee; its ties say little about the chips.
- x86-smtoff also changed JIT flags (not a clean SMT-only comparison).
- Per-core software licensing (and vendor certification) can outweigh any per-$ number here.

Sources: `headline.md` (generated), `stats.md`, `data/cells.csv`; EC2 burstable credit table
(docs.aws.amazon.com/AWSEC2/latest/UserGuide/burstable-credits-baseline-concepts.html,
2026-09-28); M5 launch (aws.amazon.com/blogs/aws/m5-the-next-generation-of-general-purpose-ec2-instances);
Red Hat EAP 7 supported configurations (access.redhat.com/articles/2026253, fetched 2026-09-28);
Phoronix (phoronix.com/review/aws-graviton5); Honeycomb m8g→m9g (2026-06-10).
