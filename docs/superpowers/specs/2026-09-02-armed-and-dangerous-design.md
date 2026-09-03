# ARMed and Dangerous — design spec

**Event:** AWS Community Day Argentina 2026-09-12 (waitlist, treated as live target) → ACD Perú 2026-10-03 (submitted) → AWS Women Colombia (guaranteed, date TBD). Session ~30 min + Q&A, nivel 300, español.
**Title (published, immutable):** *ARMed and Dangerous: lo que Graviton5 hace con tus workloads, medido en EKS*.
**Canonical abstract:** v2 (recap §11b: LLM inference on CPU as the third deep-dive, Go as silent baseline). If the Argentina waitlist clears, deliver v2 with the §9 framing: inference as "algo que no estaba en el abstract"; the v1 promise ("un servicio Go como control") is honored by the baseline.
**Date of this spec:** 2026-09-02. All stack facts below were verified against current sources on this date (§9). Re-verify on lab day before writing them into code, manifests or slides.

---

## 1. Goal and constraints

Medir en EKS qué hace Graviton5 con tres clases de workload, explicar cada número con flame graphs de eBPF (la señal de Profiles de OpenTelemetry), y entregar un harness open source reproducible + una regla de decisión por clase de workload que la audiencia aplica el lunes.

Hard constraints (event guidelines, same rules the Strands spec recorded from the ACD "Lineamiento Presentaciones" PDF):

- **Fidelidad al abstract v2.** Sin contenido comercial ni logos; afiliación solo como "Solutions Architect - phData" en la title slide.
- **Verify, don't attack** (speaker's rule, recap §12): las cifras de AWS son promesas que testeamos constructivamente — dónde se cumplen, dónde dependen del workload. Nunca "marketing vs verdad".
- **Lecciones de la retrospectiva de KCD Lima** (heredadas de rompe-tu-agente): story over spec sheet; depth over breadth; el diseño de la medición narrado como parte de la historia; credibilidad con n≥3, fuentes datadas y caveats en voz alta; un headline en su propia slide; cierre que sorprenda.
- **Cada número lleva fecha y fuente.** Terceros = mediciones independientes, nunca marketing. Propios = harness publicado. `slides/fuentes.md` estilo kcd.
- **Presupuesto lab ≤ $200.** Slide de transparencia "este lab costó $X" con desglose por fase; clúster abajo entre fases; Spot para el arco generacional. El runner mide reloj por fase y aborta si una fase se pasa del estimado.
- **AWS gated:** solo la cuenta sandbox del speaker, nunca el perfil cliente por defecto de la máquina (`require_sandbox()`, patrón rompe-tu-agente). Nada de `tofu apply` ni buildx push sin autorización explícita.
- **Demo con plan B grabado; nada del escenario depende del WiFi.**
- **Sanitización:** sin account IDs, ARNs con datos sensibles ni credenciales en nada commiteado (`demo/sanitize-check.sh`).

Non-goals (out of scope, dicho en slide): GPU inference; otros clouds (Axion/Cobalt/Ampere una línea de contexto, no medidos); workloads bound a disco/red; segunda región.

---

## 2. Story and time map (30 min, split 2 / 5 / 18 / 5)

Registro: español neutro (nunca localizado al país anfitrión), relojes y pantallas reales.

| Bloque | Min | Contenido |
|---|---|---|
| Apertura | 2 | Título. "Soy Andrés, arequipeño, Solutions Architect, trabajo con AWS a diario." La promesa: Graviton5 GA, 192 núcleos, DDR5-8800, "hasta 25% sobre Graviton4". "Lo que casi nadie hace es medirlo con su propio workload. Hoy sí." |
| Contexto | 5 | El arco m5→M9g. La slide conceptual que sostiene todo: por qué un vCPU ARM ≠ un vCPU x86 (núcleo físico vs hermano de SMT). Y "la perilla que no existe": Graviton opera a frecuencia fija, sin control de C-states/P-states; x86 sí se tunéa (m7i) — y eso define nuestra metodología de equidad (§5). |
| Desarrollo | 18 | Metodología como historia (3) → **Java** (4): alta concurrencia, platform vs virtual threads, SMT vs physical core → **MongoDB** (4): ancho de banda de memoria, flame graph → **Inference** (4): tok/s y $/Mtok en CPU, DDR5 a juicio, primera evidencia pública de G5 en inferencia → **migración** (3): node pools mixtos, Spot+Graviton, el bloqueador: DaemonSets. |
| Aprendizajes | 5 | Regla de decisión por clase de workload ("el lunes"). Qué no medimos y por qué. El lab costó $X. Cierre. |
| Q&A | 5-10 | QR de feedback en pantalla. Repetir la pregunta antes de responder. |

**Headline candidates** (confirmados por datos antes de slides, no antes):
- *"El mismo contenedor, el mismo clúster, otro silicio: 2 hilos por núcleo vs ninguno."* — el benchmark que nadie hace no es el cuánto, es el porqué.
- El ángulo novedad: **no existe evidencia pública de inferencia LLM sobre Graviton5** (verificado 2026-08-12; re-verificar): la nuestra es la primera.

**Closing candidate:** *"Graviton no es más rápido ni más barato: es distinto. Mide el porqué, no el cuánto."*

**Test design narrated, not hidden.** Cada workload tiene una línea de "por qué esta clase" y una pregunta que el flame graph responde (§4). Ese es el fix para el gap de credibilidad de Lima.

---

## 3. The lab: EKS cluster

- **Infra:** OpenTofu + `terraform-aws-modules/eks/aws` **21.25.0**, patrón del repo kcd `infra-eks/` (VPC existente del sandbox + subnets propias + access entries `API`, Bottlerocket). AWS provider ~> 6.53.
- **Node groups (MNG), uno por arquitectura** — el punto es comparar silicio, no autoscaling:
  - `x86`: `m7i.xlarge` (4 vCPU = 2 núcleos físicos + SMT), `BOTTLEROCKET_x86_64`
  - `arm`: `m9g.xlarge` (4 vCPU = 4 núcleos físicos, Graviton5, DDR5-8800), `BOTTLEROCKET_ARM_64`
  - Par xlarge = mismo vCPU y misma RAM (16 GiB) por nodo → comparación justa y barata. min=max=1 c/u: clúster de benchmark, no de producción.
  - Fallback de capacidad: `m9g.large` ×2 pods por nodo, o `m8g` con el caveat dicho en el escenario (precedente kcd: m8g.large probado; m9g.large ya corrió en EKS 1.36 el 2026-07-14).
  - Precios on-demand se capturan el día del lab (pricing API/CLI) y se commitean en `results/cost.md`; nunca se citan de memoria.
- **Karpenter v1.14.1** (chart oficial OCI, `helm_release`): un NodePool multi-arch para la escena "Karpenter eligiendo por precio-rendimiento": scale-from-zero con pods sin affinity → muestra qué arquitectura elige y a qué precio. Grabado (<2 min), es el clip de migración.
- **DaemonSet del profiler (OTel eBPF):** `otel/opentelemetry-collector-ebpf-profiler` (tag del día, referencia 0.147.0), privileged + hostPID + mounts `/proc`, `/sys/kernel`, feature gate `service.profilesSupport`, OTLP gRPC → Pyroscope. Multi-arch por naturaleza — y ejemplo viviente del DaemonSet blocker.
- **No hay clúster persistente:** `tofu apply` al inicio de cada fase de medición, `tofu destroy` al final. El costo real (reloj × tarifas del día) es el dato de la slide de transparencia.

## 3.5. La perilla que no existe: C-states (variante "x86 tuned")

Verificado 2026-09-02 contra la doc oficial EC2 (processor state control): *"AWS Graviton processors have built-in power saving modes and operate at a fixed frequency. Therefore, they do not provide the ability for the operating system to control C-states and P-states."* En cambio, **`m7i.xlarge` (nuestro nodo x86) SÍ está en la lista de instancias con control de C-states.** Lo mostrado en re:Invent era processor state control x86 — limitar C-states profundos elimina la latencia de wake-up de núcleos dormidos y mejora p99 en Java y consistencia en MongoDB. Graviton no tiene esa perilla: frecuencia fija, power saving en el silicio.

- **Variante de lab "m7i tuned"** (~$15-25): re-corremos Java y MongoDB con C-states limitados en el nodo x86 — DaemonSet privilegiado que mantiene abierto `/dev/cpu_dma_latency` (mecanismo documentado EC2), `nodeAffinity` a amd64. Medimos **m7i stock vs m7i tuned vs m9g**. Si Graviton gana o empata contra el x86 en su mejor configuración, el hallazgo es más fuerte: le dimos a x86 su mejor oportunidad (equidad metodológica recomendada por la whitepaper de AWS "Graviton Performance Testing" — citarla).
- **Slide "La perilla que no existe":** m7i stock vs tuned vs m9g + la cita literal de la doc. La conclusión es el feature: rendimiento consistente sin tuning tax, sin manual por tipo de instancia.
- **Composición con el blocker:** el DaemonSet de C-states es amd64-only *por diseño* — segundo ejemplo viviente de la sección DaemonSets ("este DaemonSet SABE que es amd64-only; los tuyos, ¿lo saben?").

---

## 4. The workloads (tres + control)

Criterio de diseño: apps chicas a propósito — un framework gigante entierra la señal microarquitectural en el flame graph. Cada workload es una clase con una pregunta que solo el profiler responde.

| Workload | Por qué esta clase | App | La pregunta que el flame graph responde |
|---|---|---|---|
| **Java, alta concurrencia** | CPU + scheduling: expone SMT vs núcleo físico | Servicio REST mínimo sobre JDK 25 (HttpServer del JDK, sin framework), **dos modos**: platform threads con pool = vCPU, y virtual threads | En x86, 4 vCPU = 2 núcleos: los threads compiten por el hermano de SMT y el scheduler aparece en el flame graph; en Graviton, 4 vCPU = 4 núcleos y el pool escala lineal. Con virtual threads, la matemática cambia en ambas. |
| **MongoDB** | Memory-bandwidth bound | Imagen oficial `mongodb` (multi-arch, tag del día) + workload de ingest y agregaciones pesadas; working set ~10 GiB (≈60-70% RAM del nodo) | Dónde vive el tiempo: DDR5 del m7i vs DDR5-8800 de Graviton5, visible en throughput de scans; los frames de copia de memoria vs CPU cuentan la historia. |
| **Inference en CPU** | El workload 2026; memory-bandwidth + vectores | Ollama (tag multi-arch amd64/arm64) con modelo open-weight 3–8B Q4, prompts fijos, `eval_count`/duración de la API → tok/s → $/Mtok | La inferencia cuantizada vive del ancho de banda de memoria, no del pico de CPU: DDR5-8800 es la apuesta de AWS y este es el juicio. **Primera evidencia pública en Graviton5** (sin public benchmarks al 2026-08-12; re-verificar antes de la slide). |
| **Go (control silencioso)** | Servicio de red simple, ~uniforme | Mini servicio HTTP en Go puro (stdlib), multi-arch | Baseline de "cuándo la arquitectura casi no importa" — la regla de decisión: "si tu workload es así, no gastes tiempo midiendo". |

Todas las imágenes propias construidas con **buildx `--platform linux/amd64,linux/arm64`**, manifiesto multi-arch en GHCR (repo público desde el día 1; fallback ECR del sandbox si GHCR complica). El pipeline de build multi-arch es parte del entregable de la charla, no plomería.

## 5. Harness y metodología (narrada, no escondida)

- **k6 v2.2.0**, escenarios `constant-arrival-rate` (throughput fijo) — evita coordinated omission y esa decisión se narra: "no medimos cuánto tarda un request aislado, medimos cuánto throughput sostiene el sistema a carga fija".
- **Warmup explícito por workload**, descartado de la medición: JIT de Java (fase a carga objetivo N min), caché de MongoDB (fría vs caliente), Ollama (primer prompt carga el modelo). Se narra porque es la trampa #1 de benchmarks de Java.
- **Vecinos ruidosos:** un workload por fase, un pod por nodo, requests/limits fijados, sin HPA durante la medición. Se dice en voz alta: es el caveat que la sala va a buscar.
- **Equidad metodológica:** cada celda se corre stock y (donde la perilla existe) tuned — §3.5. "Le dimos a cada silicio su mejor configuración."
- **n≥3 corridas por celda** (workload × arquitectura), mediana reportada, dispersión visible, JSONs crudos commiteados. Los datos crudos nunca se editan a mano; la slide sale del JSON.
- **Prometheus 3** (receptor OTLP nativo) + **Grafana** para métricas de contenedor/nodo; capturas reales de las corridas en `slides/assets/`.
- **Pyroscope 2.3.0** como backend de la señal de Profiles de OTel; flame graphs por arquitectura exportados como PNG. Caveats dichos en el escenario, con la fuente: la **especificación** de la señal es estable desde 2025, pero la implementación del eBPF profiler se describe como **Alpha/work-in-progress** en su propio README, y Grafana advierte simbolización imperfecta en algunos programas (riesgo principal: JIT de Java). Distinguir spec vs implementación es material de slide, no solo caveat.
- **Fallback de legibilidad:** si un flame graph de Java no es legible (gate de Task 6.5), se complementa con async-profiler vía OTel SDK para ese workload. Decisión de implementación, documentada en README si se usa.
- **Runner:** Python 3.13 + uv; orquesta fase = apply → deploy con `nodeSelector kubernetes.io/arch` → healthcheck → warmup → k6 ×N → capture (k6 JSON + Prometheus query + costo por reloj) → destroy. Análisis (medianas, delta %, precio-rendimiento, $/Mtok) contra JSONs commiteados. `require_sandbox()` primera línea de todo entrypoint.

## 6. El arco generacional (la yapa)

m5.xlarge → m6i → m7i (x86) y m6g → m7g → m8g → m9g (ARM), **Spot**, una sola workload (Java corto), corrida única por generación. Es una línea de tiempo en una slide, no un segundo benchmark. Caveat narrado: corrida única, Spot, orientativo — el arco, no el número.

## 7. Migración en EKS: el cierre

1. **Node pools mixtos** — el clúster del lab ya lo es: migrar no es big-bang, es un label (`kubernetes.io/arch` + nodeSelector).
2. **Spot + Graviton** como configuración más eficiente — con el número medido de cuánto aporta cada palanca en este lab.
3. **El bloqueador que nadie nombra: DaemonSets.** Escena en vivo/grabada: aplicamos un DaemonSet amd64-only al clúster mixto → `ImagePullBackOff`/`CrashLoopBackOff` en los nodos Graviton → el rollout se congela. Dos ejemplos vivientes del lab: el profiler eBPF (multi-arch o no funciona) y el DaemonSet de C-states (amd64-only *por diseño*). Regla: *antes de migrar, auditá tus DaemonSets; ahí están tus dependencias reales.*

## 8. Deck (plantilla oficial Google Slides; boundary igual que rompe-tu-agente)

25 content slides + Q&A + Gracias:

1 Título · 2 Contenido · 3 La promesa (G5 GA, 192 cores, DDR5-8800) · 4 vCPU ≠ vCPU (SMT vs physical) · 5 La perilla que no existe (C-states; Graviton frecuencia fija) · 6 El lab (diagrama EKS) · 7 Metodología como historia (arrival-rate, warmup, vecinos ruidosos, equidad stock/tuned, n≥3) · 8 Java: setup · 9 Java: número (m7i vs m7i-tuned vs m9g) · 10 Java: flame graphs lado a lado · 11 Virtual threads (el twist JDK 25) · 12 MongoDB: setup · 13 MongoDB: número + flame graph · 14 Inference: setup (Ollama, Q4) · 15 Inference: tok/s + $/Mtok (primera evidencia pública) · 16 Arco generacional m5→M9g · 17 Karpenter elige por precio-rendimiento (clip) · 18 Migración: node pools mixtos · 19 Spot + Graviton · 20 El bloqueador: DaemonSets (escena) · 21 Regla de decisión por clase ("el lunes") · 22 Qué NO medimos y por qué · 23 El harness es tuyo (repo) · 24 Este lab costó $X · 25 Aprendizajes + cierre · Q&A · ¡Gracias!

Deliverable boundary (speaker's call): el speaker posee la plantilla oficial y pega; este repo entrega solo `slides/contenido.md` (headline + body de una idea por slide + speaker notes en ES) e image assets: diagrama de arquitectura (iconos oficiales AWS), flame graphs exportados, charts matplotlib desde los JSON commiteados, capturas Grafana/Pyroscope. `slides/fuentes.md` con fecha y URL por cada cifra (formato kcd).

## 9. Verified versions and sources (2026-09-02)

- **M9g/Graviton5 GA**: hasta 192 vCPU/socket (m9g.48xl), DDR5-8800, "up to 25% better compute performance" vs M8g; claims por workload: 30% DB / 35% web / 35% ML; Nitro System sexta generación, primera con Nitro Isolation Engine; GA jun 2026, regiones us-east-1/2, us-west-2, eu-central-1. https://aws.amazon.com/ec2/instance-types/m9g/ · https://aws.amazon.com/about-aws/whats-new/2026/06/ec2-m9g-m9gd-instances-graviton5-processors-available/. El stack kcd ya corrió `m9g.large` + Bottlerocket en EKS 1.36 el 2026-07-14 (`kcd/README.md`).
- **Processor state control**: Graviton = frecuencia fija, sin C-states/P-states controlables (cita textual arriba); `m7i.xlarge` SÍ tiene control de C-states (está en la lista oficial). https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/processor_state_control.html
- **Graviton Performance Testing whitepaper** (metodología de equidad; instrumentación): https://docs.aws.amazon.com/whitepapers/latest/aws-graviton-performance-testing/
- **terraform-aws-modules/eks**: 21.25.0 (registry, hoy). AWS provider ~> 6.53 (precedente kcd). https://registry.terraform.io/modules/terraform-aws-modules/eks/aws/
- **Karpenter**: v1.14.1 (2026-08-21, latest). Chart oficial OCI `oci://public.ecr.aws/karpenter/karpenter`. https://github.com/kubernetes-sigs/karpenter/releases
- **Pyroscope**: v2.3.0 (2026-08-24). https://github.com/grafana/pyroscope/releases
- **OTel eBPF profiler**: receiver `otelcol-ebpf-profiler` (referencia 0.147.0; tag del día al deploy), DaemonSet privileged + hostPID + mounts, `--feature-gates=service.profilesSupport`, relabel `process.executable.name → service_name` en Pyroscope, 97 samples/s, Linux amd64/arm64. Cobertura: Hotspot JVM, nativo C/C++ sin debug symbols (`.eh_frame`), Go, stacktraces mixtos kernel→libc→runtime, ARM64 en todos los unwinders, ~1% CPU / <250 MB overhead. **Se describe a sí mismo como "Alpha OTel Profiles signal, work-in-progress"** — distinguir spec estable (2025) vs implementación. Caveat de simbolización: https://github.com/open-telemetry/opentelemetry-ebpf-profiler · https://grafana.com/docs/pyroscope/latest/configure-client/opentelemetry/ebpf-profiler/
- **k6**: v2.2.0 (2026-08-10; module path `go.k6.io/k6/v2` desde v2.0 — flags removidos: `--no-summary`, `k6 login`, etc.). https://github.com/grafana/k6/releases
- **OTel Profiles signal**: especificación estable desde 2025 (recap §8; re-verificar wording exacto antes de slides).
- **Tendencias** (recap §8, verificadas 2026-08-11, re-chequear antes de slides): ARM ≈9% de CPUs en clústeres K8s, creciendo 3.5× más rápido que x86 (Cast AI); Arm "up to 65% mejor precio-rendimiento" = vendor claim que esta charla testea; JDK 25 aarch64 (C2 auto-vectorization, SVE intrinsics, ~3.5× vs JDK 8) — https://inside.java/2025/10/20/jdk-25-performance-improvements/
- Regla CLAUDE.md: nada de esto se escribe en código sin re-verificar el día del lab; cada subagent recibe esta instrucción.

## 10. Traceability to abstract v2

| Promesa del abstract | Dónde aterriza |
|---|---|
| "192 núcleos por socket, 25% sobre Graviton4" | §2 apertura; §9 spec citada; testeada en cada workload |
| "la memoria DDR5 más rápida de la nube… era de la IA agéntica" | §4 MongoDB/inference: DDR5-8800 a juicio; v2 abstract |
| "aplicación Java de alta concurrencia… núcleo físico y no hermano de hyperthreading" | §4 Java, dos modos, flame graphs lado a lado |
| "MongoDB (que vive del ancho de banda de memoria)" | §4 Mongo |
| "modelo open-weight cuantizado corriendo con Ollama sobre CPU… tokens por segundo y costo por millón" (v2) | §4 inference — primera evidencia pública G5 |
| "profiling continuo con eBPF… señal de Profiles… flame graphs… adónde se va el tiempo en cada arquitectura" | §5 Pyroscope + profiler DaemonSet; §9 caveats Alpha narrados |
| "La metodología se narra como parte de la historia (warmup del JIT, coordinated omission, vecinos ruidosos)" | §5 metodología + slide 7 |
| "harness completo… open source y queda publicado: k6, Prometheus, Pyroscope, buildx, Karpenter" | §3, §5, §8 slide 23; GHCR público |
| "evolución generacional medida, de m5 a M9g" | §6 |
| "node groups mixtos, Spot más Graviton… el bloqueador… DaemonSets" | §7 |
| "tres workloads, tres porqués, y una regla de decisión por clase de workload" | §4 tabla; §8 slide 21 |

Out of scope explícito (slide 22): GPU inference, otros clouds medidos, workloads de disco/red, segunda región, big frameworks (Spring et al.) — el porqué se narra.