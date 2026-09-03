# ARMed and Dangerous — Implementation Plan

> **For agentic workers:** implement this plan task-by-task; steps use checkbox (`- [ ]`) syntax for tracking. Every dispatched subagent gets the verify-don't-guess rule verbatim (see CLAUDE.md).

**Goal:** medir en EKS qué hace Graviton5 con tres clases de workload (Java, MongoDB, inference en CPU) + control Go, explicar cada número con flame graphs de eBPF (señal de Profiles de OTel), y entregar el harness open source + slides para ARMed and Dangerous (ACD Argentina waitlist 2026-09-12 → ACD Perú 2026-10-03 → Colombia TBD).

**Architecture:** un clúster EKS efímero (OpenTofu, módulo eks 21.25.0) con dos managed node groups — `m7i.xlarge` (x86) y `m9g.xlarge` (Graviton5) — sobre el que un runner Python orquesta fases de medición: deploy con nodeSelector arch → warmup → k6 constant-arrival-rate ×N → capture (k6 JSON, Prometheus, flame graphs vía Pyroscope, costo por reloj) → destroy. Apps multi-arch propias (buildx → GHCR) + imágenes oficiales para MongoDB y Ollama. DaemonSet del OTel eBPF profiler para la señal de Profiles; DaemonSet de C-states para la variante "m7i tuned". Resultados JSON commiteados → charts matplotlib → `slides/contenido.md` + assets.

**Spec:** `docs/superpowers/specs/2026-09-02-armed-and-dangerous-design.md` (read it first; every task cites the section it implements).

## Global constraints

- **Verify every API/field/tag against current docs before writing it** (CLAUDE.md): Context7 / docs oficiales / GitHub releases del día; pin lo verificado y citarlo en README. Nothing from training memory — this stack moves monthly (Karpenter, Pyroscope, k6 v2, módulo EKS, tags de imágenes).
- **AWS is gated on the speaker.** Todo script que toca AWS llama `require_sandbox()` (AWS_PROFILE debe contener `sandbox`) como primera línea de defensa; nada de `tofu apply`, `tofu destroy`, push a registry ni corridas de lab sin el speaker diciendo "go" (GATED). Nunca el perfil cliente por defecto de la máquina.
- **Presupuesto total ≤ $200** (aprobado). Runner mide reloj por fase; si una fase se pasa del estimado, aborta y pregunta. Cluster SIEMPRE abajo entre fases (`tofu destroy` al final de cada fase, verificar con `aws ec2 describe-instances` filtrado por el tag del proyecto).
- **Español todo lo que la audiencia ve** (slides, README, comentarios de resultados, speaker notes), neutral (voseo solo en escenario Uruguay); inglés el código, tests, commits.
- Naming: `aws-aad-*` (aws-<event>-<resource>) — p.ej. `aws-aad-eks-arm-lab`, `aws-aad-subnet-*`, tags estándar `Project=armed-and-dangerous, Environment=lab, Owner=andres-zeballos, ManagedBy=tofu`.
- Sin emojis en código/salidas. Sin account IDs, ARNs con datos sensibles ni credenciales en nada commiteado; `demo/sanitize-check.sh` antes de commitear resultados o assets.
- Steps **GATED** = gasta AWS o push a registry. Pedir autorización al speaker antes del primero de cada tipo.
- Commit after every task, conventional messages. Repo root: `~/Documents/personal/charlas/armed-and-dangerous`.
- **Recorte si el waitlist de Argentina abre con <7 días:** cada task marca qué se recorta. Regla general: prefiero Java+inference con n honesto que tres workloads con n=1.
- Timeline (Strands talk es prioridad hasta el 12-09; esto se ejecuta en huecos): Tasks 1-3 noche del 02-03/09 · 4-5 el 04-05 · **7 (corrida completa) el fin de semana 06-07** · 8-9 + plan B el 08-09 · slides 10-11 · congelar o presentar el 12 · reabrir para Perú 22-27/09.

## File structure

| Path | Responsibility |
|---|---|
| `CLAUDE.md`, `README.md`, `.gitignore` | Rules, reproducibility (versions + dates + cost), layout |
| `apps/java/`, `apps/go/` | Los dos servicios propios (multi-arch Dockerfiles) |
| `apps/mongo-seed/` | Workload de ingest/agregación (script JS para mongosh, corre desde el runner) |
| `infra/` | OpenTofu: EKS 21.25.0, 2 MNG, Karpenter, outputs |
| `manifests/` | Prometheus 3 + Grafana + Pyroscope 2.3.0 (helm values) + DaemonSet profiler + DaemonSet C-states + workloads (k8s yaml por workload con nodeSelector arch) |
| `runner/` | Python 3.13 + uv: orquesta fases, k6, capture, destroy; analysis/ (medianas, deltas, $/Mtok) |
| `results/` | JSONs crudos commiteados (n≥3 por celda), flame graphs PNG, `cost.md` |
| `demo/` | `record.md` (plan B), `sanitize-check.sh` |
| `slides/` | `contenido.md`, `fuentes.md`, `assets/` |
| `docs/superpowers/{specs,plans}/` | This spec + plan |

---

### Task 1: Repo skeleton, rules, pins [SPEC §1]

**Files:** `CLAUDE.md`, `README.md` (skeleton), `.gitignore`, dirs, `demo/sanitize-check.sh` (stub), empty `.gitkeep`s.

- [ ] **Step 1:** Write `CLAUDE.md`: (a) verify-don't-guess rule (Context7/docs del día, pin y cita; cada subagent la recibe verbatim); (b) sandbox gate: credenciales default = cliente, todo AWS via `require_sandbox()` (AWS_PROFILE contiene "sandbox"); nunca apply/push/corrida sin el speaker; (c) presupuesto ≤ $200 y cluster-abajo-entre-fases; (d) deliverable boundary: speaker posee plantilla Google Slides, este repo entrega `slides/contenido.md` + assets; (e) idioma: código inglés, audiencia español neutro.
- [ ] **Step 2:** `.gitignore`: `.terraform/`, `*.tfstate*`, `.terraform.lock.hcl` NO (lock sí se commitea), `tfvars` reales (solo `example.tfvars` commiteado), `.venv/`, `__pycache__/`, `results/raw-large/` (JSONs seleccionados sí; crudos gigantes no), `.env`, `.DS_Store`.
- [ ] **Step 3:** `README.md` skeleton con secciones vacías: Versiones probadas (fechadas), Setup, Orden de corrida, Costo real, Deltas/gotchas. Patrón kcd README + rompe-tu-agente README.
- [ ] **Step 4:** `demo/sanitize-check.sh` stub que hoy solo imprime "sanitize-check: stub"; se completa en Task 10.
- [ ] **Step 5:** Commit `chore: skeleton with rules and pins`.

*Recorte si Argentina abre: ninguno — Task 1 es hora de trabajo, no de dinero.*

### Task 2: Las apps (Java JDK 25, Go control, mongo-seed) [SPEC §4]

**Files:** `apps/java/{Dockerfile,src/…}`, `apps/go/{main.go,Dockerfile}`, `apps/mongo-seed/{load.js,aggregate.js}`, smoke local.

- [ ] **Step 1:** **VERIFY**: tag exacto de imagen base JDK 25 multi-arch (dockerhub/eclipse-temurin del día) y comportamiento de virtual threads en 25 (`Thread.ofVirtual`, `Executors.newVirtualThreadPerTaskExecutor`). Elegir y pinnear en el Dockerfile. Decidir el modelo Q4 (3–8B) y tag de Ollama del día — se consumen como imágenes oficiales, no se construyen (ponytail: no hand-roll).
- [ ] **Step 2:** Java: HttpServer del JDK, cero frameworks. Dos modos via env `JAVA_MODE=platform|virtual`. Platform: pool fijo = vCPU (`Runtime.getRuntime().availableProcessors()`), `-XX:+UseSerialGC` o default GC — **decisión de implementación del día con una prueba de humo** (la GC no debe dominar el flame graph; documentar la elegida). Endpoint `GET /work` con CPU work acotado (bucle fijo, no `Thread.sleep`) para que el flame graph muestre scheduling real.
- [ ] **Step 3:** Go: `net/http` stdlib, handler con el mismo perfil de trabajo (bucle fijo). Mismo path/contrato que Java → comparables.
- [ ] **Step 4:** mongo-seed: `load.js` (bulk ingest de documentos generados, ~10 GiB working set) + `aggregate.js` (pipeline pesado de scans). Corren vía `mongosh` desde el runner contra el pod MongoDB, no como job dentro del clúster (control desde fuera = parte del harness).
- [ ] **Step 5:** Smoke local en Mac (todo compila en arm64 local): `docker build` de Java y Go, run, `curl`, mongo-seed contra un `docker run mongodb` local. Fijar en README las versiones resultantes.
- [ ] **Step 6:** Commit `feat(apps): JDK25 dual-mode service, Go control, mongo workload`.

*Recorte: nada — local, gratis.*

### Task 3: buildx multi-arch + GHCR [SPEC §4]

- [ ] **Step 1 (GATED push):** `docker buildx build --platform linux/amd64,linux/arm64 --push` de `apps/java` y `apps/go` → GHCR (repo público; `GITHUB_TOKEN` local). Fallback si GHCR complica: ECR del sandbox. Verificar con `docker buildx imagetools inspect` que ambos manifests existen. El tag lleva la fecha (`:2026-09-02` style) — reproducibilidad.
- [ ] **Step 2:** Script `apps/build-multiarch.sh` (el pipeline ES entregable de la charla; slides 6/23 lo citan).
- [ ] **Step 3:** Commit `build: multi-arch pipeline (buildx, GHCR)`.

*Recorte si Argentina abre: solo las apps del deep-dive; variantes pueden esperar.*

### Task 4: Infra EKS (OpenTofu) [SPEC §3]

**Files:** `infra/{versions.tf,variables.tf,main.tf,outputs.tf,example.tfvars}`.

- [ ] **Step 1:** Patrón kcd `infra-eks/` (VPC existente vía `var.vpc_id` + subnets propias + route table propia + IGW existente): módulo `terraform-aws-modules/eks/aws` **21.25.0** (`~> 21.25`), provider `aws ~> 6.53`, `kubernetes_version` la del día (kcd probó 1.36), `authentication_mode = "API"`, `enable_cluster_creator_admin_permissions = true`, addons kcd (coredns, kube-proxy, vpc-cni before_compute, ebs-csi-driver — **golpe conocido kcd**: sin StorageClass default los PVC quedan Pending; patch documentado en runner) y `eks-pod-identity-agent` solo si algo lo necesita (no: no hay Bedrock en este lab).
- [ ] **Step 2:** Dos MNG, min=max=1 cada uno: `x86` = `m7i.xlarge`/`BOTTLEROCKET_x86_64`, `arm` = `m9g.xlarge`/`BOTTLEROCKET_ARM_64`. **VERIFY** `ami_type` strings exactos contra el módulo 21.x y capacidad de m9g.xlarge en us-east-1 (fallback: m9g.large ×2 pods/nodo, o m8g con caveat narrado). Tags estándar en todo.
- [ ] **Step 3:** Karpenter v1.14.1 vía `helm_release` (chart OCI oficial) + rol/node role + un **NodePool multi-arch** y dos **EC2NodeClass** (una por AMI family Bottlerocket) + CRDs — **VERIFY** contra docs Karpenter del día: versiones chart↔K8s, campos NodeClass actuales. Solo para la escena scale-from-zero (slide 17), no para el benchmark (MNG fijos = comparación de silicio controlada).
- [ ] **Step 4:** Outputs: `cluster_name`, `configure_kubectl`. `tofu init && tofu validate` offline; commitear el lock.
- [ ] **Step 5:** Commit `feat(infra): dual-arch EKS with Karpenter NodePool`.

*Recorte: Karpenter queda para la semana de Perú si hay que elegir.*

### Task 5: Observabilidad en el clúster [SPEC §5]

**Files:** `manifests/{kube-prometheus-stack-values.yaml,pyroscope-values.yaml,ebpf-profiler.yaml,c-states-daemonset.yaml,workloads/}`.

- [ ] **Step 1:** Prometheus 3 + Grafana: helm `kube-prometheus-stack` values mínimos (receptor OTLP si aplica a la versión del chart del día — **VERIFY**; sino remote-write tradicional). Pyroscope **2.3.0** (chart oficial o values mínimos): OTLP gRPC 4040 + `limits.ingestion_relabeling_rules` con labelmap `process.executable.name → service_name` (doc Grafana) + datasource en Grafana.
- [ ] **Step 2:** DaemonSet OTel eBPF profiler según docs oficiales (referencia 0.147.0; **VERIFY** tag del día): privileged, hostPID, mounts `/proc` `/sys/kernel` `/sys/fs/cgroup`, `--feature-gates=+service.profilesSupport`, config con receiver `profiling` (`samples_per_second: 97`) + exporter OTLP a `pyroscope:4040`, RBAC del ejemplo oficial k8s de Pyroscope. `tolerations: operator: Exists`. **VERIFY** que Bottlerocket permite los mounts/privileged (precedente: sí para eBPF tools; probar, no asumir).
- [ ] **Step 3:** DaemonSet C-states "m7i tuned" [SPEC §3.5]: contenedor privileged que abre `/dev/cpu_dma_latency` y escribe el valor mínimo (0) manteniendo el fd abierto por la vida del pod; `nodeAffinity` `kubernetes.io/arch: amd64`. **VERIFY** el mecanismo exacto contra la guía EC2 processor-state-control (latency hint via `/dev/cpu_dma_latency` es el mecanismo estándar de Linux; confirmar que la doc EC2 lo muestra o usar el método de la doc). amd64-only por diseño = ejemplo viviente slide 20.
- [ ] **Step 4:** `manifests/workloads/*.yaml`: un Deployment por workload con `nodeSelector kubernetes.io/arch` + requests/limits fijos + sin HPA; MongoDB y Ollama consumen imágenes oficiales multi-arch con PVC (gp3 → StorageClass default parcheado, golpe kcd).
- [ ] **Step 5:** Commit `feat(obs): prometheus, pyroscope, eBPF profiler daemonset, c-states daemonset`.

*Recorte: Prometheus opcional si aprieta el tiempo (k6 JSON + flame graphs sostienen el talk); el profiler NO es recortable.*

### Task 6: El runner (Python 3.13 + uv) [SPEC §5]

**Files:** `runner/{pyproject.toml,phase.py,capture.py,analysis/__init__.py,analysis/stats.py,cost.py}`, `tests/` (unit, sin AWS).

- [ ] **Step 1:** `pyproject.toml` con uv; deps mínimas (httpx, boto3, jinja2/kubectl wrapper según convenga; k6 como CLI externo versionado). Python 3.13 (`.python-version`), no 3.14 (precedente rompe-tu-agente: ecosistema atrasa).
- [ ] **Step 2:** `phase.py`: orquesta `tofu apply` → kubectl apply workloads → wait-for-healthcheck → warmup (parámetros por workload: Java JIT N min a carga objetivo; Mongo pre-warm con queries de calentamiento; Ollama primer prompt) → `k6 run` ×N (constant-arrival-rate, escenarios k6 en `runner/k6/*.js` con **VERIFY** sintaxis v2: module path v2, sin flags removidos) → capture → `tofu destroy` + verificación final (describe-instances filtrado por tag = 0 running). `require_sandbox()` primera línea. Flags `--workload java|mongo|inference|go`, `--arch x86|arm|both`, `--tuned on|off`, `--runs N`, `--dry-run`.
- [ ] **Step 3:** `capture.py`: k6 summary JSON + Prometheus queries (p99, throughput, CPU/mem de pods) + flame graph PNG por (workload, arch) desde Pyroscope UI/API + costo de fase (reloj × precio del día capturado en `results/cost.md`). Todo a `results/<fecha>/<workload>-<arch>[-tuned]/run-<i>/`.
- [ ] **Step 4:** `analysis/stats.py`: medianas, delta %, precio-rendimiento normalizado ($/op y $/Mtok), arco generacional chart. Unit tests contra JSONs fixture (`tests/fixtures/*.json`), sin AWS.
- [ ] **Step 5:** `cost.py`: ledger simple (fase, minutos, tipo instancia, tarifa del día, $) → total vs presupuesto; aborta si la fase excede su estimado (constraint: no surprise billing).
- [ ] **Step 6:** Commit `feat(runner): phase orchestrator, capture, analysis, cost ledger`.

*Recorte: `--tuned` y `--arch both` defaults se pueden acotar; el pipeline completo no.*

### Task 6.5: **Smoke gate del profiler** (nuevo, GATED, ~$10) [SPEC §5]

- [ ] **Step 1:** Antes de quemar el presupuesto del lab completo: clúster up (Task 4), profiler DaemonSet up, app Java deploy en ambos arch, carga 15 min. Inspección: ¿el flame graph muestra frames de Java legibles (no solo `[unknown]`) en AMBAS arquitecturas? ¿Mongo nativo resuelve símbolos? ¿Los overlays (kernel→libc→runtime) se ven?
- [ ] **Step 2:** Criterio de paso: cada workload tiene ≥1 flame graph legible por arch. Si Java no pasa: activar fallback async-profiler vía OTel SDK para Java (decisión documentada en README) y repetir smoke solo para Java. Destroy al terminar.
- [ ] **Step 3:** Commit resultados del gate + decisión en `results/profiler-gate.md`. **Este gate es una condición para Task 7.**

### Task 7: Corrida completa del laboratorio (GATED, ~$150-180) [SPEC §4-5]

- [ ] **Step 1:** 3 workloads × {m7i stock, m7i tuned (Java/Mongo), m9g} × n=3 + control Go n=3 por arch. Runner escribe todo a `results/`. Cluster abajo entre fases. Una tarde-noche de corrida efectiva (fin de semana 06-07/09).
- [ ] **Step 2:** Flame graphs exportados por (workload × arch), capturas de Grafana de las corridas reales. Pase de revisión de outliers (¿dispersión razonable? repetir celda si no).
- [ ] **Step 3:** `results/cost.md` con el desglose real por fase → slide 24.
- [ ] **Step 4:** Commit `results: full lab run <fecha>`.
- [ ] **Step 5:** Análisis: confirmar/reemplazar headline candidates (spec §2) con los números reales. **Recorte si Argentina abre el 07-08/09:** n=3 solo Java+inference (Mongo n=2, Go n=1 control), caveat dicho en voz alta en la slide de metodología. Regla del plan: prefiero dos workloads con n honesto que tres con n=1.

### Task 8: Arco generacional m5→M9g (GATED, Spot, ~$20-30) [SPEC §6]

- [ ] **Step 1:** Runner reusa la fase Java con override de MNG: m5/m6i/m7i + m6g/m7g/m8g/m9g, `.xlarge` donde exista (m5.xlarge sí), corrida única por generación, Spot (`capacity_type = "SPOT"`). **VERIFY** disponibilidad Spot por familia en us-east-1 ese día.
- [ ] **Step 2:** Chart de una línea (matplotlib) desde el JSON. Caveat narrado en la slide: corrida única, Spot, orientativo.
- [ ] **Step 3:** Commit `results: generational arc <fecha>`.

### Task 9: Escenas DaemonSets + Karpenter (GATED, baratísimo) [SPEC §3.5, §7]

- [ ] **Step 1:** Aplicar DaemonSet amd64-only (imagen amd64 pura, sin manifest) al clúster mixto → capturar `ImagePullBackOff`/`CrashLoopBackOff` real en nodos Graviton (`kubectl get pods -o wide` + describe). Es la escena slide 20.
- [ ] **Step 2:** Karpenter clip: scale-from-zero con NodePool multi-arch y pods sin affinity → capturar qué arch elige y a qué precio (describe nodeclaims). Grabados, <2 min juntos.
- [ ] **Step 3:** Commit `demo: daemonset blocker scene + karpenter clip`.

### Task 10: Plan B + sanitización [SPEC §1]

- [ ] **Step 1:** `demo/record.md`: qué grabar (1080p, terminal 20pt dark + Grafana + Pyroscope de la corrida Task 7 + escenas Task 9), duración <4 min, settings.
- [ ] **Step 2:** Completar `demo/sanitize-check.sh` real (grep de account IDs, ARNs, keys en results/assets/scripts) + corrida → `sanitize-check: clean` antes de commitear cualquier resultado o asset.
- [ ] **Step 3:** Commit `chore(demo): plan B recording script, sanitize check`.

### Task 11: Slides [SPEC §8]

- [ ] **Step 1:** `slides/contenido.md`: 25 content slides, headline + body (una idea por slide, diagramas > párrafos, código ≤15 líneas monospace) + speaker notes ES. Basado en los resultados reales de Tasks 7-9 — headline confirmado por datos, no speculado.
- [ ] **Step 2:** `slides/fuentes.md` (formato kcd): fecha + URL por cifra propia y de terceros. Incluye las citas de la doc EC2 processor-state-control (la "perilla que no existe") y el caveat Alpha del eBPF profiler (spec §5) — honestidad como material de slide.
- [ ] **Step 3:** Assets: charts matplotlib desde JSONs, flame graphs, capturas, diagrama de arquitectura (iconos oficiales AWS). Boundary: speaker pega en plantilla oficial.
- [ ] **Step 4:** Commit `feat(slides): contenido, fuentes, assets`.

### Task 12: README final [SPEC §1]

- [ ] **Step 1:** Versiones pinneadas con fecha de verificación, costo real del lab, orden de corrida completo (una sección "Reproducir"), deltas/gotchas aprendidos (StorageClass default, mounts en Bottlerocket, symbolization del profiler, tag m9g capacidad) — patrón "Deltas EKS vs kind" del kcd README.
- [ ] **Step 2:** Commit `docs: final README with real cost and deltas`.

---

## Risks

- **Waitlist abre con 5 días de notice** → recortes marcados por task arriba; headline con n honesto > amplitud con n=1.
- **Capacidad m9g.xlarge** → m9g.large ×2 pods (misma RAM/vCPU total), o m8g + caveat narrado.
- **Flame graphs ilegibles (symbolization Alpha)** → Task 6.5 lo detecta ANTES de la corrida cara; fallback async-profiler para Java documentado.
- **Presupuesto** → cost ledger con abort por fase; cluster-abajo verificado; Spot donde no arruina la medición (arco generacional).
- **Strands talk come la agenda (12-09)** → plan diseñado para ejecutarse de noche/fin de semana y congelarse limpio; Perú (03-10) es el escenario real, Colombia la garantía.
- **k6 v2 breaking changes** → VERIFY sintaxis contra release notes del día (module path v2, flags removidos) antes de escribir `runner/k6/*.js`.