# ARMed and Dangerous: lo que Graviton5 hace con tus workloads, medido en EKS

Demo repo de la charla (AWS Community Day Argentina 2026, waitlist → ACD Perú
2026 → AWS Women Colombia 2026): tres clases de workload — Java de alta
concurrencia, MongoDB y inferencia LLM en CPU — medidas en el mismo clúster
EKS con nodos x86 (`m8i`) y Graviton5 (`m9g`), explicadas con flame graphs de
eBPF (señal de Profiles de OpenTelemetry) y un harness open source completo.

> Slides: `slides/contenido.md` · fuentes y caveats de cada número:
> `slides/fuentes.md` · spec y plan: `docs/superpowers/`

## Versiones probadas
(se llena con cada corrida; verificar contra docs del día antes de confiar)

- Terraform >= 1.15 + `terraform-aws-modules/eks/aws` 21.25.0, provider aws ~> 6.63, provider helm ~> 3.3, EKS 1.36 con Bottlerocket >= 1.64.0 (ver `infra/README.md`)
- Karpenter v1.14.1 (chart OCI oficial) · Pyroscope 2.3.0 · k6 v2.2.0
- OTel eBPF profiler `otel/opentelemetry-collector-ebpf-profiler` (tag del día) · APerf (`kubectl-aperf`) · metrics-server (addon EKS)
- Apps (verificado y probado en local 2026-09-03, ver `apps/*/Dockerfile`): `spring-petclinic-rest` master@`4cd8e1b0` (v4.0.2, Boot 4.1.1) sobre `eclipse-temurin:25.0.4_7-jre-noble`, build `maven:3.9.16-eclipse-temurin-25-noble` · Go `golang:1.27.1` + `gcr.io/distroless/static-debian13:nonroot` · `alpine:3.24.1` + iperf3 3.20-r0 · go-ycsb v1.0.3 · k6 `grafana/k6:2.2.0` (imagen oficial, amd64+arm64)
- Pendientes de Task 5: MongoDB 8.0 y llama.cpp `ghcr.io/ggml-org/llama.cpp:server-b10775` (imágenes oficiales; modelo `unsloth/Llama-3.1-8B-Instruct-GGUF` Q4_0, ver spec §9)
- EKS con Bottlerocket: `m8i.4xlarge` (x86, Xeon 6) vs `m9g.4xlarge` (Graviton5), un node group por celda stock/tuned

## El lab en una línea

```
 runner (Mac, sin terraform) ── escala MNG de la celda 0→1 ── aplica overlay (nodeSelector aad/cell)
        │
        ▼
 loader c7i.4xlarge ─ k6 / go-ycsb / iperf3 -c ─▶ SUT de la celda (1 pod, taint aad/sut)
                                                   x86-stock | x86-tuned | x86-smtoff  (m8i.4xlarge)
                                                   arm-stock | arm-tuned               (m9g.4xlarge)
                                                      │            │
                                   kubectl aperf ─────┘            └── DaemonSet profiler eBPF
                                   (PMU: IPC, stalls, TLB)              ─▶ Pyroscope (tools m7g.large)
        │                                                                     ─▶ flame graphs
        └── knee (ramping) → fija 80% ×n → JSON + tarball APerf + PNG ─▶ results/ ─▶ charts ─▶ slides
```

Una celda = un silicio en una configuración (stock / tuned / SMT off). Cada
workload corre en todas sus celdas; el clúster queda abajo entre días de lab.

## Reproducir
(completar en el Task 12 con el orden real de corrida y el costo medido)

### Imágenes multi-arch
`apps/build-multiarch.sh` construye con `docker buildx` las cuatro imágenes
(`aad-java`, `aad-go`, `aad-iperf3` en `linux/amd64,linux/arm64`; `aad-ycsb`
solo en `linux/amd64`, porque el loader es x86). Prueba local sin tocar
ningún registro (exporta un tarball OCI por imagen bajo `apps/build-out/` y
valida que cada tarball tenga las plataformas esperadas):

```
PUSH=0 apps/build-multiarch.sh
```

Push a GHCR (`ghcr.io/andrezc98`) con `docker buildx imagetools inspect` al
final de cada imagen para confirmar ambos manifests: **queda gated** hasta
que el speaker lo autorice explícitamente. El push se realiza sin attestations
de provenance ni SBOM (el script pasa `--provenance=false --sbom=false`);
quitar las dos flags si se requieren attestations.

```
PUSH=1 apps/build-multiarch.sh
```

## Estructura
```
apps/        java/ (spring-petclinic-rest sobre JDK 25), go/ (baseline stdlib),
             iperf3/, ycsb/ (go-ycsb, amd64 para loader), build-multiarch.sh (buildx → GHCR)
infra/       Terraform: EKS 21.25.0, 7 MNG (5 SUT por celda + loader + tools), Karpenter, metrics-server
manifests/   base/ (Pyroscope, profiler eBPF, DaemonSets de perillas: C-states y red, StorageClass)
             workloads/<java|mongo|inference|net|go>/ (kustomize base + overlays por celda)
runner/      Python 3.13 + uv: cell.py (orquestador), knee.py, capture.py, cost.py, analysis/, k6/*.js, tests/
results/     JSONs crudos (n≥3 por celda), tarballs/HTML APerf, flame graphs PNG, cost.md, profiler-gate.md
slides/      contenido.md + fuentes.md + assets/ (entregable para la plantilla oficial)
demo/        record.md (plan B grabado) + sanitize-check.sh
docs/        superpowers/{specs,plans}/ (spec y plan v2)
```

## Reglas del repo
Ver `CLAUDE.md`: verify-don't-guess, sandbox gate (perfil cliente prohibido),
presupuesto $200 (estimado v2 $40-70), clúster abajo entre días de lab, el runner
nunca ejecuta terraform, español neutro para la audiencia.