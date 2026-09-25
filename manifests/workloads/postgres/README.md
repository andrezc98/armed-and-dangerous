# PostgreSQL 18.6 + pgbench (enmienda 2026-09-25)

La segunda base de datos del lab, al lado de Mongo. Mongo se frena antes de la
CPU (los tickets de control de admisión hacen cola pasado el knee y el SUT queda
en ~8,7 de 15 núcleos), así que la historia de bases de datos no puede
depender solo de él. Decisión del speaker (R2, 2026-09-25): **PostgreSQL +
pgbench**. Mongo queda como está.

Todo lo que sigue se verificó el 2026-09-25 contra la documentación del día;
cada perilla lleva su cita también en el YAML.

## Forma

| Pieza | Qué es |
|---|---|
| `base/statefulset.yaml` | `postgres:18.6` en el SUT: mismo taint, `nodeSelector` por overlay, QoS Guaranteed con 15 CPU exclusivas y 56Gi, PVC gp3 de 200Gi y la misma política de retención que Mongo (el dataset sobrevive entre celdas del día) |
| `base/service.yaml` | `postgres.aad.svc:5432`, headless |
| `base/pgbench-init-job.yaml` | `pgbench -i -s 1000 -I dtGvp` desde el loader, una vez por día (con la etiqueta `aad/cell` de la celda que lo corrió) |
| `base/pgbench-run-job.yaml` | un proceso de pgbench (`-S`, select-only) de un escalón, una pasada de calentamiento o una corrida fija; el runner aplica dos juntos |
| `overlays/<celda>` | `x86-stock`, `x86-tuned`, `amd-stock`, `amd-tuned`, `arm-stock`, `arm-tuned` |

pgbench viene en la misma imagen del servidor, así que los Jobs de cliente
usan `postgres:18.6` (amd64 en el loader). Imagen pública como `mongo:8.0.32`:
nada de ECR, nada de infra.

## Versiones y flags verificados

| Qué | Valor | Fuente (leída el 2026-09-25) |
|---|---|---|
| Major estable más nuevo | 18 (18.6 es el minor actual; 19 sigue en beta: `19beta4` en Docker Hub) | https://www.postgresql.org/support/versioning/ |
| Imagen | `postgres:18.6`, manifest list con `linux/amd64` y `linux/arm64/v8`, digest `sha256:5a5a84b1…` | API de Docker Hub (`/v2/repositories/library/postgres/tags/18.6`) y `docker pull` local: `pgbench (PostgreSQL) 18.6 (Debian 18.6-1.pgdg13+2)` |
| Directorio de datos en 18 | `PGDATA=/var/lib/postgresql/18/docker`, volumen en `/var/lib/postgresql` | https://hub.docker.com/_/postgres (sección `PGDATA`) y el Dockerfile de `18/trixie` |
| Args del contenedor | un primer argumento que empieza con `-` hace que el entrypoint anteponga `postgres`; `-c clave=valor` para cualquier opción del `.conf` | `docker-entrypoint.sh` de `18/trixie` y la sección "Database Configuration" de la imagen |
| `$(VAR)` en args | Kubernetes expande variables de entorno del contenedor en `args` | https://kubernetes.io/docs/tasks/inject-data-application/define-command-argument-container/ |
| `-i`, `-s`, `-I dtGvp` | `G` = generación del lado del servidor (casi sin tráfico de red); `d` primero, `p` (claves primarias) al final | https://www.postgresql.org/docs/18/pgbench.html |
| Tamaño del dataset | 100.000 filas de `pgbench_accounts` por unidad de escala; 86 MB a escala 5 medido en 18.6, o sea ~17 GB a escala 1000 | misma página + `pg_database_size` en local |
| `-S` | "Shorthand for `-b select-only`" | misma página |
| `-c` / `-j` | los clientes se reparten "as evenly as possible" entre los hilos; pgbench baja `-j` a `-c` si es mayor (`if (nthreads > nclients) nthreads = nclients`) | misma página + `src/bin/pgbench/pgbench.c` en `REL_18_6` |
| `-R` | total del proceso: se divide entre sus hilos (`throttle_delay *= nthreads`); `-R 0` es un error fatal ("invalid rate limit") | `pgbench.c` en `REL_18_6` |
| Latencia bajo `-R` | "calculated from the scheduled start times", o sea incluye el schedule lag; el campo `time` del log es `now - txn_scheduled`, lo mismo | docs + `pgbench.c` (`processXactStats`) |
| `skipped` | solo existe con `-R` **y** `--latency-limit`; el runner no usa `--latency-limit` (escondería la sobrecarga), así que no hay skipped | docs de `-L` + `printResults` |
| Log por transacción | `-l`, `--sampling-rate`, archivos `pgbench_log.<pid>[.<hilo>]` en el directorio de trabajo; campos `client_id transaction_no time script_no time_epoch time_us [schedule_lag]`; `time` en µs, `failed` si la transacción falló; `schedule_lag` (campo 7) "present only if --rate is specified" | docs de `-l` y "Per-Transaction Logging" |
| Corrida abortada | con un cliente abortado pgbench imprime "Run was aborted; the above results are incomplete.", **igual imprime una línea `tps`** y sale con 2 | ensayado en local: backends terminados a los 5 s con `pg_terminate_backend` (`runner/tests/fixtures/pgbench-aborted.txt`) |
| CPU por pod | `PodMetrics`: `timestamp` y `window` definen el intervalo `[Timestamp-Window, Timestamp]`; `containers[].usage.cpu` | https://kubernetes.io/docs/reference/external-api/metrics.v1beta1/ |
| Resumen | `number of transactions actually processed`, `number of failed transactions`, `tps = … (without initial connection time)`; **sin percentiles** | docs + `printResults` |
| `shared_buffers` | default 128MB; "a reasonable starting value … is 25% of the memory in your system" | https://www.postgresql.org/docs/18/runtime-config-resource.html |
| `effective_cache_size` | default 4GB; solo para el planificador | https://www.postgresql.org/docs/18/runtime-config-query.html |
| `max_connections` | default 100 | https://www.postgresql.org/docs/18/runtime-config-connection.html |
| `huge_pages` / `huge_pages_status` | default `try`, que vuelve al default en silencio si falla; `huge_pages_status` dice `on`/`off` | runtime-config-resource y https://www.postgresql.org/docs/18/runtime-config-preset.html |
| `pg_prewarm` | `pg_prewarm(regclass, mode)`, modo `read` lee los bloques (queda en la cache del kernel); la extensión viene en la imagen | https://www.postgresql.org/docs/18/pgprewarm.html + `docker run` local |
| `blks_read` | cuenta también lecturas que resolvió la cache del kernel (`blks_hit` "only includes hits in the PostgreSQL buffer cache, not the operating system's file system cache") | https://www.postgresql.org/docs/18/monitoring-stats.html |
| `io.stat` de cgroup v2 | `rbytes` = "Bytes read" por dispositivo | https://docs.kernel.org/admin-guide/cgroup-v2.html |

Los comandos exactos de los Jobs (init, dos procesos concurrentes, con y sin
`-R`, el histograma con `awk | sort -n | uniq -c`) se ensayaron el 2026-09-25 en
local con `docker run postgres:18.6`, escala 5. Esas salidas son los fixtures de
`runner/tests/fixtures/pgbench-*.txt`: formato real, números de laptop.

## Stock y tuned

- **Stock** = defaults del servidor, escritos en el YAML para que la celda
  registre lo que corrió: `shared_buffers=128MB`, `effective_cache_size=4GB`,
  `huge_pages=try`. **Una excepción, que no es tuning**: `max_connections=600`
  en vez de 100, porque el escalón más alto abre 512 sesiones y con 100 la
  escalera no corre. El runner deja 10 conexiones libres (su propio `psql` y las
  reservadas) y se niega a arrancar una celda cuya escalera no quepa en
  `max_connections - 10` (`check_pgbench_clients`).
- **Tuned** = las perillas de nodo de la node group tuned (THP; C-states donde
  la node group las tiene), igual que Mongo, **más** dos valores con respaldo
  en la documentación, iguales en las tres familias:
  - `shared_buffers=16GB`: 25 % de los 64 GiB del nodo.
  - `effective_cache_size=48GB`: `shared_buffers` más lo que el límite de 56Gi
    del pod deja para la cache del kernel. Es solo una estimación del
    planificador; con select-only (búsqueda por clave primaria) no debería
    mover nada, y así se va a contar.
- **Huge pages quedan en `try` en todas las celdas.** Usarlas de verdad pide
  páginas reservadas en el nodo (`vm.nr_hugepages`) y un request de
  `hugepages-2Mi` en el pod: un cambio de infra que no se hizo. Como `try`
  falla en silencio, el runner guarda `huge_pages_status` en `cell.json`: si
  algún día dice `on`, algo cambió en el nodo.

Las perillas viven en un solo lugar: variables `PG_SHARED_BUFFERS`,
`PG_EFFECTIVE_CACHE_SIZE` y `PG_MAX_CONNECTIONS` del StatefulSet, expandidas en
los `args`. El overlay tuned pisa dos; en calibración, `--app-env
PG_SHARED_BUFFERS=24GB` pisa cualquiera sin editar nada.

## Cómo corre una celda

0. **La otra base, a cero.** Una celda de PostgreSQL escala el StatefulSet de
   Mongo a 0 réplicas antes de aplicar su overlay, y una de Mongo hace lo mismo
   con el de PostgreSQL: los dos toleran el taint del SUT y conservan el
   `nodeSelector` de su última celda, así que si coincide con la actual el otro
   pod arrancaría en el mismo nodo. El PVC y el dataset quedan; la próxima celda
   de esa base la vuelve a 1 al aplicar su overlay.
1. **Dataset, una vez por día.** Si falta `pgbench_accounts_pkey` (el último
   paso del init) el runner corre el init. Si existe pero `pgbench_branches`
   no tiene `scale` filas, se niega (`scale_mismatch`) y pide `--reload`.
   Después del init vuelve a mirar el índice; si no está, `init_incomplete`.
2. **Precalentamiento.** `pg_prewarm(..., 'read')` de la tabla y su índice:
   lectura secuencial de ~17 GB a la velocidad del gp3, en vez de lecturas
   aleatorias de 8 KiB. Tiene que devolver una cantidad de bloques (entero), que
   queda en `cell.json`; si no, `prewarm_failed`.
3. **Calentamiento** con pasadas de pgbench (64 clientes, 60 s) hasta que el
   contenedor deja de leer de disco: la resta de `rbytes` de su `io.stat` por
   pasada, en páginas de 8 KiB, bajo `warm_pages` (8192 = 64 MiB). El `io.stat`
   crudo de la primera y la última lectura queda en `cell.json`, y la primera
   (después del prewarm, que leyó el dataset desde EBS) tiene que tener
   `rbytes` distinto de cero: si no, `io.stat` no está contando las lecturas de
   este contenedor y se falla con `cache_unreadable`. La excepción es la celda
   que acaba de correr el init: el dataset se escribió a través de la cache del
   kernel y el prewarm no leyó nada de disco; se anota como no verificado. **No**
   `blks_read`: con 128MB de `shared_buffers` la celda stock lee casi todo desde
   la cache del kernel, y `blks_read` lo cuenta igual, así que nunca se
   aplanaría. Tope `warm_max_min` (20 min), igual que Mongo.
4. **Knee.** Escalera de clientes 16/32/64/128/256/512, 60 s por escalón, sin
   `-R`. Cada escalón son **dos Jobs** de pgbench (`-c` a la mitad, `-j` = 16
   por proceso y nunca más que sus clientes: 32 de los 64 vCPU del loader). El knee es el último escalón
   con p99 < 5 ms. Mismas reglas que la escalera de YCSB (`knee.walk`,
   `ladder_never_crossed`, guard del loader por escalón con la dispensa por
   SUT saturado), más dos:
   - **por escalón**: sin transacciones muestreadas (`no_latency_samples`),
     menos de `min_samples` (10.000) en total o menos de `min_samples / 2` en
     alguno de los dos procesos, o cualquier transacción fallida = escalón no
     resuelto, no knee. Un proceso que salió con código distinto de 0, que dice
     "Run was aborted" o cuyo histograma no suma su `samples=` no tiene reporte,
     y un escalón sin reporte corta la escalera como en Mongo;
   - **por pod de pgbench**: la CPU de cada pod (API de métricas, mismas
     ventanas por escalón que el guard del nodo) contra sus propios hilos; un
     pod en ≥ 0,9 × `-j` núcleos es un generador que no podía ir más rápido y el
     escalón no cuenta (`loader_pgbench_saturated`), con la misma dispensa en
     el escalón del cruce si el SUT estaba saturado. El guard del nodo no lo ve:
     dos pods de 16 hilos al 100 % son el 50 % del loader. Por eso este guard
     falla cerrado: cada Job de cada escalón juzgado necesita al menos una
     muestra de su pod, o el escalón queda `capacity_unresolved` (y la corrida
     fija `loader_unobserved`); la dispensa del cruce no cubre la falta de
     muestra. A diferencia de Mongo, la escalera **se detiene** en el
   escalón que cierra el recorrido: los de arriba nadie los mira.
5. **Corridas fijas** al 80 % de los tps del knee, `-R` repartido entre los dos
   procesos, 480 s, con **el doble de clientes que el knee** (tope
   `max_connections - 10`): bajo `-R`, `-c` solo limita cuántas transacciones
   hay en vuelo, y con los clientes del knee al 80 % de sus tps cada sesión
   está ocupada el 80 % del tiempo y el calendario de Poisson hace cola detrás
   de ellas. Inválida si: p99 **de servicio** > SLO, p99 del **schedule lag** >
   `pg_max_lag_p99_ms` (1,0 ms; `fixed_generator_lagging`), entrega < 0,95 ×
   objetivo, algún proceso sin reporte, pocas muestras, sin muestras o
   transacciones fallidas, o algún pod de pgbench saturado.

## El p99

pgbench no imprime percentiles. Cada Job escribe un log por transacción
muestreado (`--sampling-rate`, 0,02 por defecto) y, al terminar pgbench,
imprime un marcador, `rc=<código de salida>`, `samples=<N>`, el histograma de
la latencia **de servicio** (`uniq -c`: "<cantidad> <µs>") y, tras un segundo
marcador, el del **schedule lag**. La latencia de servicio es el campo `time`
menos el `schedule_lag`: bajo `-R` pgbench cuenta `time` desde el inicio
programado, así que trae el atraso del generador adentro; sin `-R` no hay lag
y `time` ya es la de servicio. En una corrida con `-R` (el resumen trae
`rate limit schedule lag:`) el histograma del lag también tiene que sumar
`samples=`; uno vacío o cortado dejaría pasar el presupuesto de lag sin
datos, así que ese proceso queda sin reporte. El SLO juzga al servidor con la de servicio y el
presupuesto de lag juzga al generador aparte. A `kubectl logs` llegan unos
miles de líneas y no cientos de miles.
`knee.merge_pgbench` suma los histogramas de los dos procesos, así que el p99
es **exacto** sobre la unión de las muestras (no el máximo de dos p99 como en
go-ycsb). La cantidad de muestras queda en el reporte (`Samples`, y
`MinProcSamples` / `Procs` por proceso), igual que `LagP99(us)` y `LagMax(us)`
en las corridas con `-R`. Un reporte sin muestras no trae campos de latencia.

El reporte fusionado usa el formato de líneas de go-ycsb (`READ` y `TOTAL`, la
misma línea: select-only es una lectura por transacción), así que
`parse_ycsb`, `series_from_ycsb`, `ycsb_invalid_reasons` y `analysis.stats`
lo leen sin cambios. En el disco: `knee-c<N>.txt` y `run-<i>/pgbench.txt`
fusionados, y al lado la salida propia de cada proceso (`knee-c128-c1.txt`,
`pgbench-c2.txt`…).

## Qué decide la calibración

- **SLO.** 5 ms como el READ de Mongo es un punto de partida. En la laptop el
  p99 de select-only a lazo cerrado fue 90 µs; hay que ver dónde cruza cada
  familia y si 5 ms deja la escalera sin cruzar (`ladder_never_crossed`).
- **Presupuesto de lag.** `pg_max_lag_p99_ms` = 1,0 ms (20 % del SLO) es un
  punto de partida. En la laptop, a ~4k tps con 16 clientes por proceso, el
  p99 de servicio fue 1,59 ms y el del lag 3,37 ms: esa corrida sale
  `fixed_generator_lagging`. Ver cuánto atrasa el generador en el loader y si
  el doble de clientes alcanza.
- **Escala.** 1000 (~17 GB) cabe en los 64 GiB. Medir `database_bytes` en
  `cell.json` y el tiempo del init (`-I dtGvp` genera del lado del servidor, con
  un solo núcleo).
- **`-j` y los dos procesos.** 16 hilos por proceso, 32 de los 64 vCPU del
  loader, con el guard por pod. Si algún escalón sale
  `loader_pgbench_saturated`, más procesos (`pgbench_clients`) antes que más
  hilos.
- **`--sampling-rate`.** 0,02 tiene que dar ≥ 10.000 muestras en el escalón
  más lento; el reporte trae `Samples`.
- **`io.stat` en Bottlerocket.** Que el controlador `io` esté habilitado para
  el cgroup del pod. Si no, el calentamiento falla con `cache_unreadable`
  antes de medir (no pasa en silencio).
- **Huge pages.** Hoy `try` → `off` en todas las celdas. Activarlas pide
  `vm.nr_hugepages` en el user data de la node group tuned y
  `hugepages-2Mi` en el pod: cambio de infra, decisión del speaker.
- **Modo de consultas.** Default `-M simple`, como un cliente sin preparar;
  `-M prepared` quita el parseo por consulta y movería el knee. Hoy no se usa.
