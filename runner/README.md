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
| `aws` | aws-cli 2.36.32 | `eks update-nodegroup-config` y `ec2 describe-volumes` |
| `terraform` | 1.15.2 | **solo lectura**: `terraform output -json` |

`terraform apply` y `terraform destroy` los corre una persona (ver
`infra/README.md`). El runner nunca aplica infraestructura; lo único que mueve es
`desiredSize` de una managed node group.

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

`service_name` sale de la regla de reetiquetado del chart de Pyroscope
(`labelmap process.executable.name → service_name`, en
`manifests/base/pyroscope-values.yaml`), así que es el nombre del ejecutable:
`java`, `aad-go`, `mongod`, `llama-server`, `iperf3`.

## Correr una celda

```bash
cd runner
uv sync
export AWS_PROFILE=<perfil-sandbox>       # tiene que contener "sandbox"

# El plan completo, sin tocar nada:
uv run cell --workload java --cell arm-tuned --dry-run

# La corrida de verdad (GATED: el clúster ya tiene que estar aplicado):
uv run cell --workload java --cell arm-tuned --runs 3
```

Celdas válidas por workload (las mismas que los overlays de `manifests/`):

| Workload | Celdas | Carga |
|---|---|---|
| `java` | `x86-stock`, `x86-tuned`, `x86-smtoff`, `arm-stock`, `arm-tuned`, `x86-tuned-vthreads`, `arm-tuned-vthreads` | k6, escalera 200→6000 rps, SLO p99 100 ms |
| `go` | `x86-stock`, `arm-stock` | k6, escalera 1000→20000 rps, SLO p99 20 ms |
| `inference` | `x86-stock`, `x86-tuned`, `x86-t15`, `arm-stock`, `arm-tuned` | k6 `MODE=saturate`, 4 VUs, 6 min, sin escalera |
| `mongo` | `x86-stock`, `x86-tuned`, `arm-stock`, `arm-tuned` | go-ycsb, escalera de hilos 16/32/64/128, SLO p99 READ 5 ms |
| `net` | `x86-stock`, `x86-tuned`, `arm-stock`, `arm-tuned` | iperf3 `-P 8 -t 60`, ida y vuelta, n=3 |

`x86-t15`, `x86-tuned-vthreads` y `arm-tuned-vthreads` no son node groups: son
celdas de un workload que corren sobre la node group tuned que les corresponde
(`config.CELL_MNG`).

Todos los defaults viven en `config.WORKLOADS` y se pueden pisar desde la CLI:
`--slo-ms`, `--rate-start`, `--rate-step`, `--rate-max`, `--stage-seconds`,
`--fixed-seconds`, `--warmup-seconds`, `--threads`, `--runs`, y `--env K=V`
(repetible) para cualquier otra variable de los scripts de k6.

Al terminar el día de lab, antes de que la persona corra `terraform destroy`:

```bash
uv run cell --teardown-day     # borra el StatefulSet de Mongo y sus PVC
```

El dataset de Mongo sobrevive **entre celdas del mismo día** a propósito: el
`ycsb-load` de 20M registros corre una sola vez (cuando la colección está vacía)
y cada celda solo recalienta la cache.

## Qué escribe

```
results/
  cost.md                                  # tarifas, a mano el día del lab
  <fecha>/
    cluster.json                           # terraform output, cacheado una vez
    ledger.md                              # costo del día, por celda
    <workload>/<celda>/
      cell.json                            # instancia, nodos, minutos, invalidaciones
      knee.json                            # knee, SLO, serie (rate|hilos → p99)
      knee-raw.json | knee-t<N>.txt        # la salida cruda de la búsqueda del knee
      run-<i>/
        k6.json | llama.json | ycsb.txt | iperf.json + iperf-reverse.json
        top.json                           # muestra de kubectl top cada 10 s
        meta.json                          # cpuset, aperf, flamegraph, invalidaciones
        aperf/aperf_record_<ts>.tar.gz
        flamegraph.json                    # render de Pyroscope (no hay PNG en la API)
```

Los archivos crudos no se editan nunca. `analysis/` solo lee:

```bash
uv run python -c "from analysis import stats; print(stats.summarize('../results/<fecha>/java/arm-tuned'))"
uv run python -m analysis.charts ../results/<fecha>            # PNG a slides/assets/
uv run python -m analysis.charts ../results/<fecha> --out /tmp/figs
```

`stats.summarize` devuelve mediana y min/max por celda más `usd_per_kop`,
`usd_per_mtok` y `cpu_per_gbps` cuando hay tarifa. Sin tarifa capturada
(`results/cost.md` todavía en `TODO`) esos campos simplemente no aparecen: un
precio inventado en un slide de costo es un número equivocado, no aproximado.

## Lo que el runner registra para el gate

Cada uno de estos queda escrito en `meta.json` / `knee.json` / `cell.json`, así
que el gate (plan Task 6.5) se contesta leyendo los resultados y no la memoria:

- **cpuset exclusivo**: `cat /sys/fs/cgroup/cpuset.cpus.effective` dentro del pod
  medido. Se esperan 15 vCPU (7 en `x86-smtoff`); si el cpuset es el nodo entero,
  la política `static` del CPU manager no quedó puesta y la celda se marca
  inválida y aborta. Es un control, no una perilla.
- **guard del loader**: `kubectl top node` cada 10 s; si el nodo `loader` pasa de
  70 % de CPU durante el knee, el knee es el del generador y no el del silicio:
  se marca inválido y la celda aborta.
- **corridas inválidas**: `http_req_failed.rate > 0.01` o
  `dropped_iterations.count > 0` marcan la corrida, que queda guardada pero fuera
  de las medianas.
- **APerf**: `ok` o el motivo. Si el plugin no graba en Bottlerocket la corrida
  igual vale — el argumento se sostiene con el knee y los flame graphs.
- **Pyroscope**: `ok` o el motivo, más el `flamegraph.json` de la corrida.
- **Mongo**: cantidad de documentos al empezar y el delta de
  `pages read into cache` de cada pasada de calentamiento (tiene que quedar
  plano; si no, la corrida mide EBS y no memoria).
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
  el Job anterior con ese nombre antes de aplicar, para que una repetición del
  mismo día no se choque consigo misma.
- **`recordcount` no se parametriza**: está escrito en las dos plantillas de Job
  de YCSB (load y run) y tiene que coincidir, así que el runner **verifica** que
  el YAML renderizado lo traiga en vez de sustituirlo. `render()` además falla si
  queda algún `__PLACEHOLDER__` sin reemplazar.
- **La perilla de red la aplica el runner**, y solo en el workload `net`
  (`kubectl apply -f manifests/base/net-tuned-daemonset.yaml` antes,
  `kubectl delete -f` después). En `manifests/base` retunearía también las celdas
  tuned de Java, Mongo e inferencia.
- **Si `uv run cell` dice `ModuleNotFoundError: No module named 'cell'`**, correr
  `uv sync` de nuevo. Es un choque conocido entre uv y CPython 3.13 en macOS: el
  `.pth` del install editable a veces queda con el flag `UF_HIDDEN`, y desde
  3.13 `site.addpackage` saltea los `.pth` ocultos, así que el script de consola
  se queda sin poder importar `cell.py`. Se diagnostica con
  `python3 -c "import os; print(hex(os.lstat('.venv/lib/python3.13/site-packages/_editable_impl_aad_runner.pth').st_flags))"`
  (0x8000 = oculto) y se arregla con `uv sync` o `chflags nohidden` sobre ese
  archivo. Los tests no dependen de esto: `[tool.pytest.ini_options] pythonpath`
  ya pone `runner/` en el path.

## Tests

```bash
cd runner && uv sync && uv run pytest -q
```

Sin red, sin AWS y sin clúster: los tests solo tocan `knee`, `analysis.stats`,
`cost` y `analysis.charts` sobre fixtures. `tests/fixtures/` trae las salidas
reales del smoke local de k6 (`java-knee.json` con el SLO forzado a 2 ms para que
ningún escalón pase, `java-fixed.json`, `go-fixed.json`) y de iperf3 3.20
(`iperf3-forward.json`); `llama-fixed.json`, `top-net.json` y `ycsb-t64.txt` son
sintéticos, escritos a mano con la forma exacta que producen k6 con
`inference.js`, `kubectl top` y go-ycsb.
