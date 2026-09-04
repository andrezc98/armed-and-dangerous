# runner — el orquestador de celdas

Una celda es un silicio en una configuración (`arm-tuned`, `x86-smtoff`, …) con
un workload encima. `cell.py` la corre de punta a punta: sube la node group,
despliega el overlay, calienta, busca el knee, mide n veces al 80 % del knee,
baja la node group a cero y escribe el ledger del día.

Todo lo que hace hacia afuera pasa por `config.sh()`, así que
`--dry-run` imprime el plan de comandos exacto y no toca nada. La primera línea
de cualquier entrypoint es `require_sandbox()`: sin un `AWS_PROFILE` cuyo nombre
contenga `sandbox`, el runner se niega a arrancar (copiado tal cual de
`rompe-tu-agente/agent/config.py`).

## CLIs externas

El runner no habla con AWS ni con Kubernetes desde Python: shell-out y nada más.
Por eso no hay `boto3` — la CLI de AWS ya respeta `AWS_PROFILE` y tener dos
caminos de credenciales sería un camino de más para auditar.

| CLI | Versión usada | Para qué |
|---|---|---|
| `uv` | 0.10.9 | entorno y CLI (`uv run cell`) |
| CPython | 3.13.12 (`.python-version` fija 3.13) | intérprete |
| `kubectl` | v1.33.9 (cliente; el clúster es 1.36) | jobs, overlays, `top`, `exec`, `port-forward` |
| `kubectl aperf` | plugin de aws/aperf v1.2.3 | grabación por corrida en el nodo SUT |
| `aws` | aws-cli 2.36.32 | `eks update-nodegroup-config` y `ec2 describe-volumes`, siempre con `--region us-east-1` (`config.REGION`) |

**Terraform no aparece en esa tabla a propósito: el runner no lo ejecuta nunca.**
El `apply`, el `destroy` y el `terraform output` los corre una persona (ver
`infra/README.md`); lo único que el runner mueve es `desiredSize` de una managed
node group. De ahí el paso de `cluster.json` que sigue.

Instalar el plugin de APerf (verbatim de `docs/README-EKS.md` de aws/aperf,
leído 2026-09-04):

```bash
sudo cp kubectl-aperf /usr/local/bin/ && sudo chmod +x /usr/local/bin/kubectl-aperf
kubectl aperf --help
```

## Versiones fijadas y de dónde salieron (verificado 2026-09-04)

| Qué | Pin | Fuente |
|---|---|---|
| `httpx` | 0.28.1 | https://pypi.org/pypi/httpx/json |
| `pyyaml` | 6.0.3 | https://pypi.org/pypi/pyyaml/json |
| `matplotlib` | 3.11.1 | https://pypi.org/pypi/matplotlib/json |
| `pytest` (dev) | 9.1.1 | https://pypi.org/pypi/pytest/json |
| Imagen de k6 | `grafana/k6:2.2.0` | `docker run --rm --entrypoint sh grafana/k6:2.2.0 -c 'echo ok; k6 version'` → `ok` / `k6 v2.2.0 (commit/00a9a1b7f5, go1.26.5, linux/arm64)`: la imagen **sí** trae `/bin/sh`, que es lo que necesita el `command` del Job para capturar el código de salida y el resumen |
| Sintaxis de APerf | `kubectl aperf --node=<nodo> --aperf_options="-i 1 -p <segundos>" --namespace=aad` | https://github.com/aws/aperf/blob/main/docs/README-EKS.md — el plugin **no** tiene subcomando `record`; los flags clásicos viajan dentro de `--aperf_options`, y `-i, --interval` / `-p, --period` son del binario (https://github.com/aws/aperf/blob/main/README.md) |
| Reporte de APerf | `aperf report -r <RUN1> <RUN2> ... -n <NOMBRE>` | mismo README: un solo `-r` seguido de varias corridas, no `-r a -r b`. El runner no lo corre: el plugin ya genera el reporte de la corrida adentro del pod y se copia el tarball |
| Render de Pyroscope | `GET /pyroscope/render?query=process_cpu:cpu:nanoseconds:cpu:nanoseconds{service_name="<svc>"}&from=<unix>&until=<unix>&format=json` | https://grafana.com/docs/pyroscope/latest/reference-server-api/ — `query` y `from` son obligatorios; `format` solo acepta `json` y `dot`. **No hay PNG**: por eso el layout guarda `flamegraph.json` y las imágenes de los slides son capturas de la UI de Pyroscope |
| Escalado de celdas | `aws eks update-nodegroup-config --cluster-name <c> --nodegroup-name <ng> --scaling-config desiredSize=<n>` | `aws eks update-nodegroup-config help` (aws-cli 2.36.32): la estructura `--scaling-config` acepta `minSize`, `maxSize`, `desiredSize` |
| Esperar el borrado de un Job | `kubectl wait --for=delete job/<nombre> -n aad --timeout=60s` | https://kubernetes.io/docs/reference/kubectl/generated/kubectl_wait/ — `--for` acepta `[create\|delete\|condition=...\|jsonpath=...]`, y el ejemplo es literal: "Wait for the pod "busybox1" to be deleted, with a timeout of 60s, after having issued the "delete" command". Devuelve error si el objeto nunca existió, que es el caso normal, así que va con `check=False` |
| Columnas de `kubectl top` | nodo: `NAME CPU(cores) CPU(%) MEMORY(bytes) MEMORY(%)`; pod: `NAME CPU(cores) MEMORY(bytes)` | kubectl 1.33, `staging/src/k8s.io/kubectl/pkg/metricsutil/metrics_printer.go`: `NodeColumns = []string{"NAME", "CPU(cores)", "CPU(%)", "MEMORY(bytes)", "MEMORY(%)"}` y `PodColumns = []string{"NAME", "CPU(cores)", "MEMORY(bytes)"}`, con la CPU impresa como `%vm` y la memoria como `%vMi`. **El listado de pods no trae porcentaje**: son dos parsers, no uno |
| Nodo del pod de iperf3 | `kubectl -n aad get pod -l app=iperf3-server -o jsonpath='{.items[0].spec.nodeName}'` | https://kubernetes.io/docs/reference/kubernetes-api/workload-resources/pod-v1/ — `nodeName` (string) en `PodSpec`: "NodeName is a request to schedule this pod onto a specific node" |
| cpuset de la celda de Go | `kubectl get --raw /api/v1/namespaces/aad/services/go:8080/proxy/healthz` | https://kubernetes.io/docs/tasks/access-application-cluster/access-cluster-services/ — la forma es `.../services/[https:]<service_name>[:port_name]/proxy`, y `<service_name>:<port_name>` "proxies to the specified port name or port number using http" ("You can also use the port number in place of the *port_name*"). Del otro lado, `runtime.NumCPU()` "returns the number of logical CPUs usable by the current process" (https://pkg.go.dev/runtime#NumCPU), o sea respeta la máscara de afinidad |
| Sub-métricas por escalón del knee | thresholds sobre `http_req_failed{rate:R}` (`rate<0.01`) y `http_reqs{rate:R}` (`count>0`) | un threshold sobre una sub-métrica etiquetada es lo que hace que k6 la reporte; verificado con `docker run --rm -v $PWD/runner/k6:/scripts:ro grafana/k6:2.2.0 run --quiet -e MODE=knee ... -e SUMMARY_PATH=/dev/stdout /scripts/go.js`, cuyo resumen trae `http_reqs{rate:10}` y `http_req_failed{rate:10}` |

`service_name` sale de la regla de reetiquetado del chart de Pyroscope
(`labelmap process.executable.name → service_name`, en
`manifests/base/pyroscope-values.yaml`), así que es el nombre del ejecutable:
`java`, `aad-go`, `mongod`, `llama-server`, `iperf3`.

## Correr una celda

```bash
# Primera línea del día de lab, siempre: el perfil sandbox tiene us-west-2 por
# default y el lab vive en us-east-1.
export AWS_PROFILE=<perfil-sandbox> AWS_REGION=us-east-1

cd runner
uv sync

# El plan completo, sin tocar nada:
uv run cell --workload java --cell arm-tuned --dry-run

# La corrida de verdad (GATED: el clúster ya tiene que estar aplicado):
uv run cell --workload java --cell arm-tuned --runs 3
```

Antes de la primera celda del día hacen falta tres archivos que escribe una
persona, no el runner:

1. **`results/<fecha>/cluster.json`**, con los nombres del clúster y de las node
   groups. Es la salida cruda de `terraform output -json`, redirigida justo
   después del `apply` (ver `infra/README.md`):

   ```bash
   mkdir -p results/$(date +%F)
   terraform -chdir=infra output -json > results/$(date +%F)/cluster.json
   ```

   `date +%F` (local, sin `-u`) a propósito: el runner escribe en la fecha local,
   así que un `date -u +%F` aquí crearía el directorio de mañana después de las
   19:00 en Lima y el runner buscaría el `cluster.json` en el de hoy.

   Si falta, o si no trae `cluster_name` y `nodegroup_names`, el runner corta con
   ese mismo comando en el mensaje. En `--dry-run` cae en el fixture
   `runner/tests/fixtures/cluster.json` y lo dice en la primera línea del plan,
   así que el plan se puede leer sin clúster.

2. **`results/<fecha>/ecr.json`**, con el registro de las imágenes propias. Mismo
   trato que el anterior, pero del root `infra/ecr` (ver `infra/ecr/README.md`):

   ```bash
   terraform -chdir=infra/ecr output -json > results/$(date +%F)/ecr.json
   ```

   Los dos archivos están **git-ignored**: llevan el id de la cuenta sandbox. El
   tag de las imágenes, en cambio, sale de `results/images.json`, que **sí** se
   commitea (un tag y un digest **por imagen**, no uno solo para las cuatro; sin
   datos de cuenta) y lo escribe el push gated (`PUSH=1 apps/build-multiarch.sh`),
   que mergea en vez de sobreescribir: una corrida parcial (una sola imagen) no
   mueve el tag de las otras tres. `--image-tag <tag>` pisa el tag de las cuatro
   a la vez, para apuntar una celda a otro tag puntual que ya esté en ECR (por
   ejemplo, el de un re-push del mismo día — `infra/ecr/README.md`). En
   `--dry-run` los dos caen en sus fixtures y el plan lo dice.

3. **`results/cost.md` con las tarifas del día.** Antes de subir cualquier node
   group el runner lee ese archivo y el ledger del día: si alguna tarifa sigue en
   `TODO` se niega a escalar nada, y si el día ya superó `estimate_per_day_usd`
   también, salvo que se pase `--override-budget` a propósito. `--dry-run` pasa
   siempre, que es la forma de leer el plan antes de que existan las tarifas.

Celdas válidas por workload (las mismas que los overlays de `manifests/`):

| Workload | Celdas | Carga |
|---|---|---|
| `java` | `x86-stock`, `x86-tuned`, `x86-smtoff`, `arm-stock`, `arm-tuned`, `x86-tuned-vthreads`, `arm-tuned-vthreads` | k6, escalera 200→6000 rps, SLO p99 100 ms |
| `go` | `x86-stock`, `arm-stock` | k6, escalera 1000→20000 rps, SLO p99 20 ms |
| `inference` | `x86-stock`, `x86-tuned`, `x86-t15`, `arm-stock`, `arm-tuned` | k6 `MODE=saturate`, 4 VUs, 6 min, sin escalera ni SLO de latencia (`SLO_MS=0`); el calentamiento tiene la misma forma que la medición |
| `mongo` | `x86-stock`, `x86-tuned`, `arm-stock`, `arm-tuned` | go-ycsb, escalera de hilos 16/32/64/128, SLO p99 READ 5 ms |
| `net` | `x86-stock`, `x86-tuned`, `arm-stock`, `arm-tuned` | iperf3 `-P 8 -t 60`, ida y vuelta, n=3 |

`x86-t15`, `x86-tuned-vthreads` y `arm-tuned-vthreads` no son node groups: son
celdas de un workload que corren sobre la node group tuned que les corresponde
(`config.CELL_MNG`).

Todos los defaults viven en `config.WORKLOADS` y se pueden pisar desde la CLI:
`--slo-ms`, `--rate-start`, `--rate-step`, `--rate-max`, `--stage-seconds`,
`--ramp-seconds`, `--fixed-seconds`, `--warmup-seconds`, `--threads`, `--runs`,
`--date`, `--override-budget`, `--image-tag` (el tag de las imágenes propias en
ECR, si no el de `results/images.json`), `--warm-pages` y `--warm-max-min` (los
dos topes del calentamiento de Mongo), `--reload` (bota la colección de YCSB y la
vuelve a cargar antes de la celda) y `--env K=V` (repetible) para cualquier otra variable
de los scripts de k6. `--env` llega a las tres cargas de k6 de la celda —
calentamiento, escalera del knee y corridas fijas — no solo a las dos últimas.
`--date` es la fecha **local**, no UTC: un día de lab que sigue después de las
19:00 en Lima o Buenos Aires no se parte en dos directorios (ni en dos gates de
presupuesto).

Al terminar el día de lab, antes de que la persona corra `terraform destroy`:

```bash
uv run cell --teardown-day     # NodePools, Jobs, perilla de red, sts de Mongo y
                               # todos los PVC; después los dos describe-volumes
```

Eso borra también el PVC de 20 GiB de Pyroscope, que es la intención: es el
almacén de perfiles de un día de lab, no una base de datos. El orden completo del
cierre está en un solo lugar, el README raíz, sección "Reproducir" → "Cierre del
día de lab"; este comando es su paso del medio y lo imprime al terminar.

El dataset de Mongo sobrevive **entre celdas del mismo día** a propósito: el
`ycsb-load` de 20M registros corre una sola vez (cuando la colección está vacía)
y cada celda solo recalienta la cache. Por eso una celda de Mongo **no borra su
overlay** al terminar: el StatefulSet tiene
`persistentVolumeClaimRetentionPolicy.whenDeleted: Delete`, así que borrarlo se
llevaría el PVC y el dataset con él. El pod queda `Pending` cuando la node group
baja a cero y vuelve a programarse sobre el nodo de la celda siguiente;
`--teardown-day` es el único lugar que borra el StatefulSet y los PVC.

## Qué escribe

```
results/
  cost.md                                  # tarifas, a mano el día del lab
  images.json                              # tag y digests del push, commiteado
  <fecha>/
    cluster.json                           # terraform output -json de infra/, a mano
    ecr.json                               # terraform output -json de infra/ecr, a mano
    ledger.md                              # costo del día, por celda
    <workload>/<celda>/
      cell.json                            # instancia, nodos, minutos, invalidaciones
      knee.json                            # knee, SLO, serie (rate|hilos → p99)
      knee-raw.json | knee-t<N>.txt        # la salida cruda de la búsqueda del knee
      run-<i>/
        k6.json | llama.json | ycsb.txt | iperf.json + iperf-reverse.json
        top.json                           # kubectl top cada 10 s; `nodes` trae
                                           # TODOS los nodos de la celda (red usa 2)
        meta.json                          # cpuset, aperf, flamegraph, invalidaciones
        aperf/aperf_record_<ts>.tar.gz
        aperf/aperf.log                  # stdout+stderr del plugin, el diagnóstico
        flamegraph.json                    # render de Pyroscope (no hay PNG en la API)
```

Los archivos crudos no se editan nunca. `analysis/` solo lee:

```bash
uv run python -c "from analysis import stats; print(stats.summarize('../results/<fecha>/java/arm-tuned'))"
uv run python -m analysis.charts ../results/<fecha>            # PNG a slides/assets/
uv run python -m analysis.charts ../results/<fecha> --out /tmp/figs
```

`stats.summarize` devuelve mediana y min/max por celda más `usd_per_kop`,
`usd_per_mtok` y `cpu_per_gbps` cuando hay tarifa. `cpu_per_gbps` es una razón
entre dos cosas medidas en ventanas distintas y conviene leerla así: **CPU
mediana del nodo SUT sobre TODA la ventana de la celda de red** (las muestras de
`kubectl top` cubren la corrida de ida y la de vuelta) dividida por los **Gbps de
la corrida de ida** (`iperf.json`). Es un indicador comparable entre celdas
—las dos puntas son del mismo tipo de instancia— y no un costo de CPU por Gbps
instantáneo. Sin tarifa capturada
(`results/cost.md` todavía en `TODO`) esos campos simplemente no aparecen: un
precio inventado en un slide de costo es un número equivocado, no aproximado.

## Lo que el runner registra para el gate

Cada uno de estos queda escrito en `meta.json` / `knee.json` / `cell.json`, así
que el gate (plan Task 6.5) se contesta leyendo los resultados y no la memoria:

- **cpuset exclusivo**: `cat /sys/fs/cgroup/cpuset.cpus.effective` dentro del pod
  medido. Se esperan 15 vCPU (7 en `x86-smtoff`); si el cpuset es el nodo entero,
  la política `static` del CPU manager no quedó puesta y la celda se marca
  inválida y aborta. Es un control, no una perilla. **Una lectura vacía tampoco
  pasa**: se marca `cpuset_unreadable` y la celda aborta igual. La celda de Go es
  la excepción de forma, no de fondo: su imagen es distroless y no tiene shell
  donde correr un `cat`, así que el servidor informa su propia máscara de
  afinidad (`runtime.NumCPU()`) por `/healthz` y el runner la lee por el proxy de
  Services del API server.
- **guard del loader**: `kubectl top node` cada 10 s alrededor de **las dos**
  escaleras (k6 y go-ycsb); si el nodo `loader` pasa de 70 % de CPU durante el
  knee, el knee es el del generador y no el del silicio: queda escrito en
  `knee.json` y la celda aborta. En la celda de red el guard no aplica (el
  generador es el segundo nodo de la celda, no el loader) y se saltea explícito.
- **knee inservible**: la escalera se juzga **escalón por escalón**, no entera. Un
  escalón vale si entregó la carga que ofreció
  (`http_reqs{rate:R}.count >= 0.95 x R x (STAGE_SECONDS - RAMP_SECONDS)`) y si
  contestó (`http_req_failed{rate:R}.rate < 0.01`); el knee es el último escalón
  válido con p99 <= SLO, y lo que pasa **después** del cruce se ignora, porque
  arriba del knee la escalera tiene que romperse: esa es la definición de knee.
  La regla entera de corrida (`invalid_reasons`) queda solo para las corridas
  fijas — aplicada a la escalera rechazaba justamente las que encontraban el
  knee. La celda **aborta antes de las corridas fijas** si el primer escalón ya
  es inválido, si el guard del loader disparó, o si el knee cayó en el tope de la
  escalera (`ladder_never_crossed`: nada cruzó el SLO, así que el techo lo puso
  el script y no el silicio; hay que subir `--rate-max`, o `--threads` en Mongo).
  Medir al 80 % de un knee inválido es medir el 80 % de nada.
- **corridas inválidas**: `http_req_failed.rate > 0.01`,
  `dropped_iterations.count > 0` o un Job que no imprimió resumen
  (`no_summary`) marcan la corrida en `meta.json`. La corrida queda guardada,
  `analysis.stats` la deja fuera de las medianas y la lista en `excluded`, y si
  quedan menos de tres corridas válidas la celda sale con `insufficient_runs` y
  los gráficos la saltean (el ledger igual la cobra).
- **APerf**: `ok` o el motivo, y la salida completa del plugin en
  `run-<i>/aperf/aperf.log`. Ese archivo es el único diagnóstico cuando dice
  `failed: exit 1` (sin PMU en el guest, sin `/boot`, un pod que no programa).
  Antes esa salida iba a un pipe que nadie leía, que además es la forma de que un
  hijo hablador se cuelgue al llenar el buffer de 64 KiB. Si el plugin no graba
  en Bottlerocket la corrida igual vale — el argumento se sostiene con el knee y
  los flame graphs.
- **Pyroscope**: `ok` o el motivo, más el `flamegraph.json` de la corrida.
- **Mongo**: cantidad de documentos al empezar y el delta de
  `pages read into cache` de cada pasada de calentamiento. La colección está
  vacía (y se carga) o está completa (y se reusa): cualquier número intermedio es
  `partial_dataset` y la celda se niega a medir, porque una carga cortada a la
  mitad contesta todas las lecturas y es otro benchmark, con el control de
  calentamiento perfectamente plano mientras pasa. El calentamiento repite hasta
  que dos muestras seguidas se diferencien en menos de 1000 páginas
  (`--warm-pages`), con un tope de 20 minutos de reloj (`--warm-max-min`); si se
  llega al tope la celda se marca `cache_not_warm` y aborta, porque esa corrida
  mediría EBS y no memoria.
- **minutos por celda**: lo único que se factura por celda, y lo que consume el
  ledger.

## Detalles que no son obvios

- **k6 sale con 99 cuando falla un threshold**, y eso es una corrida completa, no
  un error (`runner/k6/lib.js`). Con `backoffLimit: 0` el Job queda en `Failed`,
  así que el runner espera `Complete` **o** `Failed` y después lee los logs;
  esperar solo `Complete` colgaría justo en las corridas que traen el knee.
- **El resumen viaja por los logs**: el contenedor imprime
  `---AAD-SUMMARY---` y después el JSON, y el runner corta por ese marcador. Es
  más simple que montar un volumen compartido para sacar un archivo de un Job.
- **Los scripts de k6 van en un ConfigMap** (`k6-scripts`) generado con
  `kubectl create configmap --from-file=runner/k6 --dry-run=client -o yaml |
  kubectl apply -f -`, así que editar un `.js` y volver a correr alcanza.
- **Un nombre de Job por invocación**: el pod template de un Job es inmutable, y
  reaplicar un nombre existente falla con "field is immutable". El runner borra
  el Job anterior con ese nombre y **espera a que desaparezca**
  (`kubectl wait --for=delete job/<n> --timeout=60s`) antes de aplicar: `delete`
  vuelve antes de que el objeto se haya ido y la carrera contra su finalizer
  aparece justo en la segunda repetición del día.
- **`kubectl top` son dos tablas distintas**: la de nodos trae `CPU(%)` y la de
  pods no. Con un solo parser que exigiera el porcentaje, `pod_cpu_millicores`
  daba 0 en todas las corridas. Ver la tabla de fuentes de arriba.
- **La bajada a cero se reintenta y se espera**: `desiredSize=0` con hasta tres
  intentos (10 s de espera entre uno y otro) y después un `kubectl get nodes -l
  aad/cell=<celda>` hasta que no quede ninguno (tope 10 min). Los minutos que va
  al ledger son ese intervalo completo, de la subida a la desaparición del nodo,
  porque es exactamente lo que factura EC2. Si se pasa el tope, avisa y sigue: lo
  que no puede es dejar de escribir el ledger.
- **`recordcount` no se parametriza**: está escrito en las dos plantillas de Job
  de YCSB (load y run) y tiene que coincidir, así que el runner **verifica** que
  el YAML renderizado lo traiga en vez de sustituirlo. `render()` además falla si
  queda algún `__PLACEHOLDER__` sin reemplazar.
- **El centinela `:UNSET` se atrapa antes de encender nada**: antes del `scale()`
  el runner renderiza el overlay y las plantillas de Job del workload y se niega a
  seguir si todavía aparece. Llega al clúster como `ImagePullBackOff`, que son
  quince minutos de un 4xlarge pago hasta que alguien lo lee; renderizarlo aquí
  cuesta un segundo. **En `--dry-run` el overlay NO se renderiza de verdad**:
  `config.sh()` corta corto y devuelve `""` mientras `config.DRY_RUN` está
  puesto, así que `kubectl kustomize` nunca corre y un render "limpio" ahí no
  sería evidencia de nada — `check_images()` lo dice en vez de aparentar que
  chequeó (`# (dry-run) overlay render skipped`). Las plantillas de Job sí se
  chequean en un dry run, porque `render()`/`rewrite_images()` son sustitución
  de texto en Python puro, sin subproceso de por medio.
- **Las imágenes propias no tienen registro en git**: los manifiestos las nombran
  `aad-java:UNSET`, `aad-go:UNSET`, `aad-iperf3:UNSET` y `aad-ycsb:UNSET`, porque
  el registro real es `<cuenta>.dkr.ecr.us-east-1.amazonaws.com` y el id de cuenta
  no se commitea. El runner lo pone de dos maneras, según qué esté renderizando:
  - **Overlays**: escribe un kustomization descartable en un directorio temporal
    (`apiVersion: kustomize.config.k8s.io/v1beta1` / `kind: Kustomization`, los
    mismos valores que trae cualquier `kustomization.yaml` del repo) con
    `resources: [<overlay>]` y un `images:` con las cuatro entradas
    (`name` / `newName` / `newTag`, armadas a partir de `image_ref()` y no
    leyendo `IMAGES` directo) y corre `kubectl kustomize` sobre él. Los campos
    son los de la documentación de kustomize — `newName` "Override the image
    name for images whose image name matches `name`", `newTag` "Override the
    image tag or digest"
    (https://kubectl.docs.kubernetes.io/references/kustomize/kustomization/images/).
    La entrada `resources` es una ruta **relativa** calculada con
    `os.path.relpath`: kustomize rechaza una absoluta con "new root ... cannot be
    absolute" (kustomize v5.6.0 dentro de kubectl 1.33.9), y eso reventaría
    después de que la node group ya está arriba.
  - **Plantillas de Job**: no son parte de ningún kustomization, así que `render()`
    sustituye el centinela en el mismo paso en el que llena los
    `__PLACEHOLDER__`. Es el diff más chico de los dos caminos que había: pasar
    cada Job renderizado por otro `kubectl kustomize` habría sido un subproceso
    más por Job y un `yaml.safe_load` de una cadena vacía en `--dry-run`.
- **Cada Job lleva la etiqueta `aad/cell` de su celda** y la celda los borra al
  terminar (`kubectl -n aad delete jobs -l aad/cell=<celda>`). Los logs ya están
  en disco; lo que dejaban era sus pods en `kubectl get pods` y el nombre tomado.
- **La perilla de red la aplica el runner**, y solo en el workload `net`
  (`kubectl apply -f manifests/base/net-tuned-daemonset.yaml` antes,
  `kubectl delete -f` después). En `manifests/base` retunearía también las celdas
  tuned de Java, Mongo e inferencia.
- **Si `uv run cell` dice `ModuleNotFoundError: No module named 'cell'`**, el
  `.pth` del install editable quedó con el flag `UF_HIDDEN`, y desde CPython 3.13
  `site.addpackage` saltea los `.pth` ocultos, así que el script de consola no
  puede importar `cell.py`. Se diagnostica y se arregla así:

  ```bash
  P=.venv/lib/python3.13/site-packages/_editable_impl_aad_runner.pth
  python3 -c "import os,sys; print(hex(os.lstat(sys.argv[1]).st_flags))" $P   # 0x8040 = oculto
  chflags nohidden $P                                                        # 0x40 = listo
  ```

  `uv sync` lo arregla solo cuando además reinstala el paquete; con el entorno ya
  auditado no reescribe el archivo y el flag sigue puesto, así que `chflags` es lo
  que hay que correr. Vuelve a aparecer **cada vez que se edita el código del
  runner**: `uv run` sincroniza, la sincronización reinstala el editable, y la
  reinstalación vuelve a marcar el `.pth` como oculto (además de repetirle la
  línea). Las dos salidas que funcionan son `rm -rf .venv && uv sync` una vez
  después de editar, o `chflags nohidden $P && uv run --no-sync cell ...`. Variante peor del mismo problema: si el directorio del
  proyecto se sincroniza y aparecen copias `... 2.dist-info` / `... 2.pth`,
  `uv sync` falla con `Failed to read metadata from: .../aad_runner-0.1.0 2.dist-info`;
  ahí lo que corresponde es `rm -rf .venv && uv sync`. Los tests no dependen de
  nada de esto: `[tool.pytest.ini_options] pythonpath` ya pone `runner/` en el path.

## Tests

```bash
cd runner && uv sync && uv run pytest -q
```

Sin red, sin AWS y sin clúster: los tests tocan `knee`, `analysis.stats`,
`cost`, `analysis.charts`, los parsers de `capture` y los guards de `cell`
(incluido el plan de `--dry-run`, que es una cadena de texto) sobre fixtures. `tests/fixtures/` trae las salidas
reales del smoke local de k6 (`java-knee.json` con el SLO forzado a 2 ms para que
ningún escalón pase, `java-fixed.json`, `go-fixed.json`) y de iperf3 3.20
(`iperf3-forward.json`); `llama-fixed.json`, `ycsb-t64.txt`, `top-node.txt`,
`top-pod.txt` y `top-net.json` son sintéticos, escritos con la forma exacta que
producen k6 con `inference.js`, go-ycsb y las dos tablas de `kubectl top`
(`test_capture.py` verifica que `top-net.json` siga teniendo la forma que el
parser produce). `cluster.json` y `ecr.json` son salidas de
`terraform output -json` con su envoltorio `{"value": ...}`, que es lo que
`--dry-run` lee cuando no hay clúster; `images.json` es el archivo que escribe
(mergeando) el push, con un tag y un digest por imagen bajo la clave `images`.
El id de cuenta que aparece en `ecr.json` es `123456789012`, el valor de
documentación de AWS, no una cuenta.
