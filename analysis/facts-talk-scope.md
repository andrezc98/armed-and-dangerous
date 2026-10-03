# Facts: talk scope (what was promised, what exists, what answers it)

Internal, English. Read-only survey done 2026-09-28. Path abbreviations:
- `RECAP` = `../kcd/kcd-argentina-2026-brainstorm-recap.md`
- `SPEC` = `docs/superpowers/specs/2026-09-02-armed-and-dangerous-design.md`
- `PLAN` = `docs/superpowers/plans/2026-09-02-armed-and-dangerous.md`
- `LEDGER` = `.superpowers/sdd/2026-09-02-armed-and-dangerous/progress.md`
- `GEN` = `slides/visuals/src/gen.py`

**Stale-claim flag.** RECAP:223 ("No public Graviton5 inference numbers exist yet ... the lab's data would be novel") and RECAP:309 ("casi no hay evidencia pública de qué rinde de verdad la inferencia de LLMs sobre estos nodos") are outdated: Spare Cores published llama.cpp on every m9g size on 2026-06-12 (SPEC:48, SPEC:178; CLAUDE.md:36-37). The angle that still holds is "x86 vs Graviton5 in the same EKS cluster, with $/Mtok" (SPEC:48). Never repeat the "first public evidence" line. The RECAP:309 sentence is in the submitted "¿Qué problema resuelve?" field, so it cannot be edited now. Just don't put it on a slide.

---

## 1. The abstract as submitted (ACD Perú, the talk being given)

Title (RECAP:297; SPEC:4 "published, immutable"):

> ARMed and Dangerous: lo que Graviton5 hace con tus workloads, medido en EKS

Description (RECAP:301-305, verbatim):

> Todos escuchamos la promesa: Graviton ofrece mejor precio-rendimiento. Y este año la apuesta subió: Graviton5 ya está disponible en general, con 192 núcleos por socket, la memoria DDR5 más rápida de la nube y un mensaje de marketing claro: está construido para la era de la IA agéntica. Lo que casi nadie hace es medir qué significa todo eso para su propio workload.
>
> Esta charla lo mide en EKS. Tres clases de workload en el mismo clúster, con node groups x86 y Graviton: una aplicación Java de alta concurrencia (donde importa que un vCPU de Graviton sea un núcleo físico y no un hermano de hyperthreading), MongoDB (que vive del ancho de banda de memoria) y la nueva: un modelo open-weight cuantizado corriendo con Ollama sobre CPU, midiendo tokens por segundo y costo por millón de tokens. Para cada una muestro el número y el porqué, con profiling continuo de eBPF y flame graphs que enseñan adónde se va el tiempo en cada arquitectura. De yapa: la evolución generacional medida, de m5 a M9g.
>
> La charla es deliberadamente angosta y profunda: tres workloads, tres porqués, y una regla de decisión por clase de workload. La audiencia se lleva: un criterio medido para decidir qué corre en ARM y qué no (incluyendo si tu modelo local de IA puede vivir en los nodos que ya pagas), el harness open source completo (k6, Prometheus, Pyroscope, buildx multi-arch, Karpenter) para repetirlo todo en su propia cuenta, y el camino de migración real en EKS: node groups mixtos, Spot más Graviton, y el bloqueador del que nadie habla: los DaemonSets. Todos los números son propios; donde cito a terceros, son mediciones independientes, no marketing.

"¿Qué problema resuelve?" (RECAP:309, verbatim):

> Migrar a Graviton promete hasta 25% más rendimiento y menor costo, pero la mayoría de los equipos decide con benchmarks de marketing o no decide nada: deja plata sobre la mesa o migra workloads que rinden peor en ARM. Y con Graviton5 vendido como el CPU para la era de la IA agéntica, casi no hay evidencia pública de qué rinde de verdad la inferencia de LLMs sobre estos nodos. Esta charla aborda las dos necesidades con mediciones propias y reproducibles: qué clase de workload gana en ARM, cuál no, y por qué.

Dropdowns: Cloud Architecture, level 300, demo: sí, morning slot (RECAP:311). Format 30 min (RECAP:263; SPEC:3).

The Argentina v1 abstract (RECAP:205-213) promised "un servicio Go como control" (RECAP:211) and the same eBPF/OTel Profiles, generational arc, k6/Prometheus/Pyroscope/buildx/Karpenter, mixed node groups, Spot+Graviton and DaemonSets items (RECAP:211-213). Per SPEC:5 the Go baseline fulfils the v1 promise. Argentina is past (2026-09-12), so this only matters for AWS Women Colombia, which reuses §11b (RECAP:319) with a different closing line (RECAP:351).

### Concrete promises the audience was told to expect (P#)

| P# | Promise | Source |
|---|---|---|
| P1 | Graviton5 GA context: 192 cores/socket, "fastest DDR5 in the cloud", "built for the agentic AI era", framed as claims to be measured | RECAP:301 |
| P2 | Measured on EKS, same cluster, x86 and Graviton node groups | RECAP:303 |
| P3 | High-concurrency Java app: physical core vs hyperthreading sibling | RECAP:303 |
| P4 | MongoDB as the memory-bandwidth workload | RECAP:303 |
| P5 | Quantized open-weight model on CPU "con Ollama": tok/s and $ per million tokens | RECAP:303 |
| P6 | "El número y el porqué" for each workload: continuous eBPF profiling plus flame graphs per architecture | RECAP:303 |
| P7 | Generational arc measured, m5 to M9g | RECAP:303 |
| P8 | Three workloads, three whys, one decision rule per workload class | RECAP:305 |
| P9 | Measured criterion for what runs on ARM, including "si tu modelo local de IA puede vivir en los nodos que ya pagas" | RECAP:305 |
| P10 | Full open source harness: k6, Prometheus, Pyroscope, buildx multi-arch, Karpenter, repeatable in their own account | RECAP:305 |
| P11 | Real EKS migration path: mixed node groups | RECAP:305 |
| P12 | Spot plus Graviton | RECAP:305 |
| P13 | The DaemonSet blocker | RECAP:305 |
| P14 | All numbers own; third-party numbers are independent measurements, not marketing | RECAP:305 |
| P15 | "Hasta 25% más rendimiento": which workload class wins on ARM, which doesn't, and why | RECAP:309 |
| P16 | Demo: yes (dropdown) | RECAP:311 |

Wording drift to handle on stage:
- **"con Ollama"**: the lab runs the official llama.cpp server image, not Ollama (SPEC:105). Ollama wraps llama.cpp, so one sentence on stage covers it.
- **"Prometheus"**: dropped from the lab and replaced by metrics-server + APerf. SPEC:79 and SPEC:210 say to state this on the harness slide.
- **"x86 y Graviton"**: the lab now also has an AMD column (m8a, SPEC:66-67, SPEC:73) and PostgreSQL (SPEC:113-131). Neither is in the abstract. Both are additions and don't break it.

---

## 2. The spec's planned talk structure

### Time map (SPEC:31-43; 30 min split 2/4/19/5)

| Block | Min | Planned content | Source |
|---|---|---|---|
| Apertura | 2 | Title, self-intro, the promise (G5 GA, 192 cores, DDR5-8800, "up to 25% over G4"), "hoy sí" | SPEC:37 |
| Contexto | 4 | vCPU ≠ vCPU (m8i 8 cores + SMT at 3.9 GHz vs m9g 16 cores at 3.3 GHz, same size, Graviton ~8% cheaper); knobs: three on x86, one on Graviton; fairness = stock + best config per chip | SPEC:38 |
| Desarrollo | 19 | Method + how we read the why (3) → Java (4, 5 cells, twist = virtual threads) → MongoDB (2.5) → Inference (2.5, tok/s + $/Mtok) → Net (2, CPU per Gbps) → Go (1) → arc (1) → migration (3: mixed node groups, Karpenter clip, Spot, DaemonSets with three live examples) | SPEC:39 |
| Aprendizajes | 5 | Decision rule per class, what we didn't measure, the harness is yours, "este lab costó $X", close | SPEC:40 |
| Q&A | 5-10 | Feedback QR. Prepared answers "¿por qué no m7i?" and "¿y AMD?". The AMD answer (SPEC:41, "fuera de alcance") is **stale** since the 2026-09-25 AMD amendment (SPEC:73) | SPEC:41 |

Cut order if rehearsal runs over: slide 19 (arc → one sentence on slide 3), then slide 12 (vthreads → speaker note) (SPEC:43; PLAN:291, PLAN:316). Cut order for lab cells, now moot: net → Go → arc → x86-smtoff → vthreads (PLAN:24).

Headline candidates (to be confirmed by data, SPEC:45-48):
- "Misma talla, mismo clúster, otro silicio: 8 núcleos con SMT a 3.9 GHz contra 16 núcleos a 3.3 GHz." (SPEC:46)
- "x86 necesitó tres perillas para llegar donde Graviton arranca", only if the data says so, with the inverse version also prepared (SPEC:47).
- Inference: x86 vs Graviton5 in the same EKS cluster with $/Mtok. Not "first public evidence" (SPEC:48).
- Closing: "Graviton no es más rápido ni más barato: es distinto. Mide el porqué, no el cuánto." (SPEC:50)

### Planned deck, 25 content slides (SPEC:168-170)

1 Título · 2 Contenido · 3 La promesa (G5 GA, 192 cores, DDR5-8800, 25/30/35%) · 4 vCPU ≠ vCPU · 5 Las perillas (EC2 quote) · 6 El lab (diagram) · 7 Metodología como historia · 8 Cómo leemos el porqué: APerf + flame graph · 9 Java setup · 10 Java knee per cell (5 bars) · 11 Java why (APerf stock vs tuned vs SMT off) · 12 Virtual threads · 13 MongoDB setup · 14 MongoDB knee + why · 15 Inference setup · 16 Inference tok/s + $/Mtok · 17 Net iperf3, CPU per Gbps · 18 Go · 19 Generational arc m5→M9g · 20 Migration: mixed node groups + Karpenter (clip) + Spot · 21 DaemonSets blocker (scene, three examples) · 22 Decision rule + what we did NOT measure · 23 El harness es tuyo · 24 Este lab costó $X · 25 Aprendizajes + cierre · Q&A · ¡Gracias!

Deck gaps against the current lab: there is **no PostgreSQL slide** and **no AMD column** in the deck plan, even though both are in the lab now (SPEC:66-73, SPEC:113-131). The loader in SPEC:70 (c7i.4xlarge) is stale: the lab used c8i.16xlarge (results/cost.md:33; README.md:30).

### Planned live demos / recorded scenes

The spec rules that nothing on stage depends on WiFi and every demo has a recorded plan B (SPEC:24). Planned items:
- **Karpenter clip**: scale-from-zero with pods that have no affinity. Shows which type Karpenter picks and at what price, and says "por precio" because Karpenter has no performance signal (SPEC:76, SPEC:162; PLAN:280). Recorded; together with the DaemonSet scene, under 2 min.
- **DaemonSet blocker scene**: apply an amd64-only DaemonSet to the mixed cluster, get ImagePullBackOff/CrashLoopBackOff on Graviton, the rollout freezes. Three live examples: the eBPF profiler (multi-arch), the C-states DaemonSet and the net-tuning DaemonSet (amd64-only / tuned-only by design) (SPEC:93, SPEC:164; PLAN:279). Recorded.
- **Plan B recording** `demo/record.md`: 1080p terminal + Pyroscope + APerf report from Task 7 + the Task 9 scenes, under 4 min (PLAN:285).
- Generational arc: Java short fixed run per generation via the Karpenter NodePool, n=1, "the arc, not the number" (SPEC:157; PLAN:273-274).

### Planned visuals (SPEC:172; PLAN:293)

Architecture diagram (official AWS icons), exported flame graphs, matplotlib charts from committed JSON, Pyroscope screenshots, APerf HTML report screenshots, plus `slides/fuentes.md` with a date and URL for every figure (SPEC:21, SPEC:172; PLAN:292). Style rule from memory: re:Invent 2025 look, light background, no AWS logo or wordmark, official icons recolored to the gradient, delivered as animated SVG + MP4/PNG for Canva (talk-visuals skill).

---

## 3. What already exists

### slides/

| File | What it is | Depends on measured numbers? |
|---|---|---|
| `slides/contenido.md` | **Does not exist.** Task 11 is unchecked (PLAN:289-294). There is no outline and no placeholders. | n/a |
| `slides/fuentes.md` | **Does not exist** (PLAN:292) | n/a |
| `slides/armado.md` | **Does not exist.** Not planned in PLAN either, but the sibling pattern has one | n/a |
| `slides/assets/.gitkeep` | Empty placeholder, no assets | n/a |
| `slides/visuals/01-promesa.{svg,png,mp4}` | Promise slide: kicker "LA PROMESA", abstract sentence "Todos escuchamos la promesa…" / "Lo que casi nadie hace es medir qué significa todo eso para su propio workload." (GEN:132-134), footer "tres workloads, tres silicios, un mismo clúster" (GEN:138) | No. Text only, taken from the abstract |
| `slides/visuals/02-arquitectura-lab.{svg,png,mp4}` | Lab diagram: EKS cluster card with "Bottlerocket · Karpenter · un pod por celda" (GEN:74-75), Runner (laptop, no Terraform), Loader c8i.16xlarge with k6 · go-ycsb · pgbench (GEN:81-83), three SUT cards Intel Xeon 6 m8i / AMD EPYC m8a / Graviton5 m9g .4xlarge (GEN:57-59), Pyroscope flame graphs by eBPF. Title "Mismo clúster, mismo loader, tres silicios" (GEN:116) | No numbers. Instance names match the lab. Minor: the subtitle names Karpenter, which Task 7 cells did not use (they ran on MNGs, SPEC:59) |
| `slides/visuals/src/gen.py` | Generator for the two SVGs (talk-visuals skill); render to MP4/PNG via the skill | n/a |

Template conflict: CLAUDE.md:30-31 and SPEC:166 say the handover target is the official **Google Slides** template. Memory (talk-visuals style, 2026-09-27) says slides are built in the speaker's **Canva** template. Confirm with the speaker which one the ACD Perú deck uses.

### demo/

| File | What it is | Numbers? |
|---|---|---|
| `demo/sanitize-check.sh` | Still the Task 10 **stub** (716 B). It has not been replaced by the rompe-tu-agente copy yet (PLAN:286; LEDGER:339). It blocks committing results | n/a |
| `demo/record.md` | **Does not exist** (PLAN:285) | n/a |

### results/ (measured data that slides would be built from)

- Task 7 day 1 `results/2026-09-25-task7-d1/`: go (amd/arm/x86-stock), java (stock/tuned/tuned-vthreads × amd/arm/x86 + x86-smtoff), n=3 runs per cell with APerf tarballs.
- Task 7 day 2 `results/2026-09-26-task7-d2/`: inference (amd/arm/x86 stock+tuned + x86-t8), mongo (6 cells), net (6 cells), postgres (6 cells), plus side experiments mongo-ebs125 and postgres-2x.
- Task 7 day 3 `results/2026-09-27-task7-d3/`: second instance/day for go, java (no smtoff), inference (no t8), mongo, postgres. **No net and no x86-smtoff / x86-t8 on day 3**, so those cells have one instance/day only. Ledger d3 total $39.17 (results/2026-09-27-task7-d3/ledger.md:36).
- Flame graphs: `results/2026-09-27-task7-d3/flamegraphs/java-{arm,x86}-tuned.{svg,png}` are the only rendered ones. Every fixed run has a `flamegraph.json`. Java profiles are complete. Inference and PostgreSQL profiles have kernel frames only, so they are not slide material as they stand (LEDGER:393). Go/Mongo profile quality is not recorded.
- APerf: raw tarballs exist for every Task 7 run. Rendered HTML reports exist only for `postgres-2x/arm-tuned` (d2). The comparative `aperf report -r stock -r tuned` assets planned in SPEC:78 have not been produced.
- Headline numbers (d1/d2 medians, LEDGER:343-349; d3 LEDGER:372-385). Per $, Graviton leads Go, Java, vthreads, inference, Mongo and net efficiency. AMD leads PostgreSQL both raw and per $ (LEDGER:349). Near-ties are pending the item 3 analysis (LEDGER:361, LEDGER:376).
- Cost: `results/cost.md` holds rates, and per-day ledgers exist. Task 7 ≈ $185 estimated (LEDGER:340). The per-workload breakdown for slide 24 (PLAN:268) has not been written.

### Other ready pieces relevant to scenes

- Karpenter: static NodePools in `infra/karpenter/nodepool.yaml` (arc pools `m5,m6i,m7i,m8i` amd64 at :41 and `m6g,m7g,m8g,m9g` arm64 at :77, 4xlarge only, **on-demand only** at :50/:86). The chart is installed by hand, and chart and NodePools exist only on arc/clip days (PLAN:89-91; README.md:137-140). **No AMD generation line** in the arc pools.
- Knob DaemonSets (the "live examples" for the blocker scene) exist: `manifests/base/cstates-daemonset.yaml`, `net-tuned-daemonset.yaml`, `pg-shmem-thp-daemonset.yaml`, `ebpf-profiler.yaml`.

### Sibling deliverable format (rompe-tu-agente, read only)

- `slides/contenido.md` (579 lines): a header with event, date, duration, level and where the numbers come from (contenido.md:1-11). One `## Slide NN — <name>` block per slide with **Headline**, **Body** (bullets / quote / named image from `slides/assets/`), **Layout sugerido**, and **Notas del orador** as a blockquote ending in an estimated time `(~60 s)` (contenido.md:15-51). It says outright that it is the source of truth.
- `slides/armado.md` (956 lines): an editing guide for the official template. It covers the editorial arc, what to fix from the previous PDF, the final order ("portada del evento intacta + 25 slides"), a **layout map** table (slide → headline → template page layout, armado.md:63-94) and per-slide instructions (armado.md:96+). Its rule is not to rewrite contenido.md phrases while pasting.
- `slides/fuentes.md` + `slides/assets/` + `slides/figuras/`.

---

## 4. Promise → evidence map

Status: COVERED = Task 7 has valid n=3 data (2 instance-days where noted). PARTIAL = measured, but a planned piece is missing. NOT MEASURED = no data.

| Item | Answered by | Status | Notes |
|---|---|---|---|
| P1 192 cores / DDR5 / agentic-AI claims | Mongo + inference + PG (memory-bandwidth classes); third-party context (Spare Cores, Phoronix, SPEC:178) | PARTIAL | 4xlarge is a 16-core slice of the socket's bandwidth, so the slide needs that caveat (SPEC:105). "Up to 25/30/35% vs G4" needs the G4 (m8g) point: only the arc (Task 8) or third parties give it |
| P2 same EKS cluster, x86 + Graviton node groups | All Task 7 cells (MNG per cell) | COVERED | Plus AMD (not promised, additive) |
| P3 Java, physical core vs SMT | java stock/tuned × 3 chips (d1+d3), x86-smtoff (d1 only) | COVERED | smtoff has 1 instance-day. Headline candidate SPEC:46 is answerable |
| P3b JDK 25 twist (slide 12) | java tuned-vthreads × 3 (d1+d3) | COVERED | |
| P4 MongoDB, memory bandwidth | mongo stock/tuned × 3 (d2+d3) | COVERED | In-cache by design. Mongo ceiling is WiredTiger admission tickets (SPEC:115), which is why PG was added |
| (add) PostgreSQL | postgres stock/tuned × 3 (d2+d3) | COVERED | Not in the abstract or deck plan. AMD wins raw and per $ (LEDGER:349) and has to be shown openly |
| P5 inference tok/s + $/Mtok | inference stock/tuned × 3 (d2+d3), x86-t8 (d2 only) | COVERED | $/Mtok is computable from tok/s and cost.md rates (SPEC:105). "Ollama" wording drift |
| P6 the why: eBPF flame graphs per arch | Pyroscope flamegraph.json per fixed run; APerf tarballs per run | PARTIAL | Java only is usable (rendered arm/x86-tuned). Inference/PG = kernel-only. Mongo/Go not assessed. APerf comparison reports not generated. Mongo/inference/PG "why" must come from APerf counters or be told as a caveat |
| P7 generational arc m5→M9g | Task 8 | NOT MEASURED | Pools ready, on-demand, ~$2-3 (PLAN:271-275). No AMD line. Fallback: third-party (Spare Cores m6g→m9g, Phoronix G4→G5) + one sentence on slide 3 (SPEC:43, SPEC:157) |
| P8 three whys + one decision rule per class | All workloads + analysis (LEDGER:361) | PARTIAL | Data exists. Bootstrap / "within noise" analysis and the rule wording are not done |
| P9 can your local model live on nodes you already pay for | inference tok/s + $/Mtok | COVERED (data) | Needs framing only |
| P10 open source harness (k6, Prometheus, Pyroscope, buildx, Karpenter) | repo: runner, k6, manifests, apps/build-multiarch.sh, infra | PARTIAL | Prometheus replaced (say so, SPEC:210). Karpenter only exercised in Tasks 8/9. Results uncommitted and sanitize-check still a stub (LEDGER:339). README final is Task 12 |
| P11 mixed node groups | The lab cluster itself (SPEC:161) | COVERED (by construction) | Label/nodeSelector story. No extra run needed |
| P12 Spot + Graviton | Spot prices only (SPEC:181, captured 2026-09-03) | NOT MEASURED | Spot does not change perf, so a per-$ recompute at captured Spot prices is enough if dated. Arc NodePools are on-demand only |
| P13 DaemonSet blocker | Task 9 scene | NOT MEASURED | Manifests for the three live examples exist; the recorded failure scene does not |
| Karpenter clip (slide 20) | Task 9 step 2 | NOT MEASURED | |
| P14 own numbers + independent third parties | results/ + fuentes.md | PARTIAL | fuentes.md missing |
| P15 which class wins on ARM, which doesn't | all classes + per $ | COVERED (data) | Answer is mixed: AMD wins PG, AMD ≈ ARM on Java tuned/vthreads |
| P16 demo | Task 9 scenes + Task 10 plan B | NOT MEASURED | No recording exists |
| Slide 4 vCPU ≠ vCPU | java x86 vs arm + smtoff | COVERED | |
| Slide 5 knobs (three on x86, one on Graviton) | stock vs tuned deltas per chip | COVERED | Phrase to be verified against data (PLAN:269) |
| Slide 8/11 APerf "why" | APerf tarballs | PARTIAL | Reports not rendered |
| Slide 17 net CPU per Gbps | net × 6 cells (d2 only) | COVERED (1 instance-day) | Throughput = instance cap. Tuned knob raised send CPU (LEDGER:348), which flips the "perilla que sí se ve" story, so it must be told as measured |
| Slide 18 Go baseline | go stock × 3 (d1+d3) | COVERED | Data shows arm 36-37k vs x86 20k (LEDGER:343, :372). That is a big gap, not "casi no importa" as SPEC:107 expected, so the slide 18 framing has to change |
| Slide 24 "este lab costó $X" | per-day ledgers + Cost Explorer | PARTIAL | Per-workload breakdown not written |

---

## 5. Framing rules

- **Verify, don't attack** (RECAP:351; SPEC:19): AWS claims are promises tested constructively, showing where they hold and where they depend on the workload, never "marketing vs truth". Tuning is phrased as "cuánto tuning necesita cada silicio para llegar a su número", whichever way it falls (SPEC:19, SPEC:47).
- The Colombia copy's closing line changes to "Todos los números son propios y reproducibles; donde cito a terceros, uso mediciones independientes verificables." Peru's submitted text stays as sent (RECAP:351).
- **Honest competitor results** (memory feedback 2026-09-27): show AMD/Intel wins openly next to the Graviton wins (AMD won PostgreSQL), keep every chip's column, call near-ties "within noise", and put per-$ next to raw numbers. Lead with price-performance and "measure your workload".
- **Language** (CLAUDE.md:22-25; PLAN:18; SPEC:33): everything the audience sees (slides, README, speaker notes, result comments) is in neutral Spanish, never localized to the host country, **no voseo**. Code, tests and commits are in English. Watch SPEC:164, which carries a voseo form ("auditá tus DaemonSets"). It must become "audita tus DaemonSets" before it reaches a slide.
- **No commercial content or logos**. Affiliation appears only as "Solutions Architect - phData" on the title slide (SPEC:18). Visuals follow the re:Invent 2025 look, light background, no AWS logo or wordmark (memory talk-visuals style).
- **Every number carries a date and source**. Third parties are independent measurements (Spare Cores, Phoronix), never marketing (SPEC:21). Credibility comes from n≥3, dated sources and caveats said out loud, with one headline per slide (SPEC:20). Profiler "Alpha" caveat and spec-vs-implementation distinction on stage (SPEC:140).
- **Never repeat** "no public Graviton5 inference evidence" (CLAUDE.md:36-37; SPEC:48).
- **Sanitization**: no account IDs, sensitive ARNs or credentials in anything committed, and `demo/sanitize-check.sh` must print clean (CLAUDE.md:44-47). The script is still a stub.
- **Deliverable boundary**: the speaker owns the template. The repo hands over `slides/contenido.md` + image assets only (CLAUDE.md:27-31; SPEC:172).
