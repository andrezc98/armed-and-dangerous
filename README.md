# ARMed and Dangerous: lo que Graviton5 hace con tus workloads, medido en EKS

Demo repo de la charla (AWS Community Day Argentina 2026, waitlist → ACD Perú
2026 → AWS Women Colombia 2026): tres clases de workload — Java de alta
concurrencia, MongoDB y inferencia LLM en CPU — medidas en el mismo clúster
EKS con nodos x86 (`m7i`) y Graviton5 (`m9g`), explicadas con flame graphs de
eBPF (señal de Profiles de OpenTelemetry) y un harness open source completo.

> Slides: `slides/contenido.md` · fuentes y caveats de cada número:
> `slides/fuentes.md` · spec y plan: `docs/superpowers/`

## Versiones probadas
(se llena con cada corrida; verificar contra docs del día antes de confiar)

- OpenTofu + `terraform-aws-modules/eks/aws` 21.25.0, provider aws ~> 6.53
- Karpenter v1.14.1 (chart OCI oficial) · Pyroscope 2.3.0 · k6 v2.2.0
- OTel eBPF profiler (receiver `otelcol-ebpf-profiler`, tag del día)
- JDK 25 (multi-arch) · Go (stdlib) · MongoDB y Ollama imágenes oficiales
- EKS con Bottlerocket: `m7i.xlarge` (x86) vs `m9g.xlarge` (Graviton5)

## El lab en una línea

```
   k6 (constant-arrival-rate) ─▶ workload pod (nodeSelector arch)
                                       │
   OTel eBPF profiler (DaemonSet) ─▶ Pyroscope ─▶ flame graphs por arquitectura
                                       │
   Prometheus 3 ─▶ Grafana (p99, throughput)   runner Python: fase → JSON → chart
```

## Reproducir
(completar en el Task 12 con el orden real de corrida y el costo medido)

## Estructura
```
apps/        Java JDK 25 (platform/virtual threads), Go control, mongo-seed
infra/       OpenTofu: EKS dual-arch (m7i + m9g) + Karpenter NodePool
manifests/   Prometheus, Grafana, Pyroscope, DaemonSets (profiler eBPF, c-states), workloads
runner/      Orquestador de fases Python 3.13 (k6 ×N, capture, costo)
results/     JSONs crudos (n≥3), flame graphs, cost.md
slides/      contenido.md + fuentes.md + assets (entregable para la plantilla oficial)
demo/        plan B (record.md) + sanitize-check.sh
```

## Reglas del repo
Ver `CLAUDE.md`: verify-don't-guess, sandbox gate (perfil cliente prohibido),
presupuesto $200, clúster abajo entre fases, español para la audiencia.