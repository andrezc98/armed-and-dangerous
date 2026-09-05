# Smoke gate (Task 6.5) — 2026-09-04

Clúster: `aws-aad-eks-lab`, EKS 1.36, Bottlerocket 1.64.0 (`aws-k8s-1.36`), kernel 6.18.38, creado por GitHub Actions (OIDC) tras el fallo del apply local (ver ledger). Lecturas hechas con un pod privilegiado (`hostPath /`) en cada nodo.

## Paso 1: stock real y perillas por nodo (18:22)

| Lectura | x86-tuned (m8i.4xlarge) | x86-smtoff (m8i.4xlarge, threads_per_core=1) | arm-tuned (m9g.4xlarge) |
|---|---|---|---|
| `transparent_hugepage/enabled` | `[always]` | `[always]` | `[always]` |
| `transparent_hugepage/defrag` | `[madvise]` (default del SO) | `[madvise]` | `[madvise]` |
| CPUs visibles | 16 | **8** | 16 |
| `thread_siblings_list` de cpu0 | `0,8` (SMT activo) | `0` (SMT apagado) | `0` (1 hilo por núcleo) |
| `cpuidle/current_driver` | `intel_idle` | `intel_idle` | **`none`** |
| Estados cpuidle (latencia) | POLL 0 / C1 1 / C1E 4 / C6 170 / C6P 210 µs | idem | ninguno expuesto |
| `/dev/cpu_dma_latency` leído | 1 µs (DaemonSet C-states activo: tope en C1) | 1 µs | 2000000000 (default, sin DaemonSet) |
| `irqbalance` en el host | ausente | ausente | ausente |
| `ethtool` en el host | presente | presente | presente |
| IRQs ENA en `/proc/interrupts` | 18 | 18 | 18 |
| kubelet `cpuManagerPolicy` | `static` | `static` | `static` |
| Allocatable CPU | 15750m | 7750m | 15750m |

Conclusiones del paso 1:
- El TOML de Bottlerocket 1.64 (`settings.kernel.hugepages.transparent.enabled = "always"`) aplica sin reboot; el AMI publicado es `1.64.0-ad9d4847`.
- `cpu_options.threads_per_core = 1` en el launch template del MNG funciona: el nodo expone 8 CPUs al mismo precio.
- m8i expone C6/C6P en el guest (170/210 µs): la perilla de C-states tiene sentido en x86. Graviton no expone ningún estado cpuidle: la cita de EC2 se verifica literalmente en el nodo.
- El DaemonSet de C-states escribe la latencia de C1 (1 µs), no 0: POLL y C1 permitidos, C1E/C6 excluidos (readiness OK en los dos nodos x86).
- Bottlerocket no trae `irqbalance`: la perilla de red es solo afinidad + coalescing.

## Paso 0: observabilidad
- Pyroscope chart 2.2.1 desplegado en `tools` con PVC gp3 (StorageClass por defecto parcheada).
- Profiler eBPF `otel/opentelemetry-collector-ebpf-profiler:0.147.0` (tag de la doc de Grafana) **no arranca** en kernel 6.18: `failed to load perf_unwind_ruby`. Con `0.160.0` (Docker Hub 2026-09-02) arranca en amd64 y arm64 y Pyroscope recibe `process_cpu` de kubelet, containerd, etc. → el manifiesto se pinnea a 0.160.0.

## Paso 2/5: Java en arm-tuned, primer intento (18:25-18:45)
- Runner completo: escalado 0→1 en 75 s, deploy (imagen desde ECR, pull arm64), `cpuset.cpus.effective = 1-15` en el pod (CPU Manager static: 15 vCPU exclusivas; la 0 queda reservada), JVM ve 15 CPUs; Pyroscope registra `service_name=java` y `k6` al minuto.
- Escalera k6 200→5800 rps (pasos de 400, 60 s): p99 entre 0.55 y 0.89 ms en TODOS los escalones; SLO 100 ms nunca cruzado → el runner marcó `ladder_never_crossed` y NO inventó un knee ni corrió la fase fija (comportamiento diseñado en la revisión final). Ledger: 22.1 min de m9g.4xlarge.
- Lección: el mix de lectura de PetClinic cuesta ~0.1 ms de CPU por request en Graviton; el knee está muy por encima de 6000 rps. Segundo intento con escalera 4000→40000 (pasos de 4000, 45 s) y más VUs.

## Paso 2/5: Java en arm-tuned, segundo intento (18:47-19:00)
- Escalera 4000→40000 rps (pasos de 4000, 45 s; 500 VUs / máx 8000): 9.8 M requests, 100 % con status 200, `http_req_failed` 0, un solo `dropped_iteration`; el escalón de 40000 entregó 1.6 M requests (40 000 rps efectivos) con p99 = 0.67 ms, mediana 0.30 ms. Otra vez `ladder_never_crossed`.
- Hallazgo de gate (bug real): `loader_peak_percent` era 0 en las dos escaleras porque `kubectl top node` acepta UN solo nombre y el sampler pasaba dos → el comando fallaba en silencio y el guard del loader era vacuo. Corregido (`28817fa`): el sampler lista todos los nodos y filtra.
- Tercer intento: escalera 20000→100000 rps (pasos de 10000, 45 s; 2000 VUs / máx 16000) para encontrar el knee real o el techo del loader.

## Paso 2/5: Java en arm-tuned, tercer intento (19:03-19:16), escalera 20000→100000
| rps | 20k | 30k | 40k | 50k | 60k | 70k | 80k | 90k | 100k |
|---|---|---|---|---|---|---|---|---|---|
| p99 (ms) | 0.63 | 0.96 | 1.84 | 3.79 | 6.05 | 7.43 | 11.86 | 11.35 | 12.25 |

- El guard del loader (ya corregido) marcó la celda inválida: c7i.4xlarge al 98 % de CPU con k6 a 90-100k rps. El SUT (m9g.4xlarge, 15 vCPU exclusivas) sigue por debajo del SLO de 100 ms a 100 000 rps.
- Decisiones para Task 7: SLO de Java p99 < 10 ms (el de 100 ms de CMP333 era para una app Groovy mucho más pesada; con PetClinic el knee a 100 ms queda fuera del alcance de un solo loader) y loader c7i.8xlarge; escalera 20k→120k de a 10k.
- Cuarto intento (gate del pipeline completo): SLO 10 ms, escalera 20k→60k, `--runs 1`: knee esperado 50-60k, corrida fija al 80 % con APerf + flame graph.

## Paso 2/5: Java en arm-tuned, cuarto intento (19:17-19:31), SLO 10 ms, escalera 20000→60000
| rps | 20k | 30k | 40k | 50k | 60k |
|---|---|---|---|---|---|
| p99 (ms) | 0.62 | 0.91 | 2.32 | 3.98 | 5.92 |

- No cruzó los 10 ms y el loader llegó al 80 % en el escalón de 60k → inválida por las dos razones. **Conclusión firme del gate: con un loader c7i.4xlarge el knee de Java (PetClinic) no se alcanza en Graviton con ningún SLO razonable; el loader es el techo (≈60k rps al 80 %, ≈100k al 98 %).**
- Quinto intento, solo para ejercitar la fase fija + APerf + flame graph: SLO 2.5 ms (no es un SLO de la charla), escalera 20k→45k.

## Pasos 2, 3 y 5 en arm-tuned: pipeline completo (19:32-19:53, quinto intento, SLO de gate 2.5 ms)
- Escalera 20k→45k (pasos de 5k, 45 s): p99 0.62 / 0.79 / 0.92 / 1.13 / 1.56 / 2.62 ms → knee 40 000 rps (SLO 2.5 ms); loader al 60 % en la escalera (guard OK).
- Corrida fija al 80 % (32 000 rps, 8 min): 15.35 M requests, 0 fallos, p99 5.26 ms. `kubectl top` cada 10 s: nodo SUT mediana **4.7 vCPU** (de 15 exclusivas) → ≈6 800 rps por vCPU de Graviton5 con PetClinic; loader pico 38 %.
- Marcada `invalid` por `dropped_iterations 7547 > 0` (0.05 % de las iteraciones): la regla "cualquier drop invalida" es demasiado estricta para corridas fijas de 8 min con 2000 VUs → decisión: umbral de tasa (p. ej. > 0.1 %) en Task 7.
- **APerf en Bottlerocket (guest Graviton) graba contadores PMU**: IPC 0.98, stall-frontend 454 /kcycle, stall-backend 352 /kcycle, inst-L1 MPKI 35.4, data-L1 MPKI 6.6, L2 MPKI 5.0, dTLB MPKI 4.0, branch MPKI 0.92 (medianas del tramo central de la corrida). Es la capa del "porqué" de la charla, funcionando.
- **Flame graph (OTel eBPF 0.160.0 → Pyroscope) con símbolos Java legibles en arm64**: 1067 de 1253 frames son métodos de Spring/Hibernate/Jackson/JDK; 0 frames `[unknown]`; frames de kernel (`el0_svc`) presentes. El caveat "Alpha" del profiler no afectó a HotSpot en arm64.
- Costo de la celda: 21.3 min de m9g.4xlarge.

## Paso 2/3 en x86-tuned (19:55-20:16), misma escalera y SLO de gate 2.5 ms
| rps | 20k | 25k | 30k | 35k | 40k | 45k |
|---|---|---|---|---|---|---|
| p99 x86-tuned (ms) | 0.88 | 1.18 | 3.91 | 7.48 | 11.54 | 16.99 |
| p99 arm-tuned (ms) | 0.62 | 0.79 (25k) | 0.92 | 1.13 | 1.56 | 2.62 |

- Knee (SLO 2.5 ms): **x86-tuned 25 000 rps vs arm-tuned 40 000 rps**. Corrida fija x86 al 80 % (20 000 rps, 8 min): 9.59 M requests, 0 fallos, p99 0.81 ms; nodo SUT mediana 4.7 vCPU (las mismas 4.7 vCPU con las que Graviton sirvió 32 000 rps). Loader pico 55-62 %.
- Flame graph amd64: 943 frames Java legibles de 1199, 0 `[unknown]`. Simbolización OK en las dos arquitecturas.
- **APerf en el guest Intel (m8i) expone el PMU parcialmente**: IPC 0.86, stall-frontend 196 /kcycle, inst-L1 MPKI 23.6, data-L1 MPKI 15.6, branch MPKI 2.51; L2/L3/TLB y stall-backend leen 0 (eventos no derivables en el guest). Caveat para la slide 11: en x86 el "porqué" se apoya en IPC + front-end + L1; en Graviton está el set completo.
- Ambas corridas fijas marcadas `invalid` solo por `dropped_iterations > 0` (0.05 %): regla a relajar (tasa) en Task 7.
- Números de gate, n=1, SLO de gate: orientan la configuración de Task 7, no van a una slide.

## Paso 4: MongoDB 8.0.29 en arm-stock (20:16-20:30)
- PVC gp3 200 GiB provisionado en ~1 min (StorageClass por defecto parcheada OK); `ycsb-load` de 20 M registros completo; 4 pases de calentamiento hasta que `pages read into cache` se aplanó (control OK, sin `cache_not_warm`). Todo el ciclo: 13.7 min.
- Escalera `workloadb` por hilos (READ p99): 16 → 0.48 ms · 32 → 0.72 · 64 → 1.52 · 128 → 3.22 ms a **169 700 ops/s**; SLO 5 ms no cruzado, loader al 61 %. Task 7: hilos 32/64/128/256/512 (y loader más grande).
- Costo de la celda: 13.7 min de m9g.4xlarge.

## Paso 4b: red (iperf3) en arm-tuned, dos nodos m9g.4xlarge, perilla activa (20:31-20:38)
- DaemonSet `net-tuned` en Bottlerocket: instala `ethtool 7.0` (apk), fija 8 IRQs ENA de eth0 a CPUs distintas, `adaptive-rx off`, RPS en 0; readiness 1/1 en los dos nodos → **SELinux de Bottlerocket no bloquea las escrituras** en `/proc/irq/*/smp_affinity_list` (ni el DaemonSet de C-states en `/dev/cpu_dma_latency`).
- iperf3 `-P 8 -t 60 -J`: **16.86 Gbps** directo y **16.89 Gbps** reverso (tope "up to 17 Gbps" de m9g.4xlarge alcanzado); retransmisiones 7015 / 2703; CPU del proceso iperf3 emisor 64-73 %, receptor 12-13 %; `kubectl top` nodos: 510 y 549 millicores de mediana → ≈0.03 vCPU por Gbps. APerf y flame graph capturados.
- El guard del loader no aplica a la celda de red (el generador es el otro nodo SUT) y así lo registra el runner.

## Paso extra: inferencia en arm-tuned (20:39-20:54), llama.cpp `server-b10775`, Llama 3.1 8B Instruct Q4_0, `-np 4 -t 15`
- Descarga del GGUF (4.68 GB) desde Hugging Face con verificación sha256 OK en ~9 min (initContainer `curlimages/curl`); el servidor carga el modelo y responde `/health` 200.
- Corrida saturante (4 VUs = 4 slots, 6 min): 324 requests, 0 fallos, 41 472 tokens generados → **114.7 tok/s agregados** (29.3 tok/s por slot, p90 29.6); prompt processing 16.2 tok/s (mismo prompt: KV cache reutilizada, `prompt_per_second` no es una métrica aquí). Nodo al 92 % (14.75 vCPU de 16: saturado, como se buscaba).
- **$/Mtok = 0.78272 / (114.7 × 3600) × 1e6 = $1.90 por millón de tokens generados** (on-demand us-east-1, n=1, dato de gate).
- APerf y flame graph capturados; `timings` llega en la respuesta de `/v1/chat/completions` como estaba verificado.
- Costo de la celda: 14.9 min de m9g.4xlarge.
