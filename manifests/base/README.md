# Manifiestos del lab

Todo vive en el namespace `aad`. `manifests/base/` es lo que se instala una vez
por día de lab (observabilidad, perillas y StorageClass); `manifests/workloads/`
es lo que el runner aplica y borra celda por celda.

Cada valor fijado aquí fue verificado contra la documentación del día
(2026-09-04); las fuentes están citadas en los comentarios de cada archivo.

## Orden de instalación

```
# 1. StorageClass: gp2 viene marcada como default en EKS y no puede haber dos.
kubectl annotate storageclass gp2 \
  storageclass.kubernetes.io/is-default-class=false --overwrite

# 2. Namespace, StorageClass gp3 default, profiler eBPF y el DaemonSet de C-states.
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

`net-tuned-daemonset.yaml` **no** está en el kustomization a propósito. Es la
perilla de red y pertenece a un solo workload: dentro de la base también pinearía
las IRQ del ENA y apagaría el coalescing debajo de las celdas tuned de Java,
Mongo e inferencia, que quedarían comparadas contra su celda stock con una
perilla de más. El runner la aplica y la borra alrededor de la celda de red:

```
kubectl apply  -f manifests/base/net-tuned-daemonset.yaml   # solo celda net
kubectl delete -f manifests/base/net-tuned-daemonset.yaml   # al terminarla
```

Comprobación rápida:

```
kubectl -n aad get daemonset,pod -o wide
kubectl -n aad get pods -l app=cstates      # Ready = /dev/cpu_dma_latency en la
                                           #         latencia de salida de C1
kubectl -n aad get pods -l app=net-tuned    # Ready = TODAS las IRQ pineadas, RPS en 0
```

### El valor de la perilla de C-states es la latencia de C1, no 0

El DaemonSet `cstates` abre `/dev/cpu_dma_latency` y escribe **la latencia de
salida de C1 del nodo**
(`/sys/devices/system/cpu/cpu0/cpuidle/state1/latency`), no 0. La regla del
gobernador de cpuidle es una comparación contra la latencia de salida de cada
estado: los gobernadores "should never select any idle states with exit latency
beyond that limit"
(https://www.kernel.org/doc/html/latest/admin-guide/pm/cpuidle.html, leído
2026-09-04). Con ese límite C1 sigue disponible y C1E/C6 quedan afuera, que es
exactamente lo que pide la receta de AWS ("set C1 as the deepest C-state").
Con 0 quedaría afuera **también C1** y el único estado seleccionable sería POLL,
o sea la CPU girando en un bucle en vez de estar idle: otro experimento, y no el
que dice el slide.

El valor se escribe con el formato hexadecimal de 10 caracteres que documenta
`pm_qos_interface.rst` ("Alternatively, it can write a hex string for the value
using the 10 char long format e.g. '0x12345678'"), que es el único de los dos
formatos que un shell POSIX puede producir para un número cualquiera.

Las dos rutas (`PMQOS_DEV`, `C1_LATENCY`) son variables de entorno del contenedor
para poder correr el script contra un árbol sintético, sin nodo. Sacando el
`command` y el `readinessProbe` del YAML a dos archivos:

```bash
# El script lee state1/latency y escribe el hex de 10 caracteres exacto.
docker run --rm -v "$PWD/cstates-cmd.sh:/cmd.sh:ro" alpine:3.24.1 sh -c '
  mkdir -p /fake/cpuidle/state1 && printf 2 > /fake/cpuidle/state1/latency && : > /fake/dev
  PMQOS_DEV=/fake/dev C1_LATENCY=/fake/cpuidle/state1/latency sh /cmd.sh
  cat /fake/dev'                                    # -> 0x00000002

# La sonda, contra un "device" con el s32 que devolvería el kernel.
docker run --rm -v "$PWD/cstates-probe.sh:/probe.sh:ro" alpine:3.24.1 sh -c '
  mkdir -p /fake/cpuidle/state1 && printf 2 > /fake/cpuidle/state1/latency
  export PMQOS_DEV=/fake/dev C1_LATENCY=/fake/cpuidle/state1/latency
  printf "\002\000\000\000" > /fake/dev && sh /probe.sh; echo "match  -> $?"
  printf "\000\000\000\000" > /fake/dev && sh /probe.sh; echo "cero   -> $?"'
```

Un archivo común no es el device: al releerlo vuelven los bytes ASCII que se
escribieron, no el s32 agregado, así que el primer comando **falla a propósito**
en la relectura (`PM QoS request did not take: ... reads 808482864 us, wanted 2`).
Eso es justamente lo que se quiere ver: que el chequeo grita en vez de pasar de
largo. Lo que el árbol sintético sí prueba entero es el cálculo (leer C1,
formatear el hex) y la comparación de la sonda.

Los dos DaemonSets de perillas usan el `readinessProbe` como verificación real:
si la perilla no quedó puesta, el pod no pasa a Ready. No hay Service detrás, la
sonda es la señal. El de red recorre **todas** las IRQ y **todos** los
`rx-*/rps_cpus`: alcanza con que una sola cola se haya movido para que el pod no
pase a Ready.

## CPU exclusiva: el control que hace comparables las celdas

`requests = limits` solo compra QoS Guaranteed. Con la política por defecto del
CPU manager el kubelet aplica el límite con una cuota CFS y los hilos del pod
siguen paseando por los 16 vCPU, compartiéndolos con los DaemonSets y las IRQ.
Por eso las cinco celdas SUT arrancan con `settings.kubernetes.cpu-manager-policy
= "static"` en el user data (`infra/userdata/base.toml`, es un **control**, no una
perilla: va también en las celdas stock).

La regla es la de la documentación de Kubernetes: "Only containers that are both
part of a Guaranteed pod and have integer CPU requests are assigned exclusive
CPUs"
(https://kubernetes.io/docs/tasks/administer-cluster/cpu-management-policies/).
De ahí sale el resto del diseño de estos manifiestos:

- los pods de workload piden CPU **entera** y `requests = limits` (15; 7 en
  `x86-smtoff`), así que reciben un cpuset exclusivo;
- los DaemonSets piden milicores y con `limits` distintos de `requests`, así que
  son Burstable y viven en el pool compartido: el vCPU reservado los absorbe;
- el initContainer que descarga el GGUF también lleva `requests = limits`. La
  clase de QoS se calcula sobre los containers **y** los initContainers, así que
  uno solo sin límites dejaba al pod de inferencia en Burstable y sin CPU
  exclusiva — la única celda sin el control, justo la que mide ancho de banda.

Verificación el día del lab, dentro del pod medido:

```
kubectl -n aad exec deploy/java -- cat /sys/fs/cgroup/cpuset.cpus.effective
kubectl -n aad exec deploy/java -- grep Cpus_allowed_list /proc/self/status
# 15 vCPU y contiguos (por ejemplo 1-15). Si dice 0-15, la política no quedó
# puesta y la corrida no vale.
```

Las IRQ son otra historia: solo se reparten en la celda de red, donde ese reparto
es la perilla que se mide. En las demás celdas quedan donde las deja el kernel.

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
| `inference` | `x86-stock`, `x86-tuned`, `x86-t15`, `arm-stock`, `arm-tuned` | `llama.aad.svc:8080` |
| `net` | `x86-stock`, `x86-tuned`, `arm-stock`, `arm-tuned` | `iperf3-server.aad.svc:5201` |
| `go` | `x86-stock`, `arm-stock` | `go.aad.svc:8080` |

`x86-t15` no es un node group: corre sobre `aad/cell=x86-tuned` con `-t 15` para
medir el costo de sobresuscribir SMT (15 hilos sobre 8 cores físicos). El número
es 15 y no 16 porque con el CPU manager en `static` el pod es dueño exactamente
de los 15 vCPU que pide; `-t 16` habría sido el proceso sobresuscribiéndose a sí
mismo encima del SMT, con los dos efectos mezclados. Por lo mismo `arm-tuned` usa
`-t 15` y no `-t 16`, aunque el m9g.4xlarge tenga 16 cores físicos: el vCPU 16 es
el reservado.

Los Jobs no son parte de ningún kustomization; son plantillas que el runner
renderiza y aplica en orden:

| Archivo | Placeholders | Imagen propia |
|---|---|---|
| `workloads/mongo/base/ycsb-load-job.yaml` | `__NAME__` (carga fija de 20M registros) | `aad-ycsb:UNSET` |
| `workloads/mongo/base/ycsb-run-job.yaml` | `__NAME__`, `__WORKLOAD__`, `__OPERATIONCOUNT__`, `__THREADS__`, `__TARGET__` | `aad-ycsb:UNSET` |
| `workloads/net/base/iperf3-client-job.yaml` | `__NAME__`, `__CELL__` | `aad-iperf3:UNSET` |
| `workloads/net/base/iperf3-client-reverse-job.yaml` | `__NAME__`, `__CELL__` | `aad-iperf3:UNSET` |

`__NAME__` está en los cuatro porque el pod template de un Job es **inmutable**:
volver a aplicar un Job con un nombre que ya existe falla con "field is
immutable" en vez de arrancar la corrida siguiente. Un nombre por invocación
(`ycsb-run-<celda>-t<threads>-r<i>`) es lo único que hace re-aplicables las
plantillas, y además deja el historial legible en `kubectl get jobs`.

El Job de `run` lleva `-p recordcount=20000000`, el mismo valor que el de `load`.
No es redundante: `-P /workloads/workloada` trae el `recordcount=1000` del propio
archivo de workload, así que sin esa línea la corrida leería 1000 claves de una
colección de 20M — un benchmark de L2/L3 con etiqueta de DDR5, y con el control
de `pages read into cache` plano mientras pasa. Si se cambia, se cambia en los
dos Jobs.

### `UNSET`: por qué en git no hay registro (2026-09-04)

Las cuatro imágenes propias se referencian por **nombre pelado y tag centinela**:
`aad-java:UNSET`, `aad-go:UNSET`, `aad-iperf3:UNSET`, `aad-ycsb:UNSET`. Viven en
repositorios ECR **privados** de la cuenta sandbox (`infra/ecr/`), y el registro
es `<cuenta>.dkr.ecr.us-east-1.amazonaws.com`: escribirlo acá metería el id de
cuenta en el repo. Por eso no está, y por eso tampoco hay bloque `images:` en
ningún `base/kustomization.yaml`.

El registro y el tag los pone el runner, en el momento de renderizar:

- **Overlays**: `cell.py` escribe un kustomization descartable en un directorio
  temporal con `resources: [<overlay>]` y un `images:` con los cuatro nombres
  (`newName: <registro>/aad-<x>`, `newTag: <tag>`), y corre
  `kubectl kustomize` sobre él.
- **Plantillas de Job**: no son parte de ningún kustomization, así que `render()`
  sustituye el centinela en el mismo paso en el que llena los `__PLACEHOLDER__`.

El registro sale de `results/<fecha>/ecr.json` (`terraform -chdir=infra/ecr
output -json`, **git-ignored**, lleva el id de cuenta) y el tag, uno **por
imagen** (no uno solo para las cuatro), de `results/images.json` (lo escribe el
push gated, **sí se commitea**, no tiene datos de cuenta). Antes de escalar
cualquier node group el runner renderiza todo y se niega a seguir si queda un
`:UNSET`: llegaría al clúster como `ImagePullBackOff`, o sea quince minutos de
un 4xlarge pago. En `--dry-run` el overlay no se renderiza de verdad (`kubectl`
no corre bajo `--dry-run`), así que ese paso se salta y se dice; las plantillas
de Job sí se revisan, porque no dependen de ningún subproceso. Detalle completo
en `runner/README.md` y en `infra/ecr/README.md`.

## Versiones fijadas

| Componente | Pin | Fuente |
|---|---|---|
| Chart Pyroscope | `grafana/pyroscope` 2.2.1 (appVersion 2.2.1) | `helm search repo grafana/pyroscope --versions` |
| Profiler eBPF | `otel/opentelemetry-collector-ebpf-profiler:0.147.0` | docs de Grafana y `examples/otel-collector/ebpf/kubernetes` del repo de Pyroscope |
| MongoDB | `mongo:8.0.29` | Docker Hub, amd64 + arm64 |
| llama.cpp server | `ghcr.io/ggml-org/llama.cpp:server-b10775` | API de GHCR, amd64 + arm64 + s390x |
| Modelo | `unsloth/Llama-3.1-8B-Instruct-GGUF` / `Llama-3.1-8B-Instruct-Q4_0.gguf`, sha256 `88e2c600…ab0eaa` | cabeceras `x-linked-size` / `x-linked-etag` de Hugging Face |
| curl (initContainer) | `curlimages/curl:8.22.0` | Docker Hub, amd64 + arm64 |
| DaemonSets de perillas | `alpine:3.24.1`; `ethtool` **sin pin** | La imagen base sí está pineada, así que `apk add --no-cache ethtool` resuelve lo que v3.24 main traiga ese día; pinear `=7.0-r0` encima convierte un point release de Alpine en un DaemonSet que no arranca el día del lab. La versión usada queda impresa en el log del pod (`ethtool --version`) |

La versión de Pyroscope queda una menor atrás a propósito: el binario más nuevo
es v2.3.0 (2026-08-24) pero todavía no hay chart que lo traiga, y forzar el tag
de imagen sobre un chart que no lo probó es peor negocio que esperar.

## Al terminar el día de lab

El dataset de Mongo sobrevive entre celdas a propósito: un solo `ycsb-load` de
unos 15 minutos por día y el runner recalienta la cache en cada celda, en vez de
cargar 20M registros cinco veces. Por eso el StatefulSet lleva
`persistentVolumeClaimRetentionPolicy: {whenDeleted: Delete, whenScaled: Retain}`
y por eso hay que borrarlo explícitamente al final.

Eso lo hace `uv run cell --teardown-day`, y el orden completo del cierre (con el
volumen EBS del driver CSI, que no está en el estado de Terraform) vive en un
solo lugar: el README raíz, sección "Reproducir" → "Cierre del día de lab".

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
- Que el cpuset exclusivo quede puesto de verdad (`cpuset.cpus.effective` con 15
  vCPU dentro del pod medido) y que el vCPU reservado alcance para los DaemonSets
  que caen en la celda: kube-proxy, aws-node, ebs-csi-node, el profiler y las
  perillas suman unos 450m de `requests` sobre un solo core compartido.
- En x86 con SMT el vCPU reservado (cpu0) comparte core físico con uno de los 15
  hilos del pod. Es inherente a medir 15 de 16 vCPU y hay que decirlo en el
  slide, no esconderlo.
