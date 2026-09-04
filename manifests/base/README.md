# Manifiestos del lab

Todo vive en el namespace `aad`. `manifests/base/` es lo que se instala una vez
por día de lab (observabilidad, perillas y StorageClass); `manifests/workloads/`
es lo que el runner aplica y borra celda por celda.

Cada valor fijado acá fue verificado contra la documentación del día
(2026-09-04); las fuentes están citadas en los comentarios de cada archivo.

## Orden de instalación

```
# 1. StorageClass: gp2 viene marcada como default en EKS y no puede haber dos.
kubectl annotate storageclass gp2 \
  storageclass.kubernetes.io/is-default-class=false --overwrite

# 2. Namespace, StorageClass gp3 default, profiler eBPF y los dos DaemonSets de perillas.
kubectl apply -k manifests/base

# 3. Pyroscope (chart oficial, nodo tools).
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update grafana
helm upgrade --install pyroscope grafana/pyroscope \
  --version 2.2.1 \
  --namespace aad \
  -f manifests/base/pyroscope-values.yaml
```

El nombre del release importa: con `pyroscope` el chart resuelve su fullname a
`pyroscope` y el Service queda en `pyroscope.aad.svc:4040`, que es exactamente el
endpoint que el DaemonSet del profiler exporta por OTLP.

Comprobación rápida:

```
kubectl -n aad get daemonset,pod -o wide
kubectl -n aad get pods -l app=cstates      # Ready = /dev/cpu_dma_latency en 0 us
kubectl -n aad get pods -l app=net-tuned    # Ready = IRQ pineada y adaptive-rx off
```

Los dos DaemonSets de perillas usan el `readinessProbe` como verificación real:
si la perilla no quedó puesta, el pod no pasa a Ready. No hay Service detrás, la
sonda es la señal.

## Workloads

Un overlay por celda. `nodeSelector` de un solo valor (`aad/cell`) más la
toleration al taint `aad/sut=true:NoSchedule`, que es obligatoria porque es un
taint propio: el controlador de DaemonSet solo inyecta las de
`node.kubernetes.io/*`.

```
kubectl apply -k manifests/workloads/java/overlays/arm-tuned
kubectl delete -k manifests/workloads/java/overlays/arm-tuned
```

| Workload | Celdas (overlays) | Service |
|---|---|---|
| `java` | `x86-stock`, `x86-tuned`, `x86-smtoff`, `arm-stock`, `arm-tuned`, `x86-tuned-vthreads`, `arm-tuned-vthreads` | `java.aad.svc:9966` |
| `mongo` | `x86-stock`, `x86-tuned`, `arm-stock`, `arm-tuned` | `mongo.aad.svc:27017` |
| `inference` | `x86-stock`, `x86-tuned`, `x86-t16`, `arm-stock`, `arm-tuned` | `llama.aad.svc:8080` |
| `net` | `x86-stock`, `x86-tuned`, `arm-stock`, `arm-tuned` | `iperf3-server.aad.svc:5201` |
| `go` | `x86-stock`, `arm-stock` | `go.aad.svc:8080` |

`x86-t16` no es un node group: corre sobre `aad/cell=x86-tuned` con `-t 16` para
medir el costo de sobresuscribir SMT.

Los Jobs no son parte de ningún kustomization; son plantillas que el runner
renderiza y aplica en orden:

| Archivo | Placeholders |
|---|---|
| `workloads/mongo/base/ycsb-load-job.yaml` | ninguno (carga fija de 20M registros) |
| `workloads/mongo/base/ycsb-run-job.yaml` | `__WORKLOAD__`, `__OPERATIONCOUNT__`, `__THREADS__`, `__TARGET__` |
| `workloads/net/base/iperf3-client-job.yaml` | `__CELL__` |
| `workloads/net/base/iperf3-client-reverse-job.yaml` | `__CELL__` |

### `PUSH_DATE`

Las imágenes propias se referencian como `ghcr.io/andrezc98/aad-<x>:PUSH_DATE`.
`PUSH_DATE` es un placeholder literal: `apps/build-multiarch.sh` etiqueta con
`$(date +%F)` y el push a GHCR está gated. Cuando el push ocurra, se reemplaza el
placeholder por la fecha real (en el `images:` de cada `base/kustomization.yaml`
y en los cuatro archivos de Job) y se commitea.

## Versiones fijadas

| Componente | Pin | Fuente |
|---|---|---|
| Chart Pyroscope | `grafana/pyroscope` 2.2.1 (appVersion 2.2.1) | `helm search repo grafana/pyroscope --versions` |
| Profiler eBPF | `otel/opentelemetry-collector-ebpf-profiler:0.147.0` | docs de Grafana y `examples/otel-collector/ebpf/kubernetes` del repo de Pyroscope |
| MongoDB | `mongo:8.0.29` | Docker Hub, amd64 + arm64 |
| llama.cpp server | `ghcr.io/ggml-org/llama.cpp:server-b10775` | API de GHCR, amd64 + arm64 + s390x |
| Modelo | `unsloth/Llama-3.1-8B-Instruct-GGUF` / `Llama-3.1-8B-Instruct-Q4_0.gguf`, sha256 `88e2c600…ab0eaa` | cabeceras `x-linked-size` / `x-linked-etag` de Hugging Face |
| curl (initContainer) | `curlimages/curl:8.22.0` | Docker Hub, amd64 + arm64 |
| DaemonSets de perillas | `alpine:3.24.1` + `ethtool=7.0-r0` | Alpine v3.24 main, x86_64 y aarch64 |

La versión de Pyroscope queda una menor atrás a propósito: el binario más nuevo
es v2.3.0 (2026-08-24) pero todavía no hay chart que lo traiga, y forzar el tag
de imagen sobre un chart que no lo probó es peor negocio que esperar.

## Pendientes de verificar el día del gate

Nada de esto se puede confirmar sin un nodo Bottlerocket real:

- Si la política SELinux por defecto de Bottlerocket deja que un pod privileged
  escriba `/dev/cpu_dma_latency`. Si no, el plan B es el parámetro de kernel
  `intel_idle.max_cstate=1` por user data del node group, como ya se hace con THP.
- El nombre exacto de las IRQ de ENA en `/proc/interrupts` (el script falla
  ruidosamente si ninguna línea `eth0-Tx-Rx` aparece).
- Si la subred de los SUT tiene salida a internet para el `apk add ethtool` del
  DaemonSet de red. Si no, hay que hornear una imagen con ethtool.
- Que Pyroscope acepte de verdad los perfiles OTLP en 4040: la documentación lo
  confirma a nivel de configuración del collector, no a nivel de protocolo.
