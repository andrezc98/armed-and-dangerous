# ARMed and Dangerous — Implementation Plan (v2, 2026-09-03)

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Every dispatched subagent gets the verify-don't-guess rule verbatim (CLAUDE.md). Este plan se mantiene a nivel de diseño a propósito: CLAUDE.md prohíbe escribir manifiestos, flags o tags de memoria, así que el primer step de cada task es la verificación y los valores exactos se fijan ahí. Donde el valor ya fue verificado (spec §9) figura literal.

**Goal:** medir en EKS qué hace Graviton5 con tres clases de workload (Java, MongoDB, inference en CPU) + red + baseline Go, cada silicio llevado a su punto de quiebre en stock y tuned, explicar cada número con APerf (contadores PMU) y flame graphs de eBPF, y entregar el harness open source + slides para ARMed and Dangerous (ACD Perú 2026-10-03; Argentina 2026-09-12 solo si el waitlist abre con ≥7 días y el gate pasó; Colombia TBD).

**Architecture:** un clúster EKS por día de lab (OpenTofu, módulo eks 21.25.0) con siete managed node groups: cinco SUT (`x86-stock`, `x86-tuned`, `x86-smtoff` sobre `m8i.4xlarge`; `arm-stock`, `arm-tuned` sobre `m9g.4xlarge`) con `min=0,max=1` escalados por celda, más `loader` (`c7i.4xlarge`) y `tools` (`m7g.large`). Un runner Python orquesta celdas: escalar MNG → deploy con `nodeSelector aad/cell` → warmup → knee (k6 `ramping-arrival-rate` / YCSB threadcount) → corrida fija al 80% del knee ×n con ventana APerf → capture → escalar a 0. Imágenes propias multi-arch (buildx → GHCR) + oficiales para MongoDB y llama.cpp. DaemonSets: profiler eBPF (todos), C-states (x86 tuned), red (tuned, celda red). Resultados JSON commiteados → charts matplotlib → `slides/contenido.md` + assets.

**Tech Stack:** OpenTofu, terraform-aws-modules/eks 21.25.0, Bottlerocket, Karpenter v1.14.1, k6 v2.2.0, go-ycsb, iperf3, llama.cpp (imagen oficial), MongoDB 8.0, JDK 25 + spring-petclinic-rest, Go stdlib, OTel eBPF profiler 0.147.0, Pyroscope 2.3.0, APerf (kubectl-aperf), metrics-server, Python 3.13 + uv, matplotlib.

**Spec:** `docs/superpowers/specs/2026-09-02-armed-and-dangerous-design.md` (v2; leerla primero; cada task cita la sección que implementa).

## Global constraints

- **Verify every API/field/tag against current docs before writing it** (CLAUDE.md): Context7 / docs oficiales / GitHub releases del día; pin lo verificado y citarlo en README. Nothing from training memory — this stack moves monthly.
- **AWS is gated on the speaker.** Todo script que toca AWS llama `require_sandbox()` (copiado de `rompe-tu-agente/agent/config.py`; AWS_PROFILE debe contener `sandbox`) como primera línea; nada de `tofu apply/destroy`, escalado de MNG, push a registry ni corridas sin el speaker diciendo "go" (GATED). Nunca el perfil cliente por defecto de la máquina.
- **Presupuesto total ≤ $200 (techo); estimado v2 $40-70.** Runner lleva ledger reloj × tarifa por celda y aborta si el día de lab supera su estimado. Clúster abajo **entre días de lab** (`tofu destroy` humano al final del día + `aws ec2 describe-instances` filtrado por `Project=armed-and-dangerous` = 0 running). Entre celdas solo se escalan MNG a 0.
- **Español neutro todo lo que la audiencia ve** (slides, README, comentarios de resultados, speaker notes); nunca localizado al país anfitrión. Inglés el código, tests, commits.
- Naming: `aws-aad-*` (aws-<event>-<resource>) — p.ej. `aws-aad-eks-lab`, `aws-aad-subnet-a`; MNG `aws-aad-mng-<celda>`; tags `Project=armed-and-dangerous, Environment=lab, Owner=andres-zeballos, ManagedBy=tofu`.
- Sin emojis en código/salidas. Sin account IDs, ARNs con datos sensibles ni credenciales en nada commiteado; `demo/sanitize-check.sh` antes de commitear resultados o assets.
- Steps **GATED** = gasta AWS o push a registry. Pedir autorización al speaker antes del primero de cada tipo.
- Commit after every task, conventional messages. Repo root: `~/Documents/personal/charlas/armed-and-dangerous`.
- **Timeline (Strands talk es prioridad hasta el 12-09; esto corre en huecos):** Tasks 2-6 (gratis, local) 04-09/09 y 14-18/09 · **Task 6.5 gate 19/09** · **Task 7 corrida completa 20-21/09** (buffer 26-27/09) · Tasks 8-9 el 22-23/09 · Task 10-11 slides 24-30/09 · ensayo 01-02/10 · charla 03/10. Si el waitlist de Argentina abre: se decide con el gate en la mano; sin gate pasado y ≥7 días, no se presenta el lab ahí.
- **Recorte si hay que elegir:** Java + inference con n=3 antes que cinco escenas con n=1. Orden de recorte de celdas: red → Go → arco → celda `x86-smtoff` → virtual threads.

## File structure

| Path | Responsibility |
|---|---|
| `CLAUDE.md`, `README.md`, `.gitignore` | Reglas, reproducibilidad (versiones + fechas + costo), layout |
| `apps/java/` | Dockerfile multi-arch de `spring-petclinic-rest` sobre JDK 25 (o fallback `apps/java-min/`) |
| `apps/go/` | Baseline Go stdlib (`main.go`, Dockerfile) |
| `apps/iperf3/` | Imagen mínima iperf3 multi-arch |
| `apps/ycsb/` | Dockerfile de go-ycsb (amd64; corre en `loader`) |
| `apps/build-multiarch.sh` | Pipeline buildx → GHCR (entregable de la charla) |
| `infra/` | OpenTofu: EKS 21.25.0, 7 MNG, Karpenter, metrics-server, outputs |
| `manifests/base/` | Pyroscope values, profiler DaemonSet, C-states DaemonSet, net-tuned DaemonSet, StorageClass patch |
| `manifests/workloads/<workload>/` | kustomize base + overlays por celda (`nodeSelector aad/cell`, tolerations, requests/limits, flags stock/tuned) |
| `runner/` | Python 3.13 + uv: `cell.py` (orquestador), `knee.py`, `capture.py`, `cost.py`, `analysis/`, `k6/*.js`, `tests/` (sin AWS) |
| `results/` | JSONs crudos commiteados (n≥3 por celda), tarballs/HTML APerf, flame graphs PNG, `cost.md`, `profiler-gate.md` |
| `demo/` | `record.md` (plan B), `sanitize-check.sh` |
| `slides/` | `contenido.md`, `fuentes.md`, `assets/` |
| `docs/superpowers/{specs,plans}/` | Esta spec + plan |

---

### Task 1: Repo skeleton, rules, pins [SPEC §1] — HECHO (commit 335333d), con enmienda v2

**Files:** `CLAUDE.md` (modificar), `README.md` (modificar la sección "El lab en una línea" y "Estructura").

- [x] Steps 1-5 de v1 (skeleton, `.gitignore`, README esqueleto, stub sanitize, commit).
- [x] **Step 6:** `CLAUDE.md`: regla de idioma sin excepción de voseo; "cluster DOWN between phases" → "between lab days; SUT node groups scale to 0 between cells"; "the runner never runs tofu; scaling an MNG is GATED like apply"; sección "Sibling repos". (Hecho 2026-09-03.)
- [x] **Step 7:** `README.md`: diagrama de una línea actualizado (SUT por celda, loader, tools, APerf) y tabla "Estructura" según File structure de arriba. (Las menciones a m7i ya se corrigieron a m8i el 2026-09-03; falta el diagrama y la tabla.)
- [x] **Step 8:** Commit `docs: v2 rules (lab days, no tofu in runner, neutral spanish)`.

### Task 2: Las apps y los scripts de carga [SPEC §4]

**Files:** `apps/java/{Dockerfile,README.md}`, `apps/go/{main.go,main_test.go,Dockerfile}`, `apps/iperf3/Dockerfile`, `apps/ycsb/Dockerfile`, `runner/k6/{java.js,go.js,inference.js}`.

**Interfaces (produce):** imágenes `ghcr.io/<owner>/aad-java:<fecha>`, `aad-go:<fecha>`, `aad-iperf3:<fecha>`, `aad-ycsb:<fecha>`; contrato Java = endpoints de PetClinic REST; contrato Go = `GET /api/echo?n=<int>` que devuelve JSON `{ "n": n, "sum": <suma de 1..n> }`; scripts k6 leen `TARGET_URL`, `RATE`, `DURATION`, `MODE=knee|fixed` de env.

- [x] **Step 1 (VERIFY):** `spring-petclinic-rest` — versión de Spring Boot del repo y si soporta JDK 25; tag exacto de la imagen base `eclipse-temurin:25-jre` multi-arch del día; nombre de la propiedad de virtual threads en esa versión de Boot (`spring.threads.virtual.enabled`); endpoints reales (`/api/owners`, `/api/pets/{id}`, `/api/visits`) leyendo el OpenAPI del proyecto. Anotar todo en `apps/java/README.md` con fecha.
- [x] **Step 2:** `apps/java/Dockerfile` multi-stage: build del jar de PetClinic REST (perfil H2 en memoria) + runtime JDK 25; `JAVA_TOOL_OPTIONS` vacío por defecto (las flags stock/tuned las pone el overlay, no la imagen). **Time-box 2 h**: si JDK 25 + Boot no compila, escribir `apps/java-min/` (JDK 25 `HttpServer` + Jackson: `POST /api/transform` recibe JSON de 2 KB, lo parsea, ordena un arreglo interno, serializa) y documentar la decisión en README.
- [x] **Step 3:** `apps/go/main.go`: `net/http` stdlib, `GET /api/echo?n=`, JSON con `encoding/json`, `GOMAXPROCS` por defecto. `main_test.go`: un test de tabla (`n=0`, `n=10` → `sum=55`, `n` inválido → 400). Ejecutar `go test ./...` → PASS. Dockerfile `FROM golang:<tag del día> AS build` + `FROM gcr.io/distroless/static`.
- [x] **Step 4:** `apps/iperf3/Dockerfile`: `FROM alpine:<tag del día>` + `apk add --no-cache iperf3`, `ENTRYPOINT ["iperf3"]`. `apps/ycsb/Dockerfile`: build de go-ycsb desde el tag del día (**VERIFY** tag) para linux/amd64 (corre en `loader`).
- [x] **Step 5 (VERIFY k6 v2):** `runner/k6/java.js` y `go.js` con dos escenarios seleccionables por `MODE`: `ramping-arrival-rate` (stages de 200 a `RATE_MAX` req/s en pasos de 60 s; `preAllocatedVUs` alto) y `constant-arrival-rate` (`RATE`, `DURATION`); thresholds `http_req_duration{p(99)}` como métrica, no como abort. `inference.js`: `constant-arrival-rate` contra `/v1/chat/completions` con prompt fijo y `max_tokens` fijo, extrae `timings` (**VERIFY** nombre del campo en llama-server) a métricas custom. Salida `--summary-export` (**VERIFY** flag vigente en v2) a JSON.
- [x] **Step 6:** Smoke local en Mac: `docker build` de las cuatro imágenes (arm64 local), `docker run` Java y Go, `k6 run` 30 s en `MODE=fixed` contra cada uno, `iperf3 -s` / `-c localhost` entre dos contenedores. Anotar versiones resultantes en README.
- [x] **Step 7:** Commit `feat(apps): petclinic jdk25 image, go baseline, iperf3, ycsb, k6 scenarios`.

### Task 3: buildx multi-arch + GHCR [SPEC §4]

- [ ] **Step 1:** `apps/build-multiarch.sh`: `docker buildx build --platform linux/amd64,linux/arm64 --push` para `aad-java`, `aad-go`, `aad-iperf3` y `--platform linux/amd64` para `aad-ycsb`; tag = fecha ISO; `docker buildx imagetools inspect` al final para probar que ambos manifests existen. Fallback comentado: ECR del sandbox.
- [ ] **Step 2 (GATED push):** ejecutar con `GITHUB_TOKEN` local contra GHCR público. Guardar la salida de `imagetools inspect` en `results/images-<fecha>.txt`.
- [ ] **Step 3:** Commit `build: multi-arch pipeline (buildx, GHCR)`.

### Task 4: Infra EKS (OpenTofu) [SPEC §3, §3.5]

**Files:** `infra/{versions.tf,variables.tf,main.tf,nodegroups.tf,karpenter.tf,outputs.tf,example.tfvars}`, `infra/userdata/thp.toml`.

**Interfaces (produce):** outputs `cluster_name`, `configure_kubectl`, `nodegroup_names` (map celda → nombre MNG), `karpenter_nodepool_name`; etiqueta de nodo `aad/cell=<celda>`; taint `aad/sut=true:NoSchedule` en SUT; label `aad/role=loader|tools`.

- [ ] **Step 1 (VERIFY):** contra docs del día: strings `ami_type` `BOTTLEROCKET_x86_64`/`BOTTLEROCKET_ARM_64` en el módulo 21.x; `kubernetes_version` disponible (kcd probó 1.36); nombre exacto del addon `metrics-server`; sintaxis de `cpu_options` y `bootstrap_extra_args` en `eks-managed-node-group`; tabla TOML exacta de Bottlerocket para parámetros de kernel (spec §9, discussion 1989) y si `reboot-to-reconcile` existe en la versión de Bottlerocket del AMI.
- [ ] **Step 2:** `main.tf`: patrón kcd `infra-eks/` (VPC existente vía `var.vpc_id`, **una** subnet pública propia en una AZ, route table propia, IGW existente); módulo `terraform-aws-modules/eks/aws` `~> 21.25`, provider `aws ~> 6.53`, `authentication_mode = "API"`, `enable_cluster_creator_admin_permissions = true`; addons coredns, kube-proxy, vpc-cni (`before_compute`), ebs-csi-driver, metrics-server. Sin pod identity (no hay Bedrock).
- [ ] **Step 3:** `nodegroups.tf`: siete MNG según la tabla de spec §3. SUT: `min_size=0, max_size=1, desired_size=0`, `labels = { "aad/cell" = <celda> }`, taint `aad/sut=true:NoSchedule`; `x86-smtoff` con `cpu_options = { threads_per_core = 1 }` (**VERIFY** si también exige `core_count = 8`); `*-tuned` y `x86-smtoff` con `bootstrap_extra_args = file("userdata/thp.toml")`. `loader` y `tools` con `min=max=desired=1`, labels `aad/role`. Tags estándar en todo.
- [ ] **Step 4:** `karpenter.tf`: Karpenter v1.14.1 vía `helm_release` (chart OCI oficial) + IAM + una `NodePool` restringida a familias `m5,m6i,m7i,m8i,m6g,m7g,m8g,m9g` talla `4xlarge`, `limits` 1 nodo, y dos `EC2NodeClass` Bottlerocket (una por arquitectura) — **VERIFY** campos v1 del día. Solo para el arco (Task 8) y el clip (Task 9).
- [ ] **Step 5:** `outputs.tf` con los outputs de la interfaz. `tofu init && tofu validate` offline (sin credenciales); commitear `.terraform.lock.hcl`.
- [ ] **Step 6:** Commit `feat(infra): per-cell node groups (smt-off, thp), loader/tools, karpenter nodepool`.

### Task 5: Manifiestos: observabilidad, perillas y workloads [SPEC §3, §3.5, §4]

**Files:** `manifests/base/{pyroscope-values.yaml,ebpf-profiler.yaml,cstates-daemonset.yaml,net-tuned-daemonset.yaml,storageclass-default.yaml}`, `manifests/workloads/{java,mongo,inference,net,go}/{base,overlays/<celda>}/`.

**Interfaces (produce):** Services `java.aad.svc:8080`, `go.aad.svc:8080`, `mongo.aad.svc:27017`, `llama.aad.svc:8080`, `iperf3-server.aad.svc:5201`; overlays nombrados igual que las celdas de spec §3; DaemonSets con `nodeSelector` por `aad/cell` y tolerations al taint SUT.

- [ ] **Step 1 (VERIFY):** valores mínimos del chart de Pyroscope 2.3.0 (OTLP gRPC 4040, `limits.ingestion_relabeling_rules` con labelmap `process.executable.name → service_name`, nodeSelector `aad/role=tools`); manifiesto del profiler según docs Grafana (imagen `otel/opentelemetry-collector-ebpf-profiler:0.147.0` o tag del día, privileged, hostPID, mounts `/proc` `/sys/kernel`, `--feature-gates=+service.profilesSupport`, receiver `profiling` `samples_per_second: 97`, exporter OTLP a Pyroscope); tolerations `operator: Exists`.
- [ ] **Step 2:** `cstates-daemonset.yaml`: contenedor privileged con hostPath `/dev`, proceso que abre `/dev/cpu_dma_latency`, escribe `0` (int32) y duerme manteniendo el fd; `nodeSelector` `aad/cell in (x86-tuned, x86-smtoff)`. `net-tuned-daemonset.yaml`: privileged + `hostNetwork` + `hostPID`, script que apaga irqbalance si existe, fija afinidad de cada IRQ ENA a un núcleo distinto (`/proc/irq/*/smp_affinity_list`), `ethtool -C <if> adaptive-rx off`, verifica `rps_cpus = 0`; `nodeSelector` `aad/cell in (x86-tuned, arm-tuned)`; se aplica solo en la celda red. Ambos con un `readinessProbe` que falla si el ajuste no quedó (`cat /sys/devices/system/cpu/cpu0/cpuidle/state*/disable`, `cat /proc/irq/<n>/smp_affinity_list`).
- [ ] **Step 3:** `manifests/workloads/java`: Deployment 1 réplica, imagen `aad-java`, `resources` requests=limits `cpu: 15, memory: 48Gi` (deja margen a DaemonSets), Service; overlays `x86-stock`/`arm-stock` con `JAVA_TOOL_OPTIONS="-Xms24g -Xmx24g"`, overlays `*-tuned` y `x86-smtoff` con `-Xms24g -Xmx24g -XX:+UseTransparentHugePages -XX:-TieredCompilation -XX:ReservedCodeCacheSize=64M -XX:InitialCodeCacheSize=64M`; overlay adicional `-vthreads` que añade la propiedad de virtual threads. `x86-smtoff` con `cpu: 7`.
- [ ] **Step 4:** `manifests/workloads/mongo`: StatefulSet `mongo:8.0` (**VERIFY** tag), args `--wiredTigerCacheSizeGB 40`, PVC gp3 200Gi (StorageClass default parcheada: `storageclass-default.yaml`, golpe kcd), requests=limits `cpu: 15, memory: 56Gi`; Job `ycsb-load` (imagen `aad-ycsb`, en `loader`, `recordcount=20000000`, `workloada`) y Job template `ycsb-run` parametrizado por `WORKLOAD`, `THREADS`, `TARGET`, `OPERATIONCOUNT`.
- [ ] **Step 5:** `manifests/workloads/inference`: Deployment `ghcr.io/ggml-org/llama.cpp:server-<tag del día>`, initContainer que descarga el GGUF de Llama 3.x 8B Instruct Q4_0 a un `emptyDir` (**VERIFY** URL/hash del modelo y licencia), args `--parallel 4 -c 8192 --host 0.0.0.0 --port 8080` (**VERIFY** flags) + `-t` según overlay (stock: sin `-t`; `x86-tuned`: `-t 8`; `x86-t16`: `-t 16`; `arm-tuned`: `-t 16`).
- [ ] **Step 6:** `manifests/workloads/net`: Deployment `iperf3-server` (`aad-iperf3 -s`) con `podAntiAffinity` `requiredDuringScheduling` contra `iperf3-client` y Job template `iperf3-client` (`-c iperf3-server -P 8 -t 60 -J`, luego `-R`), ambos en la misma celda (MNG escalada a 2). `manifests/workloads/go`: Deployment + Service, `cpu: 15`, sin overlays de flags.
- [ ] **Step 7:** `kustomize build` de cada overlay pasa offline; `kubeconform` (o `kubectl apply --dry-run=client` contra kind local) sin errores.
- [ ] **Step 8:** Commit `feat(manifests): pyroscope, profiler, knob daemonsets, per-cell workload overlays`.

### Task 6: El runner (Python 3.13 + uv) [SPEC §5]

**Files:** `runner/{pyproject.toml,.python-version,config.py,cell.py,knee.py,capture.py,cost.py,analysis/__init__.py,analysis/stats.py,analysis/charts.py}`, `runner/tests/{test_stats.py,test_knee.py,test_cost.py,fixtures/*.json}`.

**Interfaces (produce):** CLI `uv run cell --workload java|mongo|inference|net|go --cell <celda> [--runs 3] [--dry-run]`; layout `results/<fecha>/<workload>/<celda>/run-<i>/{k6.json|ycsb.txt|iperf.json|llama.json,top.json,aperf/,flamegraph.png}` + `results/<fecha>/<workload>/<celda>/knee.json`; `analysis.stats.summarize(results_dir) -> dict` con medianas, knee, `usd_per_kop`, `usd_per_mtok`, `cpu_per_gbps`; `cost.ledger(results_dir) -> markdown`.

- [ ] **Step 1:** `pyproject.toml` con uv, Python 3.13 (`.python-version`; no 3.14, precedente rompe-tu-agente), deps mínimas (`boto3`, `httpx`, `pyyaml`, `matplotlib`); `kubectl`, `aws`, `kubectl-aperf` como CLIs externos versionados en README. `config.py`: copiar `require_sandbox()` de `rompe-tu-agente/agent/config.py` sin cambios + constantes de celdas: mapa overlay → MNG desde `tofu output -json` (`x86-stock`, `x86-tuned`, `x86-smtoff`, `arm-stock`, `arm-tuned` son 1:1; el overlay de inference `x86-t16` corre en la MNG `x86-tuned`; los overlays Java `x86-tuned-vthreads` y `arm-tuned-vthreads` corren en sus MNG tuned).
- [ ] **Step 2:** Test primero: `tests/test_knee.py` — dado un fixture de series k6 (rate → p99), `knee.find(series, slo_ms)` devuelve la última tasa con p99 ≤ SLO y `None` si ninguna cumple. Ejecutar → FAIL. Implementar `knee.py` (búsqueda lineal sobre los stages) → PASS.
- [ ] **Step 3:** Test primero: `tests/test_stats.py` — con tres `run-*/k6.json` de fixture, `summarize` da mediana y dispersión (min/max) y `usd_per_kop = tarifa_h / (rps*3600/1000)`; con fixture `llama.json`, `usd_per_mtok`; con fixture `iperf.json` + `top.json`, `cpu_per_gbps`. FAIL → implementar `analysis/stats.py` → PASS.
- [ ] **Step 4:** Test primero: `tests/test_cost.py` — ledger suma `minutos × tarifa/60` por celda y marca `OVER_ESTIMATE` si supera el estimado del día. FAIL → `cost.py` → PASS. Tarifas se leen de `results/cost.md` (capturadas el día del lab, nunca hardcodeadas).
- [ ] **Step 5:** `cell.py` (sin tests unitarios, `--dry-run` imprime el plan de comandos): `require_sandbox()` → `aws eks update-nodegroup-config --scaling-config desiredSize=1` (2 para `net`) → esperar nodo Ready con label `aad/cell` → `kubectl apply -k manifests/workloads/<w>/overlays/<celda>` (+ DaemonSets de perilla si la celda es tuned) → healthcheck → warmup (Java 3 min a carga; Mongo: `ycsb-load` si no existe + lecturas hasta que `serverStatus` muestre `pages read into cache` plano; llama: un prompt) → knee (Job k6 `MODE=knee` en `loader` / Jobs YCSB con threadcount 16, 32, 64, 128) → guard loader (`kubectl top node` < 70% o abortar) → por cada run: lanzar `kubectl aperf` en el nodo SUT (**VERIFY** sintaxis del plugin y flags `record -i 1 -p <segundos>`), Job de carga fija al 80% del knee, recoger salidas, `kubectl top pod/node` cada 10 s a `top.json`, exportar PNG de Pyroscope por `service_name` (**VERIFY** endpoint de render) → `desiredSize=0` → ledger.
- [ ] **Step 6:** `analysis/charts.py`: barras por celda (knee), tok/s y $/Mtok, CPU/Gbps, línea del arco; salida PNG a `slides/assets/`. Un test de humo que renderiza con fixtures sin error.
- [ ] **Step 7:** Commit `feat(runner): cell orchestrator, knee, capture, cost ledger, analysis`.

### Task 6.5: Smoke gate (GATED, ~$8, medio día) [SPEC §3.5, §5]

Condición para Task 7. Todo con el clúster de un día de lab (`tofu apply` humano).

- [ ] **Step 1:** Escalar `x86-tuned` y `arm-tuned` a 1. Anotar el **stock real** leyendo en cada nodo (pod privileged): `/sys/kernel/mm/transparent_hugepage/enabled`, `nproc`, `lscpu` (threads per core), `/sys/devices/system/cpu/cpu0/cpuidle/state*/name` (¿hay > C1 en m8i?), presencia de `irqbalance`. Comprobar que el nodo tuned muestra `[always]` y que `x86-smtoff` (escalar aparte) muestra 8 CPUs.
- [ ] **Step 2:** Aplicar profiler + Pyroscope; deploy Java en ambas arquitecturas, 15 min de carga fija. ¿Frames Java legibles (no solo `[unknown]`) en AMBAS? ¿Mongo y llama nativos resuelven símbolos? Si Java no pasa: fallback async-profiler vía OTel SDK solo para Java, documentado.
- [ ] **Step 3:** `kubectl aperf` en cada SUT durante 2 min de carga: ¿graba en Bottlerocket (perf, `/boot`, PMU en guest)? Generar un `aperf report` comparando x86 vs arm. Si no graba: anotar la limitación; el porqué se sostiene con knee + flame graphs.
- [ ] **Step 4:** Mongo: `ycsb-load` completo + 5 min de `workloadb`; `pages read into cache` debe quedar plano. Red: iperf3 60 s m9g↔m9g con y sin DaemonSet tuned; el readiness del DaemonSet debe pasar.
- [ ] **Step 5:** Knee de Java en `arm-tuned` con el guard del loader activo: CPU del loader < 70% en el knee o subir la talla de `loader` antes de Task 7.
- [ ] **Step 6:** Escalar todo a 0, `tofu destroy`, verificar 0 instancias. Commit `results/profiler-gate.md` con cada lectura y decisión: `results: smoke gate <fecha>`.

### Task 7: Corrida completa del laboratorio (GATED, ~$25-35, dos días de lab) [SPEC §4-5]

- [ ] **Step 1 (día 1):** `tofu apply`. Java 5 celdas + 2 de virtual threads (≈5.5 h) y Go 2 celdas (≈1.2 h), n=3. Ledger al cierre; `tofu destroy`; 0 instancias.
- [ ] **Step 2 (día 2):** `tofu apply`. Mongo 4 celdas (≈3.2 h), inference 5 celdas (≈2.8 h), red 4 celdas (≈0.8 h), n=3. Ledger; destroy; 0 instancias.
- [ ] **Step 3:** Pase de outliers: dispersión razonable por celda; repetir la celda si no. Exportar flame graphs por celda, reportes APerf stock vs tuned por arquitectura, capturas de Pyroscope.
- [ ] **Step 4:** `results/cost.md` con desglose real por workload → slide 24. Commit `results: full lab run <fechas>`.
- [ ] **Step 5:** Análisis: confirmar/reemplazar headline candidates (spec §2) con números reales; escribir la frase de tuning en su forma verificada (verify, don't attack).

### Task 8: Arco generacional m5→M9g (GATED, on-demand, ~$2-3) [SPEC §6]

- [ ] **Step 1:** Con la NodePool de Karpenter: por generación, parchear el requirement `node.kubernetes.io/instance-type` a `<familia>.4xlarge`, desplegar Java (overlay stock con nodeSelector por instance-type), corrida fija corta (5 min) una vez, capturar. **VERIFY** disponibilidad on-demand por familia en la AZ ese día.
- [ ] **Step 2:** Chart de una línea desde el JSON (`analysis/charts.py`). Caveat en la slide: corrida única, orientativo; corroboración de terceros (Spare Cores, Phoronix).
- [ ] **Step 3:** Commit `results: generational arc <fecha>`.

### Task 9: Escenas DaemonSets + Karpenter (GATED, ~$1) [SPEC §3.5, §7]

- [ ] **Step 1:** Aplicar un DaemonSet amd64-only (imagen amd64 pura, sin manifest multi-arch) al clúster con un nodo de cada arquitectura → capturar `ImagePullBackOff`/`CrashLoopBackOff` real en Graviton (`kubectl get pods -o wide` + `describe`). Escena slide 21; mostrar al lado los `nodeSelector` del profiler y de los DaemonSets de perilla.
- [ ] **Step 2:** Karpenter clip: scale-from-zero con la NodePool y pods sin affinity → capturar qué tipo elige y a qué precio (`describe nodeclaims`). Grabados, <2 min juntos.
- [ ] **Step 3:** Commit `demo: daemonset blocker scene + karpenter clip`.

### Task 10: Plan B + sanitización [SPEC §1]

- [ ] **Step 1:** `demo/record.md`: qué grabar (1080p, terminal 20pt dark + Pyroscope + reporte APerf de la corrida Task 7 + escenas Task 9), duración <4 min, settings.
- [ ] **Step 2:** Reemplazar el stub por `rompe-tu-agente/demo/sanitize-check.sh` (copiar; ajustar rutas a `results/`, `slides/assets/`, `infra/`); correr → `sanitize-check: clean`.
- [ ] **Step 3:** Commit `chore(demo): plan B recording script, sanitize check`.

### Task 11: Slides [SPEC §8]

- [ ] **Step 1:** `slides/contenido.md`: 25 content slides según spec §8, headline + body (una idea por slide, diagramas > párrafos, código ≤15 líneas monospace) + speaker notes ES. Basado en resultados reales de Tasks 7-9 — headline confirmado por datos. Orden de recorte si el ensayo pasa de 30 min: 19, luego 12.
- [ ] **Step 2:** `slides/fuentes.md` (formato kcd): fecha + URL por cifra propia y de terceros; incluye la cita EC2 de processor state control, la de CPU options (SMT off sin cambio de precio), el caveat Alpha del profiler, Spare Cores y Phoronix, y las tarifas capturadas el día del lab.
- [ ] **Step 3:** Assets: charts desde JSONs, flame graphs, capturas Pyroscope y APerf, diagrama de arquitectura (iconos oficiales AWS). Boundary: speaker pega en plantilla oficial.
- [ ] **Step 4:** Commit `feat(slides): contenido, fuentes, assets`.

### Task 12: README final [SPEC §1]

- [ ] **Step 1:** Versiones pinneadas con fecha de verificación, costo real del lab, orden de corrida completo (sección "Reproducir": apply → gate → días 1 y 2 → arco → destroy), deltas/gotchas (StorageClass default, TOML de Bottlerocket para THP, cpuidle en guest, APerf en Bottlerocket, simbolización del profiler, capacidad m9g.4xlarge por AZ) — patrón "Deltas EKS vs kind" del kcd README.
- [ ] **Step 2:** Commit `docs: final README with real cost and deltas`.

---

## Risks

- **PetClinic REST no compila en JDK 25** → time-box 2 h y fallback `apps/java-min/` (Task 2).
- **APerf no graba en Bottlerocket** (perf/PMU en guest, `/boot`) → gate lo detecta; el porqué se sostiene con knee + flame graphs y se dice en la slide 8.
- **Flame graphs ilegibles (symbolization Alpha)** → gate antes de la corrida cara; fallback async-profiler para Java.
- **THP no aplica por TOML** (nombre de tabla / versión de Bottlerocket) → alternativa bootstrap container en el gate; el stock real siempre se lee y anota.
- **Mongo se va a disco** → control `pages read into cache` en gate y en cada corrida; si sube, bajar `recordcount`.
- **Loader saturado** → guard 70%; subir `loader` a `c7i.8xlarge` (+$0.7/h) antes de Task 7.
- **Capacidad m9g.4xlarge** → cambiar AZ completa antes que talla; `m8g.4xlarge` solo con caveat.
- **Presupuesto** → ledger con abort por día; clúster abajo entre días verificado; estimado v2 $40-70 contra techo $200.
- **Strands talk come la agenda (12-09)** → nada GATED antes del 19-09; Perú (03-10) es el escenario real, Colombia la garantía.
- **k6 v2 breaking changes** → VERIFY sintaxis contra release notes del día antes de escribir `runner/k6/*.js`.
- **Densidad del deck (25 en 30 min)** → orden de recorte fijado (19, 12) y ensayo cronometrado el 01-10.
