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

- OpenTofu + `terraform-aws-modules/eks/aws` 21.25.0, provider aws ~> 6.53
- Karpenter v1.14.1 (chart OCI oficial) · Pyroscope 2.3.0 · k6 v2.2.0
- OTel eBPF profiler `otel/opentelemetry-collector-ebpf-profiler` (tag del día) · APerf (`kubectl-aperf`) · metrics-server (addon EKS)
- JDK 25 + `spring-petclinic-rest` (multi-arch) · Go (stdlib) · iperf3 · go-ycsb · MongoDB 8.0 y llama.cpp `server` imágenes oficiales
- EKS con Bottlerocket: `m8i.4xlarge` (x86, Xeon 6) vs `m9g.4xlarge` (Graviton5), un node group por celda stock/tuned

## El lab en una línea

```
 runner (Mac, sin tofu) ── escala MNG de la celda 0→1 ── aplica overlay (nodeSelector aad/cell)
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

## Estructura
```
apps/        java/ (spring-petclinic-rest sobre JDK 25), go/ (baseline stdlib),
             iperf3/, ycsb/ (go-ycsb, amd64 para loader), build-multiarch.sh (buildx → GHCR)
infra/       OpenTofu: EKS 21.25.0, 7 MNG (5 SUT por celda + loader + tools), Karpenter, metrics-server
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
nunca ejecuta tofu, español neutro para la audiencia.