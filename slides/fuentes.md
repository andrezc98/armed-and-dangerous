# Fuentes verificadas: ARMed and Dangerous (ACD Perú, 2026-10-03)

> Verificadas el 2026-09-29 con fetch directo de la fuente oficial o de la publicación original
> (nunca memoria de entrenamiento). Precios, tipos de instancia y Spot: AWS Pricing API y EC2 API
> en us-east-1. Cifras propias: cada una apunta a su archivo en `results/` y `analysis/`.
> Formato: **dato citable** → fuente, fecha, URL, cita textual, estado, caveat.
>
> Estados: **VERIFICADO** · **CAMBIÓ** (valor anterior → actual) · **MATIZ** (la fuente dice algo
> más acotado que nuestra frase: usar su redacción) · **NO ENCONTRADO** (no decirlo en escena).
> Este archivo reemplaza la §9 del spec (tiene versiones y claims viejos, listados abajo).

## Índice

1. [Parte 1. Cifras propias (el lab)](#parte-1-cifras-propias-el-lab)
2. [Parte 2. AWS (fuentes oficiales)](#parte-2-aws-fuentes-oficiales)
3. [Parte 3. Terceros (publicaciones originales)](#parte-3-terceros-publicaciones-originales)
4. [Parte 4. Software, documentación y versiones](#parte-4-software-documentación-y-versiones)

Cada parte cierra con sus propias listas de **discrepancias con nuestros documentos** y de
**cosas que no decir en escena**.

---

## Parte 1. Cifras propias (el lab)


> Cada número que la charla diga sobre NUESTRO lab, con su archivo. Compilado 2026-09-29 desde
> `analysis/` regenerado ese día (`collect.py` → 115 celdas / 235 corridas, `headline.py`,
> `stats.py`: "sanity check ... OK" en ambos). Sin AWS: todo sale de archivos en disco.
> Formato: **dato citable** (tal como se dice en escena) → fuente, fecha, archivo(s), n, etiqueta, caveat.
> Las cifras de terceros (AWS, Phoronix, Honeycomb, Spare Cores) van en la sección de terceros, no aquí.

### Convenciones

- **Fuentes.** T7 = Task 7: d1 `results/2026-09-25-task7-d1/` (Go, Java; 2026-09-25/26), d2 `results/2026-09-26-task7-d2/` (inferencia, PostgreSQL, MongoDB, red; 2026-09-26/27), d3 `results/2026-09-27-task7-d3/` (segunda instancia de todo salvo red, x86-smtoff y x86-t8; 2026-09-27/28). T8 = arco generacional `results/2026-09-28-task8-arc/` + `results/2026-09-28-task8-arc-r2/` (2026-09-28). T9 = escenas `results/2026-09-28-task9/` (2026-09-28). CAL = calibración `results/2026-09-2{4,5,6}-cal-*` (n=1).
- **n.** "2 días × 3" = dos instancias independientes (máquina distinta, día distinto) × 3 corridas fijas por día. Es el estándar del titular de T7.
- **Etiquetas** (de `analysis/stats.md`, método en stats.md:5-20): **clara** = el intervalo bootstrap excluye 1.00 y los rangos por día no se tocan; **leve** = no se tocan pero el intervalo llega a 1.00; **dentro del ruido** = los rangos por día se solapan. **Sin etiqueta** = descriptivo (contadores, un solo día, arco) o derivado aquí.
- **Precios** on-demand us-east-1 de `results/cost.md:28-39`: m9g 0.78272, m8a 0.97376, m8i 0.84672 $/h (m9g es 7.6 % más barato que m8i y 19.6 % más barato que m8a). "Por $" = throughput ÷ $/h, normalizado a x86 = 1.00.
- **Chips.** arm = m9g.4xlarge (Graviton5), amd = m8a.4xlarge (EPYC 9R45), x86 = m8i.4xlarge (Xeon 6). Todos .4xlarge, 16 vCPU, 64 GiB.
- Las líneas citadas (`stats.md:NN`, `headline.md:NN`) corresponden a los archivos generados el 2026-09-29; si se regeneran con datos nuevos, las líneas pueden moverse.

---

### Slide 3. La promesa (Graviton5 vs Graviton4)

**O-01. "En nuestro Java, Graviton5 hizo el doble que Graviton4: 80 mil contra 40 mil rps en el mismo tamaño, repetido en dos nodos de Graviton4."**
- Fuente: T8 arco, Java stock (JDK 25, PetClinic REST), 2026-09-28.
- Archivos: `analysis/headline.md:35-36` (m8g 40.0k "2 nodes", m9g 80.0k); `results/2026-09-28-task8-arc/java/arc-m9g/`, `.../arc-m8g/`, `results/2026-09-28-task8-arc-r2/java/arc-m8g/`; `analysis/data/runs.csv` filas `arc-m8g`/`arc-m9g` (`run_knee` 40000 / 80000).
- n: 1 corrida fija por familia; m8g en 2 nodos distintos (40k y 40k).
- Etiqueta: sin etiqueta (arco orientativo, n=1).
- Caveat: una sola carga (Java stock). AWS dice "hasta 25 %" y las suites amplias dan ~30 %: decir los dos ("en nuestro Java 2x; en suites ~30 %; decide tu workload"). Por $ es 3.27x/1.78x = **1.84x** (headline.md:35-36).

**O-02. "Para servir mil peticiones por segundo, Graviton5 gastó 0.15 núcleos; Graviton4, 0.31."**
- Fuente: T8 arco, 2026-09-28. Cálculo: mediana de CPU del pod durante la corrida fija ÷ tasa fija (krps).
- Archivos: `analysis/data/telemetry.csv` (`top_pod_cpu_cores_median`: m9g 9.51, m8g 9.83 / r2 9.72) y `analysis/data/runs.csv` (`rate`: 64000 / 32000; `delivered_rps` 63.9k / 32.0k). m9g 9.51/64 = **0.149**; m8g 9.83/32 = **0.307** (r2: 9.72/32 = 0.304). Ledger: `.superpowers/sdd/2026-09-02-armed-and-dangerous/progress.md:412`.
- n: 1 corrida por familia (m8g: 2 nodos).
- Etiqueta: sin etiqueta.
- Caveat: CPU de `metrics-server` (muestras cada 10 s), no contadores PMU. Con `delivered_rps` en vez de `rate` sale 0.149 / 0.308. Coherente con IPC de APerf en el arco: m9g 1.92 vs m8g 1.16 / 1.20 (telemetry.csv `pmu_ipc_p50`, 1 corrida).

---

### Slide 4. vCPU ≠ vCPU

**O-03. "Misma talla, 16 vCPU: en el Xeon son 8 núcleos con SMT; en Graviton5 y en el EPYC son 16 núcleos físicos."**
- Fuente: hardware leído en nodos reales (gate 2026-09-04) + spec.
- Archivos: `analysis/facts-setup.md` §1.1 (tabla) y lista bajo ella: m8i `thread_siblings_list` de cpu0 = `0,8`; m9g = `0`; m8a 16 núcleos × 1 hilo (`results/profiler-gate.md:7-20`, `infra/nodegroups.tf:71-90`).
- n: lectura de nodo, no medición de rendimiento.
- Etiqueta: n/a (hecho de hardware).
- Caveat: en m8a la topología viene de spec/infra, no de una lectura `thread_siblings_list` en disco.

**O-04. "Apagamos SMT en el Xeon: el Java pasó de 46 mil a 30 mil rps (0.65x)."**
- Fuente: T7 d1 solamente, 2026-09-25/26.
- Archivos: `analysis/stats.md:36,39,147`; `analysis/data/stats-comparisons.csv:77`; `results/2026-09-25-task7-d1/java/x86-smtoff/`.
- n: 1 día × 3 (smtoff); stock 2 días × 3, pero la comparación usa d1.
- Etiqueta: clara (con la advertencia de un solo día: el intervalo solo remuestrea corridas de una máquina).
- Caveat: **no es una comparación de una sola variable**: x86-smtoff lleva además el paquete JIT completo (`-TieredCompilation`, code cache 64M) que x86-stock y x86-tuned no llevan (facts-setup.md, pregunta abierta 1). Decirlo así: "sin SMT y con otros flags JIT". Pod de 7 vCPU exclusivas en vez de 15.

**O-05. "Cada pod medido tuvo 15 vCPU exclusivas; el runner verificó el cpuset antes de cada celda o la abortó."**
- Fuente: diseño del lab + verificación en cada celda.
- Archivos: `analysis/facts-setup.md` §1.4 (static CPU manager, 1 vCPU reservada, allocatable 15750m; `runner/cell.py:477-518`); ejemplo `results/2026-09-25-task7-d1/java/amd-tuned/run-1/meta.json` (`cpuset "1-15"`, count 15); columnas `cpuset`, `cpuset_count` en `analysis/data/runs.csv`.
- n: todas las corridas de T7.
- Etiqueta: n/a (control).
- Caveat: en x86 con SMT, la cpu0 reservada comparte núcleo físico con uno de los 15 hilos del pod (facts-setup.md §1.4). x86-smtoff: 7 vCPU.

---

### Slide 5. Las perillas (cuánto tuning necesita cada silicio)

**O-06. "El tuning de Java dio +15 % en el Xeon, +10 % en Graviton5 y nada medible en el EPYC."**
- Fuente: T7 d1+d3.
- Archivos: `analysis/stats.md:132-134`; `analysis/decision-guide.md` Path 0.
- n: 2 días × 3 por celda.
- Etiqueta: x86 1.15x clara; arm 1.10x clara; amd 1.01x dentro del ruido.
- Caveat: "tuned" = mejor configuración medida por chip, no las mismas flags: x86 = THP + C-states a C1 + `-XX:+UseTransparentHugePages` (tiered on); arm = THP + paquete CMP333; amd = THP + C1 + CMP333 (facts-setup.md §3.1, §3.7).

**O-07. "Con todas sus perillas, el Xeon llegó a 53 mil rps; Graviton5 sin tocar nada hizo 80 mil."**
- Fuente: T7 d1+d3.
- Archivos: `analysis/stats.md:37` (arm stock 80.0k, d1 80k / d3 80k) y `:42` (x86 tuned 53.0k, d1 54k / d3 52k).
- n: 2 días × 3.
- Etiqueta: sin etiqueta propia en stats.md (comparación cruzada stock vs tuned, derivada aquí: 80/53 = 1.51x); los rangos por día no se tocan (80–80 vs 52–54).
- Caveat: es la frase candidata "x86 necesitó tres perillas para llegar donde Graviton arranca"; lo que dicen los datos es que **ni con las perillas llega**. En Graviton el sistema operativo no puede controlar C-states (frecuencia fija), así que tiene una perilla menos (facts-setup.md §1.1).

**O-08. "Ajustar los hilos de llama.cpp al tamaño del pod dio +29 % en el Xeon, +20 % en el EPYC y +7 % en Graviton5."**
- Fuente: T7 d2+d3.
- Archivos: `analysis/stats.md:135-137`.
- n: 2 días × 3.
- Etiqueta: x86 1.29x clara; amd 1.20x clara; arm 1.07x **leve**.
- Caveat: arm tuned d2 = 100.0 vs d3 = 108.0 tok/s (stats.md:33, deriva +8 %); el d2 quedó sin explicación en el ledger. En Graviton decir "entre 0 y 13 %", no "7 %" como número firme.

**O-09. "En PostgreSQL, shared_buffers de 16 GB más páginas grandes para la memoria compartida dieron +19 a +24 % en los tres chips."**
- Fuente: T7 d2+d3.
- Archivos: `analysis/stats.md:138-140` (arm 1.21x, amd 1.19x, x86 1.24x).
- n: 2 días × 3 (knee por día).
- Etiqueta: clara en los tres.
- Caveat: shared_buffers solo, sin THP, daba +4.6 a +9.5 % en calibración (n=1, progress.md:248); THP para shmem sumó +11.3 % arm / +12.3 % amd / +11.5 % x86 al knee, con 93.6–93.7 % del pool en páginas de 2 MiB (progress.md:285-287; facts-setup.md §3.5).

**O-10. "En MongoDB, THP no movió nada: 1.00x en Graviton5 y en el EPYC, +3 % en el Xeon."**
- Fuente: T7 d2+d3.
- Archivos: `analysis/stats.md:141-143`.
- n: 2 días × 3.
- Etiqueta: arm y amd dentro del ruido; x86 1.03x clara (pero pequeña).
- Caveat: Mongo no está limitado por CPU en el knee.

**O-11. "La perilla de red del runbook de latencia no dio un solo Gbps más y costó más CPU: 2.2x por Gbps en Graviton5, 2.1x en el EPYC, 1.2x en el Xeon."**
- Fuente: T7 d2 solamente (sin segunda instancia).
- Archivos: `analysis/stats.md:179-187`; `results/2026-09-26-task7-d2/net/`; ledger progress.md:290-294.
- n: 1 día × 3.
- Etiqueta: sin etiqueta (un solo día, sin intervalo).
- Caveat: la perilla (IRQ fijadas por núcleo, adaptive-rx off) es un ajuste de **latencia**; iperf3 -P 8 mide throughput, así que el lab ve el costo y no el beneficio. Encuadre: "mide tu objetivo", no "la perilla es mala". El ledger dice "~1.3x" en x86 con rangos crudos; stats.md (mediana de la razón) dice 1.20x: usar 1.2x.

---

### Slide 6. El lab

**O-12. "Un clúster EKS 1.36, una zona, un loader de 64 vCPU, un pod por nodo con 15 vCPU exclusivas; el loader nunca pasó de 70 % o la corrida no contaba."**
- Fuente: diseño + guardas del runner.
- Archivos: `analysis/facts-setup.md` §2.1-2.3, §4.7; `results/cost.md:34` (c8i.16xlarge); `analysis/data/runs.csv` `loader_peak_percent`.
- n: n/a.
- Etiqueta: n/a.
- Caveat: las celdas de T7 corrieron en managed node groups, no en Karpenter (Karpenter solo en T8/T9). Resuelto en `slides/visuals/08-arquitectura` (2026-10-01): dice "managed node groups", sin Karpenter.

**O-13. "Tres silicios, seis clases de workload: Java, Go, inferencia, PostgreSQL, MongoDB y red."**
- Archivos: `analysis/headline.md:5-18`; `analysis/stats.md:173-187` (red).
- Caveat: el abstract promete Java, MongoDB e inferencia; Go, PostgreSQL, red y la columna AMD son adiciones.

---

### Slide 7. Metodología

**O-14. "Cada celda corrió en dos máquinas distintas, en días distintos, con tres corridas fijas de 8 minutos cada una."**
- Fuente: T7 d1/d2 + d3.
- Archivos: `analysis/stats.md:3` (alcance), `:22-57`; `analysis/facts-setup.md` §4.2 (480 s al 80 % del knee).
- n: 2 días × 3 (inferencia: corridas de 6 min, 360 s).
- Caveat: excepciones de un solo día: red (d2), x86-smtoff (d1), x86-t8 (d2).

**O-15. "De un día a otro, con otra máquina del mismo tipo, los resultados se movieron entre 0 y 8 %."**
- Archivos: `analysis/stats.md:26-57` (columna "drift d→d"; máximo +8.0 % en inferencia arm tuned, stats.md:33).
- n: 2 días por celda.
- Caveat: con dos máquinas por celda no se ve la variación de toda la flota.

**O-16. "Hicimos 77 comparaciones: 67 claras, 1 leve y 9 dentro del ruido."**
- Archivos: `analysis/stats.md:236-240` (lista de etiquetas); `analysis/data/stats-comparisons.csv` (77 filas).
- Caveat: el bootstrap con 2 días solo puede combinar 3 pares de días (stats.md:15); por eso se reporta también la envolvente mín–máx.

**O-17. "El día 3 terminó con 30 de 30 celdas válidas y cero corridas inválidas."**
- Archivos: progress.md:383 (`=== 2026-09-28 05:15Z — Task 7 day 3 COMPLETE incl. MongoDB (30/30 cells, 0 invalid runs)`); d1+d2: progress.md:328 (38/38 celdas, todas las corridas publicadas válidas tras el re-juicio R3 de 0.25 %).
- Caveat: 7 corridas Java del d1 eran inválidas bajo la regla vieja de 0.1 % de iteraciones descartadas y válidas bajo R3 (`analysis/data/README.md`, "Re-judged records").

**O-18. "El knee es el último escalón con p99 bajo el SLO: 10 ms en Java, 20 ms en Go, 5 ms de lectura en MongoDB y PostgreSQL."**
- Archivos: `analysis/facts-setup.md` §4.2, §4.4, §4.5.
- Caveat: inferencia no tiene SLO: es un loop cerrado con 4 slots y se mide tok/s agregado.

---

### Slide 8. Cómo leemos el porqué (APerf)

**O-19. "Solo cuatro contadores existen en los tres chips: IPC, fallas de predicción de saltos, fallas de caché L1 de instrucciones y ciclos detenidos en el front-end."**
- Archivos: `analysis/data/README.md` (tabla "PMU availability"); `analysis/stats.md:191-193`.
- Caveat (decir en escena): m8i expone solo IPC, branch, L1d/L1i y stall-frontend; m8a no tiene L1d, L3 ni stall-backend; m9g tiene todo salvo L3. Cada fabricante mapea los nombres a sus propios eventos: las comparaciones entre fabricantes son indicativas. El IPC entre ISAs distintas (Arm vs x86) no mide el mismo trabajo por instrucción.

---

### Slides 9-11. Java

**O-20. "Java stock: Graviton5 80 mil rps, EPYC 89 mil, Xeon 46 mil."**
- Fuente: T7 d1+d3.
- Archivos: `analysis/headline.md:12`; `analysis/stats.md:37-39`.
- n: 2 días × 3.
- Etiqueta: arm/x86 1.74x clara; amd/x86 1.93x clara; arm/amd 0.90x clara (stats.md:85-89).
- Caveat: en Java stock, **AMD gana en crudo** a Graviton5 (0.90x). Mostrarlo.

**O-21. "Por dólar, Java stock: Graviton5 1.88x el Xeon, EPYC 1.68x; Graviton5 1.12x el EPYC."**
- Archivos: `analysis/headline.md:12`; `analysis/stats.md:86,88,90`.
- Etiqueta: las tres claras.
- Caveat: la ventaja por $ de arm sobre amd es el precio (m9g 19.6 % más barato), no velocidad.

**O-22. "Java tuned: Graviton5 88 mil, EPYC 90 mil, Xeon 53 mil; Graviton5 y EPYC empatan en crudo."**
- Archivos: `analysis/headline.md:13` (marca `arm=amd`); `analysis/stats.md:40-42, 91-96`.
- Etiqueta: arm/x86 1.66x clara; amd/x86 1.70x clara; arm/amd 0.98x **dentro del ruido**.
- Por $: arm/x86 1.80x, amd/x86 1.48x, arm/amd 1.22x (todas claras, stats.md:92,94,96).
- Caveat: arm tuned va de 80k a 90k entre corridas (stats.md:40, CV 4.12 %).

**O-23. "Por qué (Java stock): IPC 1.25 en Graviton5, 1.35 en el EPYC, 0.93 en el Xeon; fallas de predicción de saltos 1.0, 2.0 y 2.5 por mil instrucciones."**
- Archivos: `analysis/stats.md:208-210` (tuned: 211-213).
- n: 6 corridas (2 días × 3), p50 de muestras de 1 s.
- Etiqueta: sin etiqueta (descriptivo).
- Caveat: ver O-19 (PMU y ISA). IPC más alto en AMD es coherente con que AMD gane en crudo en Java.

**O-24. "Flame graphs: solo los de Java están completos."**
- Archivos: `results/2026-09-27-task7-d3/flamegraphs/java-{arm,x86}-tuned.{svg,png}`; progress.md:393.
- Caveat: inferencia y PostgreSQL tienen solo frames de kernel (eBPF sin stacks de usuario): no son material de slide.

### Slide 12. Virtual threads

**O-25. "Encender virtual threads subió Java +24 % en Graviton5, +21 % en el EPYC y solo +6 % en el Xeon."**
- Archivos: `analysis/stats.md:144-146`.
- n: 2 días × 3.
- Etiqueta: las tres claras.

**O-26. "Con virtual threads, Graviton5 y el EPYC llegan a 109 mil rps los dos; el Xeon, 56 mil."**
- Archivos: `analysis/headline.md:14` (`arm=amd`); `analysis/stats.md:43-45, 97-102`.
- Etiqueta: arm/x86 1.95x clara; amd/x86 1.95x clara; arm/amd 1.00x **dentro del ruido**. Por $: arm/x86 **2.11x**, amd/x86 1.69x, arm/amd 1.24x (claras).
- Caveat: "mismo rendimiento, más barato", no "más rápido" que AMD.

---

### Slides 13-14. MongoDB

**O-27. "MongoDB: Graviton5 239 mil ops/s; EPYC y Xeon, 185 mil los dos."**
- Fuente: T7 d2+d3, YCSB workload B (95/5), 20M documentos, en caché.
- Archivos: `analysis/headline.md:15-16`; `analysis/stats.md:46-51, 103-114`.
- Etiqueta: arm/x86 stock 1.29x clara, tuned 1.26x clara; amd/x86 1.00x (stock) y 0.97x (tuned) **dentro del ruido**.
- Por $: arm/x86 1.39x (stock) / 1.36x (tuned); amd/x86 0.87x / 0.84x (claras).
- Caveat: Mongo no está limitado por CPU en el knee; el empate AMD = Intel (mismo escalón exacto los dos días en stock) dice poco de los chips (stats.md:18).

**O-28. "Por qué (Mongo stock): IPC 1.12 en Graviton5, 0.94 en el EPYC, 0.59 en el Xeon."**
- Archivos: `analysis/stats.md:217-219`.
- n: 6 corridas. Sin etiqueta. Caveat: O-19.

**O-29. "El primer intento de MongoDB no midió la CPU: midió el disco. El volumen gp3 de 125 MiB/s entregó 134 mil de 194 mil ops/s; con 1000 MiB/s, las corridas se sostuvieron."**
- Fuente: T7 d2, 2026-09-26 (celda apartada).
- Archivos: `results/2026-09-26-task7-d2/mongo-ebs125/` (`set_aside` en `analysis/data/cells.csv`); progress.md:295-297, 310.
- n: 3 corridas inválidas (EBS) + re-corrida 3/3 válida.
- Caveat: anécdota de método, no resultado de chip. El knee (242.7k) era correcto; solo las corridas largas quedaron sin disco.

---

### Slides 15-16. Inferencia (llama.cpp, Llama 3.1 8B Q4_0)

**O-30. "Inferencia en CPU, stock: Graviton5 97 tokens por segundo, EPYC 65, Xeon 44."**
- Fuente: T7 d2+d3.
- Archivos: `analysis/headline.md:8`; `analysis/stats.md:29-31, 73-78`.
- Etiqueta: arm/x86 2.18x, amd/x86 1.45x, arm/amd 1.50x (claras).

**O-31. "Inferencia tuned (-t 15): Graviton5 104 tok/s, EPYC 78, Xeon 58. Por dólar, Graviton5 rinde 1.96x el Xeon."**
- Archivos: `analysis/headline.md:10`; `analysis/stats.md:33-35, 79-84`.
- Etiqueta: arm/x86 1.81x raw / 1.96x por $; amd/x86 1.35x / 1.17x; arm/amd 1.34x / 1.67x (todas claras).
- Caveat: la imagen oficial de llama.cpp trae kernels AMX para el Xeon y **no** trae KleidiAI para Graviton en las celdas titulares. arm tuned d2 100 vs d3 108 (O-08).

**O-32. "Costo por millón de tokens (on-demand, solo el nodo): Graviton5 $2.09, EPYC $3.49, Xeon $4.09 en tuned; $2.24, $4.19 y $5.30 en stock."**
- Fuente: derivado aquí de las medias de `analysis/stats.md:29-35` y `results/cost.md:30-32` con la fórmula de `runner/analysis/stats.py:42-45` ($/h ÷ (tok/s × 3600) × 1e6).
- n: 2 días × 3 (las tok/s).
- Etiqueta: hereda la de las razones de tok/s (claras).
- Caveat: tok/s agregado de 4 slots, `max_tokens 128`, prompt fijo; no incluye loader, control plane ni Savings Plans. Calibración n=1 daba $2.00 / $3.46 / $4.09 (progress.md:219); usar los de T7.

**O-33. "llama.cpp, sin -t, usa 16 hilos en Graviton5 y en el EPYC, pero 8 en el Xeon: solo los núcleos físicos."**
- Archivos: `analysis/data/cells.csv` columna `llama_n_threads` (16 en arm/amd, 8 en x86, d2 y d3); `results/2026-09-27-task7-d3/inference/*/cell.json` (`llama_system_info`); `analysis/README.md` ("Facts verified while assembling"); progress.md:303, 307.
- Caveat: el número sale de la sonda `system_info` del runner en el mismo pod, sin `-t`; `facts-setup.md` pregunta abierta 4 todavía lo marca por confirmar para el servidor. Stock en arm/amd = 16 hilos sobre un cpuset de 15 (se sobre-suscribe en 1).

**O-34. "En calibración, pasar el Xeon de 8 a 15 hilos dio +42 % (40.6 → 57.5 tok/s)."**
- Fuente: CAL 2026-09-24, n=1.
- Archivos: `analysis/data/cells.csv` filas `2026-09-24-cal-llama-x86/x86-tuned` (40.6, 8 hilos) y `2026-09-24-cal-llama-x86t15/x86-t15` (57.5); `analysis/facts-setup.md` §3.3.
- n: 1 celda por lado.
- Etiqueta: sin etiqueta.
- Caveat: **en T7 la misma comparación dio +18 %**, no +42 %: x86-t8 47.6 vs x86-tuned 56.3 en d2 (t8/tuned = 0.85x, stats.md:148, clara, un solo día). Para el escenario usar T7 (+18 % por los hilos; +29 % tuned vs stock, O-08). El +42 % es solo historia de calibración.

**O-35. "KleidiAI en Graviton5 no mejoró este modelo en calibración: 105 contra 109 tok/s."**
- Fuente: CAL 2026-09-24, n=1.
- Archivos: `analysis/data/cells.csv` filas `2026-09-24-cal-llama-kleidiai/arm-tuned-kleidiai` (105.2) y `2026-09-24-cal-llama-arm/arm-tuned` (108.8).
- Etiqueta: sin etiqueta (n=1, dentro de la variación d2–d3 de 8 %).
- Caveat: decir "no vimos ganancia", no "KleidiAI no sirve".

**O-36. "Por qué (inferencia tuned): IPC 1.01 en Graviton5, 0.82 en el EPYC, 0.62 en el Xeon."**
- Archivos: `analysis/stats.md:204-206`. n: 6 corridas. Sin etiqueta. Caveat: O-19; el Xeon ejecuta instrucciones AMX (más trabajo por instrucción), el IPC no captura eso.

---

### (Sin slide en el plan) PostgreSQL

El plan de 25 slides no tiene slide de PostgreSQL ni columna AMD (facts-talk-scope.md §2); si entra, estas son las cifras.

**O-37. "PostgreSQL (pgbench select-only): el EPYC hace 594 mil tps; Graviton5 335 mil y el Xeon 340 mil."**
- Fuente: T7 d2+d3, tuned.
- Archivos: `analysis/headline.md:18`; `analysis/stats.md:55-57, 121-126`.
- Etiqueta: amd/x86 1.75x clara; arm/amd 0.56x clara; arm/x86 0.98x **dentro del ruido**.
- Caveat: AMD gana claro en crudo y por $; mostrarlo abiertamente.

**O-38. "Por dólar, en PostgreSQL gana AMD: 1.52x el Xeon; Graviton5 queda en 1.06x."**
- Archivos: `analysis/stats.md:122,124,126` (arm/amd por $ 0.70x).
- Etiqueta: claras.
- Caveat: arm vs x86 empatan en crudo; el 1.06x por $ es solo precio.

**O-39. "Stock: EPYC 499 mil, Graviton5 277 mil, Xeon 274 mil tps."**
- Archivos: `analysis/stats.md:52-54, 115-120`. Etiqueta: amd/x86 1.82x clara; arm/x86 1.01x dentro del ruido.

---

### Slide 17. Red (iperf3)

**O-40. "En red, el throughput es el techo de la instancia: 16.9 Gbps en Graviton5, 14.9 en el EPYC y en el Xeon."**
- Fuente: T7 d2, 2026-09-26.
- Archivos: `analysis/stats.md:179-186`; progress.md:289-294 (18/18 corridas válidas).
- n: 1 día × 3.
- Etiqueta: sin etiqueta (un día).
- Caveat: no es propiedad del chip, es el límite de red de la instancia.

**O-41. "Lo que sí depende del chip es la CPU por Gbps: recibir 1 Gbps costó 0.029 núcleos en Graviton5, 0.037 en el EPYC y 0.088 en el Xeon: tres veces más."**
- Archivos: `analysis/stats.md:179,182,185` (cores/Gbps fwd, stock); rev 0.020 / 0.030 / 0.040.
- n: 1 día × 3 (mediana).
- Etiqueta: sin etiqueta.
- Caveat: fwd = el SUT recibe. CPU del nodo menos su línea base ociosa, desde metrics API. Un solo día.

---

### Slide 18. Go

**O-42. "Go, sin tuning: Graviton5 36.5 mil rps, EPYC 29 mil, Xeon 20 mil."**
- Fuente: T7 d1+d3.
- Archivos: `analysis/headline.md:7`; `analysis/stats.md:26-28, 67-72`.
- Etiqueta: arm/x86 1.82x, amd/x86 1.45x, arm/amd 1.26x (claras). Por $: arm/x86 **1.97x**, amd/x86 1.26x, arm/amd 1.57x.
- Caveat: el spec esperaba "el chip casi no importa"; los datos dicen lo contrario. Go compilado con GOAMD64/GOARM64 por defecto (v1 / v8.0).

**O-43. "Por qué (Go): IPC 1.23 / 1.02 / 0.68; fallas de salto 1.1 / 2.4 / 3.2 por mil instrucciones."**
- Archivos: `analysis/stats.md:197-199`. n: 6 corridas. Sin etiqueta. Caveat: O-19.

---

### Slide 19. Arco generacional (m5 → m9g)

**O-44. "Desde un m5 de 2017, el Java stock rinde: m6i 1.33x, m7i 1.50x, m8i 2.0x, m8a 3.75x; en Graviton, m6g 0.92x, m7g 1.08x, m8g 1.67x, m9g 3.33x."**
- Fuente: T8, 2026-09-28.
- Archivos: `analysis/headline.md:26-36`; `results/2026-09-28-task8-arc/ledger.md`; `results/chain-arc.out`.
- n: 1 corrida fija de 300 s por familia (m8g: 2 nodos).
- Etiqueta: sin etiqueta (orientativo).
- Caveat: solo Java stock; knee fino con escalones de 2k, así que ±2k es la resolución.

**O-45. "Por dólar, desde m5: m8i 1.81x, m8a 2.96x, m9g 3.27x."**
- Archivos: `analysis/headline.md:28-36` (columna "vs m5 per $"; m6i 1.33x, m7i 1.43x, m6g 1.14x, m7g 1.27x, m8g 1.78x).
- Caveat: precios de m5–m8g capturados 2026-09-28 (`results/cost.md:33-38`).

**O-46. "El arco mide en la misma escala que el benchmark: m9g 80 mil = 80 mil; m8a 90 mil frente a 88–90 mil; m8i 48 mil frente a 46 mil."**
- Archivos: `analysis/headline.md:24` y `:31-36` frente a `:12`; corridas T7 x86 stock 44–48k (stats.md:39).
- Caveat: m8i del arco (48k) cae dentro del rango de corridas de T7 (44–48k), pero arriba de la mediana (46k).

**O-47. "Graviton2 (m6g) rinde menos que el m5 en crudo (0.92x), pero es 14 % mejor por dólar."**
- Archivos: `analysis/headline.md:33`.
- Caveat: n=1; importa para O-49 (Karpenter eligió justo m6g).

---

### Slide 20. Migración: node groups mixtos + Karpenter (clip)

**O-48. "Un pod sin nodeSelector ni afinidad: Karpenter lanzó un m6g.4xlarge y el nodo estuvo Ready en 30 segundos."**
- Fuente: T9, 2026-09-28 17:57–17:58Z.
- Archivos: `results/2026-09-28-task9/karpenter-clip.txt:27-43` (apply 17:57:36Z; "arc node Ready after 30 s", "pod Ready after 30 s" a las 17:58:07Z; nodeclaim `m6g.4xlarge`, on-demand, us-east-1a); `results/2026-09-28-task9/clip-deployment.yaml` (request 8 CPU / 8 Gi, imagen pause).
- n: 1 escena.
- Caveat: la línea de log "created nodeclaim" (`karpenter-clip.txt:48`) lista los candidatos `m6g.4xlarge, m7g.4xlarge, m8g.4xlarge, m9g.4xlarge`: los NodePools del lab solo permitían familias .4xlarge on-demand, y el mismo log muestra `aad/mongo-0` también pendiente. Karpenter 1.14.1.

**O-49. "Karpenter eligió por precio: la familia más barata, Graviton2 de 2019. Sin fijar familias, te llevas 0.92x de un m5, no 3.33x."**
- Archivos: `karpenter-clip.txt:48-49` (candidatos y elegido); `results/cost.md:36` (m6g 0.616 $/h, el menor de la lista); `analysis/headline.md:33,36`; `analysis/decision-guide.md` Path C.
- Caveat: Karpenter no tiene señal de rendimiento; en el clip, con 4 familias permitidas, eligió la más barata. Es un ejemplo, no una regla medida en muchos lanzamientos.

**O-50. "Al borrar la escena, Karpenter retiró los dos nodos en 127 segundos."**
- Archivos: `results/2026-09-28-task9/karpenter-clip.txt:53` ("WhenEmpty consolidation removed both arc nodes after 127 s", 18:02:45Z).
- Caveat: los dos nodos son el m6g del clip y el m6i de la escena DaemonSet; consolidación `WhenEmpty` después de 1 min (facts-setup.md §2.5).

---

### Slide 21. El bloqueador de los DaemonSets (escena)

**O-51. "Un DaemonSet con imagen solo amd64: corre en el nodo x86 y en los dos nodos Graviton el contenedor muere con `exec /bin/sh: exec format error`."**
- Fuente: T9, 2026-09-28 17:59–18:00Z.
- Archivos: `results/2026-09-28-task9/daemonset-blocker.txt:29-42` (legacy-agent-8tglw `1/1 Running` en ip-10-42-13-198 = **m6i.4xlarge** amd64, log "agent up on x86_64"; legacy-agent-6xcqj en m6g.4xlarge y legacy-agent-d62ht en m7g.large, ambos arm64, `0/1 Error`, 3 reinicios, log `exec /bin/sh: exec format error`); `:56-76` (Exit Code 255, evento `BackOff ... Back-off restarting failed container`); manifiesto `results/2026-09-28-task9/legacy-agent-daemonset.yaml` (busybox 1.37 fijado al digest linux/amd64).
- n: 1 escena, 3 nodos.
- Caveat: el pull de la imagen **funciona** (`Successfully pulled`, línea 72); el fallo es al ejecutar, no `ImagePullBackOff` como anticipaba el spec. El nodo amd64 es un **m6i**, no un m5 (el ledger progress.md:406 dice "m5": error del ledger). Los "tres ejemplos vivos" del spec (profiler, C-states, net-tuned) no se ejecutaron en la escena; el transcript solo muestra (líneas 78-108) que los DaemonSets de perillas usan `nodeAffinity` por `aad/cell`.

**O-52. "La imagen se descarga sin error en los nodos Graviton: nada avisa hasta que el contenedor arranca."**
- Archivos: `daemonset-blocker.txt:70-76`.
- Caveat: con un manifiesto de una sola plataforma, containerd baja la única variante disponible. Con un índice multi-arch sin la variante arm64, el error sería otro (no medido).

---

### Slide 22. Regla de decisión

**O-53. "Promedio geométrico por dólar, mejor configuración de cada chip: Graviton5 1.59x el Xeon; el EPYC 1.23x; Graviton5 1.29x el EPYC."**
- Archivos: `analysis/stats.md:165-171` (tabla de media geométrica; con vthreads 1.64x / 1.26x / 1.30x; solo stock 1.68x / 1.30x / 1.29x).
- n: 5 clases (sin red).
- Etiqueta: sin etiqueta propia (agregado de razones claras y dentro del ruido).
- Caveat: en crudo arm/amd = **1.04x**: casi iguales en velocidad promedio; la diferencia es precio.

**O-54. "Graviton5 gana por dólar en cinco de seis clases; AMD gana PostgreSQL en crudo y por dólar."**
- Archivos: `analysis/stats.md:156-163` (sección 4); `analysis/README.md` ("The results in one table").
- Caveat: las cinco son Go, Java, inferencia, MongoDB y eficiencia de red (CPU/Gbps, un solo día, sin cálculo por $). Contra el Xeon, Graviton5 gana por $ también en PostgreSQL (1.06x), pero pierde contra AMD.

**O-55. "Por clase, contra el Xeon por dólar: Go 1.97x, Java 1.80x (2.11x con virtual threads), inferencia 1.96x, MongoDB 1.36x, PostgreSQL 1.06x."**
- Archivos: `analysis/stats.md:158-163`; `analysis/decision-guide.md` Path C.
- Etiqueta: todas claras.

**O-56. "Si hoy estás en un m5 con Java y debes seguir en x86: m8a da ~3.75x en crudo y ~3x por dólar; m8i, 2x y 1.8x."**
- Archivos: `analysis/decision-guide.md` Path A/B y "Example routes"; `analysis/headline.md:31-32`.
- Etiqueta: [M8] (arco, n=1).

**O-57. "Burstable (t3/t2) sin créditos: ahí no hay benchmark, hay una clase de instancia equivocada."**
- Archivos: `analysis/decision-guide.md` "Burstable today".
- Etiqueta: **[E] estimado**, no medido. Ver "Cifras que NO se pueden decir".

---

### Slide 24. Lo que costó el lab

**O-58. "Este lab costó alrededor de 320 dólares de on-demand, de los cuales 114 ya están confirmados en Cost Explorer."** (usar esta frase solo si Cost Explorer no se actualiza antes del 10-03; si se actualiza, cambiarla por la cifra real)

Desglose (todo lo que registran `progress.md` y los ledgers; separado por origen):

| Concepto | USD | Tipo | Fuente |
|---|---|---|---|
| Cost Explorer, servicios del lab hasta 2026-09-26 | **113.74** | **real** (con retraso; el 26 puede estar incompleto) | progress.md:340 |
| Estimación del controlador "a la fecha" 2026-09-27 ~04:40Z, incl. noche ociosa | ~175 | estimado | progress.md:340 |
| "Task 7 ≈ $185" | ~185 | estimado (otro corte: solo T7) | progress.md:340 |
| Fijo 09-27 04:40Z → 09-28 10:50Z (loader c8i.16xlarge + tools m7g.large + control plane = 3.18 $/h × 30.2 h) | ~96.0 | estimado (derivado aquí) | progress.md:330, 389-390; `results/cost.md:34-39` |
| SUT del día 3 (suma de filas de celdas) | 20.08 | estimado del runner (minutos × tarifa) | `results/2026-09-27-task7-d3/ledger.md`; facts-history.md §7 |
| Volumen Mongo subido a 16000 IOPS / 1000 MiB/s, resto hasta la reversión 09-28 ~11:00Z | ~4 | estimado (~3.3 $/día) | progress.md:391, 395 |
| Estacionado 09-28 ~11:00Z → ~17:55Z (control plane + volúmenes; nodo tools cordonado hasta 16:05Z) | ~1 | estimado | progress.md:390-396 |
| Fijo del día T8/T9 (~17:55Z → destroy 23:35Z, 5.7 h × 3.18) | ~18.1 | estimado (derivado aquí) | `karpenter-clip.txt:3` (tools con 2m12s a las 17:58Z); progress.md:411 |
| SUT del arco (9 familias + re-corrida m8g) | 3.64 | estimado del runner | `results/2026-09-28-task8-arc/ledger.md` (3.30) + `-arc-r2/ledger.md` (0.34) |
| Nodos Karpenter de T9 (m6g ~5 min, m6i ~4 min) | ~0.1 | estimado (derivado aquí) | `karpenter-clip.txt`, `daemonset-blocker.txt:1-5` |
| **Total estimado al cierre (2026-09-28 23:35Z)** | **~318** | estimado: 175 + 96 + 20 + 4 + 1 + 18 + 3.6 + 0.1 | |
| Después del cierre: snapshot Pyroscope 20 GB (~1 $/mes) + almacenamiento ECR | < 2/mes | estimado | progress.md:415 |

- **No sumar los "total" de los ledgers por directorio**: cada uno carga una línea fija modelada de 6 h (loader + tools + control plane), así que los ~30 directorios de calibración repiten 10–19 $ que no existieron (facts-history.md, contradicción 5). Solo las filas SUT de los ledgers son reales en su forma (minutos × tarifa).
- Plan original: ~40–70 $ en total (spec:26) y T7 "~25–35 $" (plan:263). El techo de 200 $ se relajó el 2026-09-04.
- **Qué falta para un total real**: (1) Cost Explorer para 2026-09-27, 09-28 y 09-29 (retraso de 24–48 h; consultar desde el 2026-09-30, filtrado por la cuenta sandbox y sin créditos/reembolsos); (2) confirmar que el 2026-09-26 ya está completo en los 113.74; (3) cargos no modelados: IPv4 públicas (subredes públicas, `map_public_ip_on_launch`), EBS de los nodos, logs de CloudWatch del control plane si el módulo los creó, transferencia de datos, pulls de ECR; (4) el día del smoke gate (2026-09-04, ledger 6.51 $) y la calibración 09-24/25 ya deberían estar dentro de los 113.74; verificarlo con el desglose diario.
- Caveat: el ~175 del controlador y el ~96 del tramo fijo son las dos piezas más grandes y las dos son estimaciones. Rango honesto: 290–340 $.

---

#### Actualización 2026-09-29: Cost Explorer (costo real)
- **El lab costó unos $345 en recursos propios; la cuenta completa, $434** (2026-09-03 → 2026-09-29, UnblendedCost, sin créditos ni reembolsos).
- Fuente: AWS Cost Explorer, cuenta sandbox, consultado 2026-09-29 (`aws ce get-cost-and-usage`, agrupado por servicio). 09-28 y 09-29 todavía figuran como estimados y pueden moverse un poco.
- Recursos del lab: EC2 cómputo $317.58, EC2 otros (EBS, IPs) $12.52, EKS $10.00, VPC $1.26, CloudWatch $3.04.
- Servicios de seguridad de la cuenta (no son el lab, pero su costo crece con la actividad del lab): AWS Config $30.17, Amazon Detective $32.84, GuardDuty $9.95, Security Hub $8.89, Inspector $3.24, CloudTrail $2.53, Systems Manager $1.68 (≈ $89).
- Por día (total de la cuenta): 09-25 $69.28 · 09-26 $118.21 · 09-27 $121.73 · 09-28 $94.44 (estimado).
- Estado: **REAL** (reemplaza la estimación de ~$318 de arriba, que no incluía los servicios de seguridad y subestimaba el tiempo del clúster encendido).
- En escena: "unos $345 en infraestructura del lab; con los guardrails de seguridad de la cuenta, $434". No sumar los "total" de los ledgers por celda.

### Hechos de hardware y plataforma medidos (apoyo para cualquier slide)

**O-59. "Graviton5 no deja al sistema operativo controlar C-states: no expone estados de reposo."** — m9g: cpuidle driver `none`, sin idle states; m8i: `intel_idle`, POLL/C1/C1E/C6/C6P (`results/profiler-gate.md:7-20`; facts-setup.md §1.1). Gate 2026-09-04, lectura de nodo.

**O-60. "La perilla de C-states del Xeon se leyó en el nodo: `/dev/cpu_dma_latency` = 1 µs (C1)."** — `results/profiler-gate.md:15`; facts-setup.md §1.5. Caveat: en m8a la latencia de C1 no se verificó en nodo real; solo `cstates_ready: true` en las corridas amd-tuned (facts-setup.md pregunta abierta 5).

**O-61. "Nodo m6g.4xlarge de Karpenter: 15890m de CPU asignable."** — `karpenter-clip.txt:49`. (Los MNG del lab: 15750m, con 250m reservados que el kubelet redondea a 1 vCPU; facts-setup.md §1.4.)

**O-62. "La imagen oficial de llama.cpp detectó AMX en el Xeon, AVX-512 sin AMX en el EPYC, y NEON + SVE + MATMUL_INT8 en Graviton5, sin KleidiAI."** — `results/2026-09-27-task7-d3/inference/*/cell.json` (`llama_system_info`); facts-setup.md §3.3.

---

### Cifras que NO se pueden decir

Parecen tentadoras; los datos no las sostienen.

1. **"Graviton5 es más rápido que AMD en Java tuned / virtual threads."** Empate en crudo (0.98x y 1.00x, dentro del ruido, stats.md:95, 101). Lo correcto: "misma velocidad, 20 % más barato" (por $ 1.22x / 1.24x, claras).
2. **"Graviton5 es más rápido que el Xeon en PostgreSQL."** 0.98x (tuned) y 1.01x (stock) crudos, dentro del ruido (stats.md:115, 121). El 1.06x / 1.09x por $ es solo precio: decir "empata y cuesta menos".
3. **"AMD es más lento que Intel en MongoDB"** o cualquier lectura de chip del empate AMD = Intel en Mongo. Mismo escalón exacto los dos días; Mongo no está limitado por CPU en el knee (stats.md:18). El 0.84x/0.87x por $ de AMD es precio sobre un empate.
4. **"THP no sirve para MongoDB"** como ley general. Solo: "en este Mongo, en caché y no limitado por CPU, no movió nada" (stats.md:141-143).
5. **Cualquier número de red, x86-smtoff o x86-t8 dicho como "dos instancias".** Son de un solo día (red d2, smtoff d1, t8 d2): stats.md:32, 36, 147-148, 173-175. Decir "un día, tres corridas".
6. **"Apagar SMT le quita 35 % al Xeon."** El 0.65x mezcla SMT off con otros flags JIT y un pod de 7 vCPU (facts-setup.md pregunta abierta 1). Decir "sin SMT y con otros flags JIT, 30 mil contra 46 mil".
7. **"El día 2 de inferencia en Graviton fue un nodo ruidoso."** El ledger lo deja sin explicación (analysis/README.md; facts-history.md contradicción 10). Decir "varió 8 % entre dos máquinas; no sabemos por qué".
8. **"El tuning de llama.cpp da +7 % en Graviton5"** como número firme. Etiqueta leve (intervalo 1.00–1.13, stats.md:135).
9. **"Pasar el Xeon a 15 hilos da +42 %."** Es calibración n=1 (40.6 → 57.5). En T7 los hilos dieron +18 % (t8 47.6 vs tuned 56.3, d2) y tuned vs stock +29 %.
10. **"Graviton5 es 2x Graviton4"** sin calificar. Es un solo workload (Java stock), 1 corrida por familia, en 2 nodos m8g. Suites amplias: ~30 %. Siempre las dos cifras.
11. **Las filas "sin créditos" de t3/t2 (5x, 9.4x, 12.9x, 24.1x…) como resultados de benchmark.** Son estimaciones [E] con fórmula (decision-guide.md, "Burstable today"), no mediciones. Si se muestran: "estimado", y leerlas como "estás en la clase equivocada".
12. **"Karpenter siempre elige Graviton2."** Una escena, un lanzamiento, NodePools con 4 familias permitidas (O-49). Lo medido: "eligió por precio; en el clip, la más barata".
13. **"El DaemonSet queda en ImagePullBackOff."** No: la imagen se baja y el contenedor muere con `exec format error` (daemonset-blocker.txt:36, 72). Y el nodo amd64 fue un m6i, no un m5.
14. **"IPC 1.25 contra 0.93: Graviton hace 34 % más trabajo por ciclo."** IPC entre Arm y x86 cuenta instrucciones distintas; los contadores son indicativos entre fabricantes y m8i expone solo cuatro (data/README.md). Usarlos como pista del porqué, no como medida de trabajo.
15. **"Graviton5 gana por dólar en red: X veces."** No hay cálculo por $ de red; el throughput es el techo de la instancia. Lo medido es CPU por Gbps (un día).
16. **"Este lab costó $X"** con una cifra exacta que no sea la de Cost Explorer. Hoy solo 113.74 $ son reales (hasta 09-26); el resto es estimación (~318 $). Tampoco sumar los "total" de los ledgers por directorio.
17. **Flame graphs de inferencia o PostgreSQL** como explicación. Solo tienen frames de kernel (progress.md:393).
18. **"Primera evidencia pública de inferencia en Graviton5."** Spare Cores publicó llama.cpp en m9g el 2026-06-12 (CLAUDE.md; facts-talk-scope.md).
19. **"$/Mtok de 2.00 / 3.46 / 4.09"** de calibración. Usar los de T7 (O-32): 2.09 / 3.49 / 4.09 tuned.
20. **"El arco dice que m8i hace 48 mil."** El arco es n=1; para m8i la cifra de benchmark es 46 mil (mediana de 2 días × 3). Si se muestran juntos, decir que el arco calibra, no reemplaza.

---

## Parte 2. AWS (fuentes oficiales)


> Verificadas el 2026-09-29 con fetch directo de páginas oficiales de AWS (aws.amazon.com, docs.aws.amazon.com, aboutamazon.com, github.com/aws) y con la AWS CLI en solo lectura (perfil sandbox, `us-east-1`: `pricing get-products`, `ec2 describe-instance-types`, `ec2 describe-spot-price-history`). Nada sale de memoria de entrenamiento.
> Formato: **dato citable** → fuente, fecha de publicación, URL, verificado, cita textual (idioma original), estado, caveat.
> Estados: VERIFICADO · CAMBIÓ (antes → ahora) · NO ENCONTRADO · MATIZ (la redacción oficial es más estrecha que la nuestra).
> Nota de método: las citas de páginas de producto y blogs llegaron vía extractor de WebFetch; las de docs.aws.amazon.com (processor state control, CPU options, launch templates, créditos burstable, versiones EKS) y de `gp.html` se leyeron en crudo.

---

### 1. Graviton5 / M9g

#### 1.1 **M9g con Graviton5: disponible de forma general el 10 de junio de 2026**
- Fuente: AWS News Blog, "Now available: Amazon EC2 M9g and M9gd instances powered by new AWS Graviton5 processors" (Esra Kayabali).
- Fecha: 2026-06-10.
- URL: https://aws.amazon.com/blogs/aws/now-available-amazon-ec2-m9g-and-m9gd-instances-powered-by-new-aws-graviton5-processors/
- Verificado: 2026-09-29.
- Cita: "Today, M9g instances are generally available, alongside the new M9gd instances"
- Estado: **VERIFICADO**.
- Caveat: el preview se anunció el 2025-12-04 (re:Invent 2025): https://aws.amazon.com/about-aws/whats-new/2025/12/ec2-m9g-instances-graviton5-processors-preview/

#### 1.2 **"Hasta 25% mejor rendimiento de cómputo" que Graviton4**
- Fuente: AWS News Blog (1.1) y página de producto "Amazon EC2 M9g instances".
- Fecha: 2026-06-10 (blog); página de producto sin fecha.
- URL: https://aws.amazon.com/blogs/aws/now-available-amazon-ec2-m9g-and-m9gd-instances-powered-by-new-aws-graviton5-processors/ · https://aws.amazon.com/ec2/instance-types/m9g/
- Verificado: 2026-09-29.
- Cita (blog): "Graviton5 offers up to 25% better compute performance compared to Graviton4-based instances"
- Cita (producto): "M9g instances deliver up to 25% better compute performance, higher networking bandwidth, and more Amazon EC2 Elastic Block Store (Amazon EBS) bandwidth than previous generation AWS Graviton4-based M8g instances."
- Estado: **VERIFICADO**.
- Caveat: siempre "up to" (hasta); es claim del fabricante.

#### 1.3 **35% web, 35% inferencia ML, 30% bases de datos (vs M8g/Graviton4)**
- Fuente: AWS News Blog (1.1); página de producto M9g.
- Fecha: 2026-06-10.
- URL: las de 1.2.
- Verificado: 2026-09-29.
- Cita (blog): "up to 35% faster performance for web applications, up to 35% for machine learning inference, and up to 30% for databases"
- Cita (producto): "M9g instances are up to 30% faster for databases, and up to 35% faster for web applications and machine learning workloads compared to M8g instances."
- Estado: **VERIFICADO**.
- Caveat: los tres son "up to".

#### 1.4 **DDR5-8800, "la memoria más rápida de cualquier instancia de procesador en la nube"**
- Fuente: AWS News Blog (1.1); About Amazon, "AWS Graviton5 is now generally available, delivering purpose-built performance for the agentic AI era".
- Fecha: 2026-06-10 (ambas; la nota de About Amazon es del 2025-12-04, actualizada el 2026-06-10).
- URL: https://aws.amazon.com/blogs/aws/now-available-amazon-ec2-m9g-and-m9gd-instances-powered-by-new-aws-graviton5-processors/ · https://www.aboutamazon.com/news/aws/aws-graviton-5-cpu-amazon-ec2
- Verificado: 2026-09-29.
- Cita (blog): "DDR5-8800 memory, AWS Graviton5 instances deliver the fastest memory of any processor instances in the cloud, and 5 times more L3 cache"
- Cita (About Amazon): "DDR5-8800 (the fastest DDR5 in the cloud)"
- Estado: **VERIFICADO**.

#### 1.5 **L3 5 veces más grande; cada núcleo ve 2.6x más L3 que en Graviton4**
- Fuente: AWS News Blog (1.1); About Amazon (1.4); AWS Graviton Getting Started (GitHub, AWS).
- Fecha: 2026-06-10 (blog); 2025-12-04/2026-06-10 (About Amazon); repo sin fecha de página.
- URL: las de 1.4 · https://github.com/aws/aws-graviton-getting-started/blob/main/README.md
- Verificado: 2026-09-29.
- Cita (blog): "With 192 cores, a 5x larger L3 cache, up to 33% lower inter-core latency"
- Cita (About Amazon): "Each Graviton5 core has access to 2.6x more L3 cache than Graviton4"
- Cita (Getting Started, tabla): LLC "48MB per NUMA" (Graviton4: "36MB").
- Estado: **VERIFICADO**.
- Caveat: "5x" es por chip (192 núcleos); por núcleo la cifra es 2.6x. En una talla .4xlarge la frase correcta es la de 2.6x.

#### 1.6 **192 núcleos**
- Fuente: AWS News Blog (1.1); página "AWS Graviton Processor"; About Amazon (1.4).
- Fecha: 2026-06-10.
- URL: https://aws.amazon.com/ec2/graviton/ · las de 1.4.
- Verificado: 2026-09-29.
- Cita (Graviton): "Graviton5 features 192 cores, a 5x larger cache, and up to 33% lower inter-core latency."
- Cita (About Amazon): "192 cores in a single package"
- Estado: **VERIFICADO**.

#### 1.7 **Proceso de 3 nm**
- Fuente: About Amazon (1.4).
- Fecha: 2025-12-04, actualizada 2026-06-10.
- URL: https://www.aboutamazon.com/news/aws/aws-graviton-5-cpu-amazon-ec2
- Verificado: 2026-09-29.
- Cita: "Graviton5 adopts the latest 3nm technology"
- Estado: **VERIFICADO**.
- Caveat: no aparece en el blog de lanzamiento ni en la página de producto; citar About Amazon.

#### 1.8 **Neoverse V3 a 3.3 GHz**
- Fuente: AWS Graviton Getting Started (GitHub, org `aws`); `aws ec2 describe-instance-types`; AWS Pricing API.
- Fecha: repo sin fecha de página; API leída 2026-09-29.
- URL: https://github.com/aws/aws-graviton-getting-started/blob/main/README.md
- Verificado: 2026-09-29.
- Cita (Getting Started, tabla): Core "V3", Frequency "3300MHz", Cores "192", Memory "12x DDR5", Architecture "Armv9.2-a", Instance families "M9g/M9gd".
- API: `m9g.4xlarge` → `SustainedClockSpeedInGhz: 3.3`; Pricing API `clockSpeed: 3.3 GHz`.
- Estado: **MATIZ**.
- Caveat: ni el blog, ni la página de producto, ni About Amazon nombran Neoverse V3 ni 3.3 GHz. En slides, citar el repo oficial de AWS y la API, no "el anuncio".

#### 1.9 **Sexta generación del AWS Nitro System, con Nitro Isolation Engine**
- Fuente: AWS News Blog (1.1); página de producto M9g; About Amazon.
- Fecha: 2026-06-10.
- URL: las de 1.2 y 1.4.
- Verificado: 2026-09-29.
- Cita (blog): "Built on the sixth-generation AWS Nitro System" y "Nitro Isolation Engine...the first formally verified cloud hypervisor"
- Cita (producto): "AWS Graviton5 introduces Nitro Isolation Engine as an enhancement to the Nitro System, harnessing formal verification to provide mathematical certainty that customer workloads are isolated."
- Estado: **VERIFICADO**.

#### 1.10 **Regiones al lanzamiento: us-east-1, us-east-2, us-west-2, eu-central-1**
- Fuente: AWS News Blog (1.1).
- Fecha: 2026-06-10.
- URL: la de 1.1.
- Verificado: 2026-09-29.
- Cita: "M9g and M9gd instances are available in the US East (N. Virginia), US East (Ohio), US West (Oregon), and Europe (Frankfurt) Regions"
- Estado: **VERIFICADO** (a la fecha del lanzamiento; no se revisó la expansión posterior).

#### 1.11 **m9g.4xlarge: 16 vCPU (16 núcleos, 1 hilo), 64 GiB, red hasta 17 Gbps (base 8.5), EBS hasta 12 Gbps (base 6,000 Mbps)**
- Fuente: página de producto M9g; blog (1.1); docs "General purpose instances" (`gp.html`); `describe-instance-types`.
- Fecha: 2026-06-10 (blog); docs y API leídos 2026-09-29.
- URL: https://aws.amazon.com/ec2/instance-types/m9g/ · https://docs.aws.amazon.com/ec2/latest/instancetypes/gp.html
- Verificado: 2026-09-29.
- Cita (producto, tabla): "16 | 64 | EBS-Only | Up to 17 | Up to12"
- Cita (gp.html): red "8.5 / 17.0"; EBS "6000.00 / 12000.00" Mbps, "750.00 / 1500.00" MB/s, "24000.00 / 48000.00" IOPS.
- API: `DefaultCores 16`, `DefaultThreadsPerCore 1`, `NetworkPerformance "Up to 17 Gigabit"`, `BaselineBandwidthInMbps 6000`, `MaximumBandwidthInMbps 12000`.
- Estado: **VERIFICADO**.
- Caveat: 17 Gbps y 12 Gbps son ráfaga ("up to"); lo sostenido es 8.5 Gbps de red y 6,000 Mbps de EBS.

#### 1.12 **m9g.48xlarge: 192 vCPU, 768 GiB, 100 Gbps, 72 Gbps EBS**
- Fuente: página de producto M9g; blog (1.1).
- URL: https://aws.amazon.com/ec2/instance-types/m9g/
- Verificado: 2026-09-29.
- Cita (producto, tabla): "192 | 768 | EBS-Only | 100 | 72"
- Estado: **VERIFICADO**.

---

### 2. M8i (Intel)

#### 2.1 **Intel Xeon 6 a medida (Granite Rapids), turbo sostenido en todos los núcleos de 3.9 GHz**
- Fuente: página de producto "Amazon M8i instances"; AWS News Blog "New general-purpose Amazon EC2 M8i and M8i-flex instances are now available" (Channy Yun); `gp.html`; Pricing API.
- Fecha: 2025-08-28 (blog).
- URL: https://aws.amazon.com/ec2/instance-types/m8i/ · https://aws.amazon.com/blogs/aws/new-general-purpose-amazon-ec2-m8i-and-m8i-flex-instances-are-now-available/
- Verificado: 2026-09-29.
- Cita (producto): "custom Intel Xeon 6 processors with a sustained all-core turbo frequency of 3.9 GHz"
- Cita (blog): "custom Intel Xeon 6 processors available only on AWS with sustained all-core 3.9 GHz turbo frequency"
- Cita (gp.html): "Intel Xeon Granite Rapids"; Pricing API `physicalProcessor`: "Intel Xeon Scalable (Granite Rapids)".
- Estado: **VERIFICADO**.
- Caveat: la página de producto y el blog no dicen "Granite Rapids"; el nombre en clave sale de docs y de la Pricing API.

#### 2.2 **DDR5-7200, "2.5x más throughput de memoria" que la generación anterior**
- Fuente: página de producto M8i; blog (2.1).
- URL: las de 2.1.
- Verificado: 2026-09-29.
- Cita (producto): "DDR5 7200MT/s DIMMs, providing 2.5x higher memory throughput compared to previous generation instances"
- Cita (blog): "2.5 times more memory bandwidth compared to previous generation M7i and M7i-flex instances"
- Estado: **VERIFICADO**.
- Caveat: el blog no menciona DDR5-7200; solo la página de producto.

#### 2.3 **"20% más rápida que M7i en general"**
- Fuente: página de producto M8i; blog (2.1).
- URL: las de 2.1.
- Verificado: 2026-09-29.
- Cita (producto): "20% faster than M7i overall"
- Cita (blog): "up to 20 percent higher performance"
- Estado: **VERIFICADO**.
- Caveat: el blog dice "up to"; la página de producto dice "overall". Otros claims: "up to 15% better price-performance", NGINX "60%", PostgreSQL "up to 30% faster", deep learning "40%".

#### 2.4 **Lanzamiento: 28 de agosto de 2025**
- Fuente: AWS News Blog (2.1); What's New "New General Purpose Amazon EC2 M8i and M8i-flex instances".
- URL: https://aws.amazon.com/blogs/aws/new-general-purpose-amazon-ec2-m8i-and-m8i-flex-instances-are-now-available/ · https://aws.amazon.com/about-aws/whats-new/2025/08/amazon-ec2-m8i-and-m8i-flex-instances-generally-available/
- Verificado: 2026-09-29.
- Cita: "28 AUG 2025 by Channy Yun"; regiones iniciales "US East (N. Virginia), US East (Ohio), US West (Oregon), and Europe (Spain)".
- Estado: **VERIFICADO**.

#### 2.5 **m8i.4xlarge: 16 vCPU = 8 núcleos × 2 hilos (SMT), 64 GiB, red hasta 15 Gbps (base 7.5), EBS hasta 10 Gbps (base 5,000 Mbps)**
- Fuente: página de producto M8i; blog (2.1); `gp.html`; `describe-instance-types`.
- URL: https://aws.amazon.com/ec2/instance-types/m8i/ · https://docs.aws.amazon.com/ec2/latest/instancetypes/gp.html
- Verificado: 2026-09-29.
- Cita (producto/blog): vCPU "16", Memory "64", Network "Up to 15", EBS "Up to 10".
- Cita (gp.html): "m8i.4xlarge | 64.00 | Intel Xeon Granite Rapids | 16 | 8 | 2"; red "7.5 / 15.0"; EBS "5000.00 / 10000.00".
- API: `DefaultCores 8`, `DefaultThreadsPerCore 2`, `ValidThreadsPerCore [1, 2]`, `SustainedClockSpeedInGhz 3.9`.
- Estado: **VERIFICADO**.
- Caveat: la página de producto y el blog no mencionan SMT; el "8 núcleos × 2 hilos" sale de docs y de la API.

---

### 3. M8a (AMD)

#### 3.1 **AMD EPYC de 5ª generación (Turin), modelo EPYC 9R45**
- Fuente: página de producto "Amazon M8a instances"; AWS News Blog "New general-purpose Amazon EC2 M8a instances are now available" (Betty Zheng); `gp.html`; Pricing API.
- Fecha: 2025-10-08 (blog).
- URL: https://aws.amazon.com/ec2/instance-types/m8a/ · https://aws.amazon.com/blogs/aws/new-general-purpose-amazon-ec2-m8a-instances-are-now-available/
- Verificado: 2026-09-29.
- Cita (producto): "5th Generation AMD EPYC processors (formerly code named "Turin")"
- Cita (gp.html): "m8a.4xlarge | 64.00 | AMD EPYC 9R45 | 16 | 16 | 1"; Pricing API `physicalProcessor`: "AMD EPYC 9R45 Processor".
- Estado: **VERIFICADO**.

#### 3.2 **Frecuencia: 4.5 GHz**
- Fuente: página de producto M8a; blog (3.1); `describe-instance-types`; Pricing API.
- URL: las de 3.1.
- Verificado: 2026-09-29.
- Cita (producto): "maximum frequency of 4.5 GHz for M8a instances"
- API: `SustainedClockSpeedInGhz 4.5`; Pricing API `clockSpeed`: "Up to 4.5 GHz".
- Estado: **MATIZ**.
- Caveat: AWS lo llama "maximum frequency" y "Up to 4.5 GHz" en el texto; nosotros escribimos "4.5 GHz sostenidos". El único respaldo para "sostenido" es el nombre del campo de la API. En slide: "hasta 4.5 GHz".

#### 3.3 **Sin SMT: cada vCPU es un núcleo físico**
- Fuente: blog (3.1); página de producto M8a; API.
- URL: las de 3.1.
- Verificado: 2026-09-29.
- Cita (blog): "Each vCPU on an M8a instance corresponds to a physical CPU core, meaning there is no simultaneous multithreading (SMT)."
- Cita (producto): "Each vCPU on M8a and M8azn instances is a physical CPU core."
- API: `DefaultThreadsPerCore 1`, `ValidThreadsPerCore [1]`.
- Estado: **VERIFICADO**.

#### 3.4 **Tipo y velocidad de DRAM**
- Fuente buscada: página de producto M8a, blog (3.1), página "AWS and AMD" (https://aws.amazon.com/ec2/amd/), búsqueda en aws.amazon.com y docs.aws.amazon.com.
- Verificado: 2026-09-29.
- Lo único oficial: "M8a instances deliver 45% higher memory bandwidth compared to M7a instances" (producto) / "45% more memory bandwidth compared to M7a instances" (blog).
- Estado: **NO ENCONTRADO**.
- Caveat: AWS no publica la velocidad DDR5 de M8a. No poner "DDR5-6400" en una slide como dato de AWS; usar "45% más ancho de banda de memoria que M7a".

#### 3.5 **Lanzamiento: 8 de octubre de 2025; us-east-1 llegó después**
- Fuente: AWS News Blog (3.1); What's New "Amazon EC2 M8a Instances now available in additional regions".
- URL: https://aws.amazon.com/blogs/aws/new-general-purpose-amazon-ec2-m8a-instances-are-now-available/ · https://aws.amazon.com/about-aws/whats-new/2025/11/amazon-ec2-m8a-instances-additional-regions/
- Verificado: 2026-09-29.
- Cita (blog): "08 OCT 2025"; regiones iniciales "US East (Ohio) US West (Oregon) and Europe (Spain)".
- Estado: **VERIFICADO**.
- Caveat: N. Virginia no estaba en el lanzamiento; llegó en la expansión de noviembre de 2025.

#### 3.6 **Claims de AWS vs M7a: hasta 30% más rendimiento, hasta 19% mejor precio-rendimiento, 60% GroovyJVM, 39% Cassandra, 45% más ancho de banda de memoria**
- Fuente: blog (3.1); página de producto M8a.
- URL: las de 3.1.
- Verificado: 2026-09-29.
- Cita (blog): "up to 30% higher performance", "up to 19% better price performance", "up to 60% faster performance for GroovyJVM", "up to 39% faster performance for Cassandra"; Nitro: "sixth generation AWS Nitro Cards".
- Estado: **VERIFICADO**.

#### 3.7 **m8a.4xlarge: 16 vCPU (16 núcleos), 64 GiB, red hasta 15 Gbps (base 7.5), EBS hasta 10 Gbps (base 5,000 Mbps)**
- Fuente: blog (3.1); página de producto; `gp.html`; API.
- URL: https://aws.amazon.com/ec2/instance-types/m8a/ · https://docs.aws.amazon.com/ec2/latest/instancetypes/gp.html
- Verificado: 2026-09-29.
- Cita (blog): "16 | 64 GiB | Up to 15 Gbps | Up to 10 Gbps"
- Cita (gp.html): red "7.5 / 15.0"; EBS "5000.00 / 10000.00" Mbps, "20000.00 / 40000.00" IOPS.
- Estado: **VERIFICADO** (llena el hueco de EBS que teníamos).

---

### 4. `describe-instance-types` (us-east-1, 2026-09-29) + procesador de `gp.html`

Fuente: `aws ec2 describe-instance-types --region us-east-1` (API oficial, leída 2026-09-29) y https://docs.aws.amazon.com/ec2/latest/instancetypes/gp.html (columna Processor). La API no devuelve nombre de procesador, solo fabricante. Estado de toda la tabla: **VERIFICADO**.

| Tipo | vCPU | Núcleos | Hilos/núcleo (válidos) | Clock sostenido (API) | Fabricante | Procesador (gp.html) | Red (API) | Red base (Gbps) | EBS base / máx (Mbps) | Hypervisor |
|---|---|---|---|---|---|---|---|---|---|---|
| m9g.4xlarge | 16 | 16 | 1 ([1]) | 3.3 | AWS | AWS Graviton5 | Up to 17 Gigabit | 8.5 | 6,000 / 12,000 | nitro |
| m8i.4xlarge | 16 | 8 | 2 ([1,2]) | 3.9 | Intel | Intel Xeon Granite Rapids | Up to 15 Gigabit | 7.5 | 5,000 / 10,000 | nitro |
| m8a.4xlarge | 16 | 16 | 1 ([1]) | 4.5 | AMD | AMD EPYC 9R45 | Up to 15 Gigabit | 7.5 | 5,000 / 10,000 | nitro |
| m8g.4xlarge | 16 | 16 | 1 ([1]) | 2.8 | AWS | AWS Graviton4 Processor | Up to 15 Gigabit | 7.5 | 5,000 / 10,000 | nitro |
| m7g.4xlarge | 16 | 16 | 1 ([1]) | 2.6 | AWS | AWS Graviton3 Processor | Up to 15 Gigabit | 7.5 | 5,000 / 10,000 | nitro |
| m6g.4xlarge | 16 | 16 | 1 ([1]) | 2.5 | AWS | AWS Graviton2 Processor | Up to 10 Gigabit | 5.0 | 4,750 / 4,750 | nitro |
| m7i.4xlarge | 16 | 8 | 2 ([1,2]) | 3.2 | Intel | Intel Xeon Sapphire Rapids | Up to 12.5 Gigabit | 6.25 | 5,000 / 10,000 | nitro |
| m6i.4xlarge | 16 | 8 | 2 ([1,2]) | 3.5 | Intel | Intel Xeon Ice Lake | Up to 12.5 Gigabit | 6.25 | 5,000 / 10,000 | nitro |
| m5.4xlarge | 16 | 8 | 2 ([1,2]) | 3.1 | Intel | Intel Xeon Platinum 8175 | Up to 10 Gigabit | 5.0 | 4,750 / 4,750 | nitro |
| c8i.16xlarge | 64 | 32 | 2 ([1,2]) | 3.9 | Intel | (Pricing API: Intel Xeon Scalable (Granite Rapids)) | 30 Gigabit | 30.0 | 20,000 / 20,000 | nitro |
| m7g.large | 2 | 2 | 1 ([1]) | 2.6 | AWS | AWS Graviton3 Processor | Up to 12.5 Gigabit | 0.937 | 630 / 10,000 | nitro |
| t3.xlarge | 4 | 2 | 2 ([1,2]) | 2.5 | Intel | Intel Skylake P-8175 | Up to 5 Gigabit | 1.024 | 695 / 2,780 | nitro |
| t3.2xlarge | 8 | 4 | 2 ([1,2]) | 2.5 | Intel | Intel Skylake P-8175 | Up to 5 Gigabit | 2.048 | 695 / 2,780 | nitro |
| t2.xlarge | 4 | 4 | 1 (n/d) | 2.3 | Intel | Intel Broadwell E5-2686v4 | Moderate | 0.75 | n/d | xen |
| t2.2xlarge | 8 | 8 | 1 (n/d) | 2.3 | Intel | Intel Broadwell E5-2686v4 | Moderate | 1.0 | n/d | xen |

Caveats de la tabla:
- La Pricing API da otro clock para dos Graviton: m7g "2.5 GHz" (API EC2: 2.6) y m8g "2.7 GHz" (API EC2: 2.8). Getting Started dice Graviton3 "2600MHz", Graviton4 "2800MHz". Citar la API de EC2 o Getting Started, no la Pricing API.
- El clock de t3 en la API (2.5) no coincide con el de su página de producto ("up to 3.1 GHz" sostenido en todos los núcleos, 3.1 también en la Pricing API).
- t2 no expone `ValidThreadsPerCore` (no admite CPU options) ni EBS-optimized.

---

### 5. Procesador por generación (slide del arco)

| Familia | Redacción oficial del procesador | Fuente / URL | Lanzamiento (GA) | Estado |
|---|---|---|---|---|
| m5 | "1st or 2nd generation Intel Xeon Platinum 8000 series processor (Skylake-SP or Cascade Lake) with a sustained all core Turbo CPU clock speed of up to 3.1 GHz"; al lanzar: "Custom Intel® Xeon® Platinum 8175M series processors running at 2.5 GHz" | https://aws.amazon.com/ec2/instance-types/m5/ · https://aws.amazon.com/blogs/aws/m5-the-next-generation-of-general-purpose-ec2-instances/ | 2017-11-28 | VERIFICADO |
| m6i | "M6i instances are powered by 3rd Generation Intel Xeon Scalable processors (Ice Lake) with an all-core turbo frequency of 3.5 GHz" | https://aws.amazon.com/ec2/instance-types/m6i/ · https://aws.amazon.com/about-aws/whats-new/2021/08/amazon-ec2-m6i-instances/ | agosto 2021 | VERIFICADO |
| m7i | "custom 4th Generation Intel Xeon Scalable processors (code named Sapphire Rapids)" con "an all-core turbo frequency of 3.2 GHz (max core turbo frequency of 3.8 GHz)" | https://aws.amazon.com/ec2/instance-types/m7i/ · https://aws.amazon.com/about-aws/whats-new/2023/08/amazon-ec2-m7i-flex-m7i-instances/ | agosto 2023 | VERIFICADO |
| m8i | "custom Intel Xeon 6 processors with a sustained all-core turbo frequency of 3.9 GHz" (Granite Rapids según docs/Pricing API) | §2 | 2025-08-28 | VERIFICADO |
| m6g | "AWS Graviton2 Processors are based on 64-bit Arm Neoverse cores and custom silicon designed by AWS"; Getting Started: Neoverse N1, 2500MHz | https://aws.amazon.com/ec2/instance-types/m6g/ · https://aws.amazon.com/about-aws/whats-new/2020/05/amazon-ec2-m6g-instances-powered-by-aws-graviton2-processors-generally-available/ | GA mayo 2020 (preview en re:Invent 2019) | VERIFICADO |
| m7g | "AWS Graviton3 is the latest generation of AWS-designed Arm-based processors..."; Getting Started: Neoverse V1, 2600MHz | https://aws.amazon.com/ec2/instance-types/m7g/ · https://aws.amazon.com/about-aws/whats-new/2023/02/amazon-ec2-m7g-r7g-instances/ | febrero 2023 | VERIFICADO |
| m8g | "AWS Graviton4 processors deliver up to 30% better compute performance than Graviton3 processors."; Getting Started: Neoverse V2, 2800MHz | https://aws.amazon.com/ec2/instance-types/m8g/ · https://aws.amazon.com/about-aws/whats-new/2024/09/amazon-ec2-c8g-m8g-instances/ | septiembre 2024 | VERIFICADO |
| m9g | Graviton5, Neoverse V3, 3300MHz (Getting Started) | §1 | 2026-06-10 | VERIFICADO |
| m8a | "5th Generation AMD EPYC processors (formerly code named "Turin")", EPYC 9R45 | §3 | 2025-10-08 | VERIFICADO |

Caveats:
- m5 puede caer en Skylake-SP o Cascade Lake según la página de producto actual; `gp.html` y la Pricing API dicen "Intel Xeon Platinum 8175" (Skylake). Nuestra m5 del arco fue Skylake solo si así se leyó en el nodo.
- m7g: Graviton3 ya existía en C7g (2022); M7g es de febrero de 2023. En el arco M, poner 2023.

Otros procesadores que usa el decision guide:
- **t3**: "1st or 2nd generation Intel Xeon Platinum 8000 series processor (Skylake-SP or Cascade Lake) with a sustained all core Turbo CPU clock speed of up to 3.1 GHz" (https://aws.amazon.com/ec2/instance-types/t3/); `gp.html`: "Intel Skylake P-8175". **MATIZ** (puede ser Cascade Lake).
- **t2**: `gp.html`: "Intel Broadwell E5-2686v4" (t2.xlarge, t2.2xlarge). **VERIFICADO**.
- **m4**: https://docs.aws.amazon.com/ec2/latest/instancetypes/pg.html → m4.large a m4.10xlarge "Intel Xeon E5-2676v3" (Haswell); solo m4.16xlarge "Intel Xeon E5-2686v4". **VERIFICADO** (ver discrepancia 9).

---

### 6. Processor state control (C-states / P-states)

#### 6.1 **Graviton: frecuencia fija, el sistema operativo no controla C-states ni P-states**
- Fuente: Amazon EC2 User Guide, "Processor state control for Amazon EC2 Linux instances".
- Fecha: sin fecha visible en la página.
- URL: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/processor_state_control.html
- Verificado: 2026-09-29.
- Cita: "AWS Graviton processors have built-in power saving modes and operate at a fixed frequency. Therefore, they do not provide the ability for the operating system to control C-states and P-states."
- Estado: **VERIFICADO**.

#### 6.2 **m7i, m8i y m8a completas (y c8i) en la lista "C-states only"**
- Fuente y URL: las de 6.1.
- Verificado: 2026-09-29.
- Cita (encabezado): "C-states only — The following instance types provide the ability for an operating system to control C-states:"; General purpose incluye "`m7i.large` … ` m7i.4xlarge` … `m7i.48xlarge`", "`m8a.medium` … `m8a.4xlarge` … `m8a.48xlarge`", "`m8i.large` … `m8i.4xlarge` … `m8i.96xlarge`"; Compute optimized incluye "`c8i.large` … `c8i.16xlarge` … `c8i.96xlarge`".
- Cita (C-states y P-states): "Bare metal: All bare metal instances with Intel and AMD processors" (más algunas tallas grandes antiguas: m4.10xlarge, m4.16xlarge, c4.8xlarge, etc.).
- Estado: **VERIFICADO**.
- Caveat: m5 solo aparece en 12xlarge/24xlarge y m6i solo en 16xlarge/32xlarge; m5.4xlarge y m6i.4xlarge no tienen control de C-states. P-states en virtualizadas modernas: ninguna.

---

### 7. CPU options (SMT) y launch templates de EKS

#### 7.1 **Hilos por núcleo configurables; excluidas T2, C7a, M7a, R7a, Mac y Graviton**
- Fuente: Amazon EC2 User Guide, "CPU options for Amazon EC2 instances".
- URL: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instance-optimize-cpu.html
- Verificado: 2026-09-29.
- Cita: "you can specify the following CPU options during and after instance launch: … Threads per core: You can disable SMT by specifying a single thread per CPU core."
- Cita: "You can't modify the number of threads per core for T2, C7a, M7a, R7a, and Apple silicon Mac instances, and instances based on the AWS Graviton processor."
- Estado: **MATIZ**.
- Caveat: la doc ya dice "during and after instance launch"; nuestro texto dice "al lanzar". M8a no está en la lista de exclusión, pero su `ValidThreadsPerCore` es `[1]`: no hay SMT que apagar.

#### 7.2 **Sin cambio de precio al cambiar CPU options**
- Fuente y URL: las de 7.1.
- Verificado: 2026-09-29.
- Cita: "There is no additional charge for specifying CPU options. … For other EC2 instances, you're charged the same as instances that are launched with the default CPU options."
- Cita: "How we calculate the vCPUs consumed by an instance is not affected by changing its CPU options."
- Estado: **VERIFICADO**.
- Caveat: m8i con SMT apagado (8 vCPU visibles) cuesta lo mismo que con 16 vCPU. La excepción es Windows/SQL Server con licencia incluida.

#### 7.3 **EKS managed node groups: `CpuOptions` no está entre los campos prohibidos del launch template**
- Fuente: Amazon EKS User Guide, "Customize managed nodes with launch templates".
- URL: https://docs.aws.amazon.com/eks/latest/userguide/launch-templates.html
- Verificado: 2026-09-29.
- Cita (prohibidos en el launch template): "Subnet under Network interfaces", "IAM instance profile under Advanced details", "Shutdown behavior and Stop - Hibernate behavior".
- Cita (Bottlerocket): "Amazon EC2 user data in launch templates that are used with managed node groups must be in the MIME multi-part archive format for Amazon Linux AMIs and TOML format for Bottlerocket AMIs."
- Estado: **VERIFICADO** (por ausencia: la página no menciona CPU options).
- Caveat: la doc no dice que CPU options esté soportado; solo no lo prohíbe. Lo que lo prueba es el lab: el nodo x86-smtoff arrancó con 8 CPU y siblings `0` (results/profiler-gate.md).

---

### 8. Instancias burstable (t2/t3)

#### 8.1 **Baseline por vCPU: t3.large 30%, t3.xlarge 40%, t3.2xlarge 40%; t2.large 30%, t2.xlarge 22.5%, t2.2xlarge 17%**
- Fuente: Amazon EC2 User Guide, "Key concepts for burstable performance instances" (tabla de créditos).
- URL: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/burstable-credits-baseline-concepts.html
- Verificado: 2026-09-29.
- Cita (tabla): "t3.large | 36 | 864 | 2 | 30%", "t3.xlarge | 96 | 2304 | 4 | 40%", "t3.2xlarge | 192 | 4608 | 8 | 40%", "t2.large | 36 | 864 | 2 | 30%", "t2.xlarge | 54 | 1296 | 4 | 22.5%", "t2.2xlarge | 81.6 | 1958.4 | 8 | 17%"
- Cita (definición): "Baseline utilization is expressed as a percentage of vCPU utilization, which is calculated as follows: Baseline utilization % = (number of credits earned/number of vCPUs)/60 minutes."
- Estado: **VERIFICADO**.
- Caveat: T3 arranca en Unlimited por defecto y T2 en Standard ("Standard (default), Unlimited").

#### 8.2 **Modo Unlimited: créditos excedentes a $0.05 por vCPU-hora (Linux, T2/T3); $0.04 en T4g**
- Fuente: "Amazon EC2 On-Demand Pricing", sección T2/T3/T4g Unlimited Mode Pricing.
- URL: https://aws.amazon.com/ec2/pricing/on-demand/
- Verificado: 2026-09-29.
- Cita: Linux/RHEL/SLES "$0.05 per vCPU-Hour" (T2 y T3); T4g "$0.04 per vCPU-Hour"; Windows "$0.096 per vCPU-Hour"; "The CPU Credit pricing is the same for all instance sizes, for On-Demand, Spot, and Reserved Instances, and across all regions."
- Estado: **VERIFICADO**.
- Caveat: se cobra solo si el promedio de 24 h supera el baseline (burstable-credits-baseline-concepts: "If the average CPU usage over a 24-hour period exceeds the baseline, the instance is billed for the additional usage at a flat additional rate per vCPU-hour").

---

### 9. M5 (2017)

#### 9.1 **M5: 14% mejor precio/rendimiento que M4, por núcleo**
- Fuente: AWS News Blog, "M5 – The Next Generation of General-Purpose EC2 Instances" (Jeff Barr).
- Fecha: 2017-11-28.
- URL: https://aws.amazon.com/blogs/aws/m5-the-next-generation-of-general-purpose-ec2-instances/
- Verificado: 2026-09-29.
- Cita: "the M5 instances are designed for highly demanding workloads and will deliver 14% better price/performance than the M4 instances on a per-core basis"
- Cita (procesador al lanzar): "Custom Intel® Xeon® Platinum 8175M series processors running at 2.5 GHz"
- Estado: **VERIFICADO**.

---

### 10. Precios (us-east-1, Linux, Shared, on-demand) y Spot

#### 10.1 **On-demand, Pricing API, 2026-09-29**
- Fuente: AWS Price List API (`aws pricing get-products`, `AmazonEC2`, `US East (N. Virginia)`, Linux, `preInstalledSw=NA`, `tenancy=Shared`, `capacitystatus=Used`). `effectiveDate` de todas las tarifas: 2026-09-01.
- Verificado: 2026-09-29.
- Estado: **VERIFICADO** para las 12 filas de results/cost.md (ninguna cambió).

| Tipo | $/h hoy | results/cost.md | Estado |
|---|---|---|---|
| m9g.4xlarge | 0.78272 | 0.78272 | VERIFICADO |
| m8i.4xlarge | 0.84672 | 0.84672 | VERIFICADO |
| m8a.4xlarge | 0.97376 | 0.97376 | VERIFICADO |
| m8g.4xlarge | 0.71808 | 0.71808 | VERIFICADO |
| m7g.4xlarge | 0.6528 | 0.6528 | VERIFICADO |
| m6g.4xlarge | 0.616 | 0.616 | VERIFICADO |
| m7i.4xlarge | 0.8064 | 0.8064 | VERIFICADO |
| m6i.4xlarge | 0.768 | 0.768 | VERIFICADO |
| m5.4xlarge | 0.768 | 0.768 | VERIFICADO |
| c8i.16xlarge | 2.99872 | 2.99872 | VERIFICADO |
| m7g.large | 0.0816 | 0.0816 | VERIFICADO |
| t3.xlarge | 0.1664 | (no está) | VERIFICADO (nuevo) |
| t3.2xlarge | 0.3328 | (no está) | VERIFICADO (nuevo) |
| t2.xlarge | 0.1856 | (no está) | VERIFICADO (nuevo) |
| t2.2xlarge | 0.3712 | (no está) | VERIFICADO (nuevo) |

#### 10.2 **Control plane de EKS: $0.10 por clúster-hora en soporte estándar; $0.60 en soporte extendido**
- Fuente: "Amazon EKS pricing".
- URL: https://aws.amazon.com/eks/pricing/
- Verificado: 2026-09-29.
- Cita: "$0.10 per cluster per hour" (standard); "$0.60 per cluster per hour (Standard Kubernetes version support + $0.50 per cluster per hour)" (extended).
- Estado: **VERIFICADO** (igual que results/cost.md).

#### 10.3 **Spot us-east-1, Linux/UNIX, 2026-09-22 → 2026-09-30 01:00 UTC**
- Fuente: `aws ec2 describe-spot-price-history --region us-east-1 --product-descriptions Linux/UNIX --start-time 2026-09-22T00:00:00Z`.
- Verificado: 2026-09-29.
- Método: mediana sobre los registros de cambio de precio (no ponderada por tiempo), todas las AZ juntas; aparte, la mediana y el último valor de us-east-1a.

| Tipo | Mediana 7 d (todas las AZ) | Rango | us-east-1a mediana / último | Spot ÷ on-demand (mediana) | Spec 2026-09-03 | Estado |
|---|---|---|---|---|---|---|
| m9g.4xlarge | $0.3464 | 0.3097–0.3996 | $0.3540 / $0.3443 | 44% | $0.314 | **CAMBIÓ** ($0.314 → $0.346, +10%) |
| m8i.4xlarge | $0.3695 | 0.2865–0.4221 | $0.3653 / $0.3731 | 44% | $0.366 | **CAMBIÓ** (mínimo: $0.366 → $0.3695, +1%) |
| m8a.4xlarge | $0.3592 | 0.2686–0.4349 | $0.3934 / $0.3934 | 37% | — | VERIFICADO (nuevo) |
| m8g.4xlarge | $0.2927 | 0.2712–0.3417 | $0.2742 / $0.2899 | 41% | — | VERIFICADO (nuevo) |
| m5.4xlarge | $0.3302 | 0.2290–0.4017 | $0.3786 / $0.3425 | 43% | — | VERIFICADO (nuevo) |

Caveats:
- m9g no tiene precio Spot en us-east-1f (solo 1a–1d); las demás tienen 1a, 1b, 1c, 1d y 1f.
- La diferencia entre AZ es grande: m8i va de $0.29 (1f) a $0.40 (1d). Con una sola cifra, decir "mediana de la semana en us-east-1" y no "el precio Spot".
- Con Spot, m9g y m8i quedan a menos de 7% de distancia (0.346 vs 0.370); la ventaja on-demand de m9g (−7.6%) se mantiene más o menos igual. m8a en Spot sale más barata que m8i (0.359 vs 0.370) y el orden de precios on-demand se invierte.

---

### 11. EKS

#### 11.1 **Kubernetes 1.36 en EKS: en soporte estándar; lanzado en EKS el 2 de junio de 2026; soporte estándar hasta el 2 de agosto de 2027; extendido hasta el 2 de agosto de 2028**
- Fuente: Amazon EKS User Guide, "Understand the Kubernetes version lifecycle on EKS"; What's New "Amazon EKS and Amazon EKS Distro now supports Kubernetes version 1.36".
- URL: https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions.html · https://aws.amazon.com/about-aws/whats-new/2026/06/amazon-eks-distro-kubernetes-version-1-36/
- Verificado: 2026-09-29.
- Cita: "The following Kubernetes versions are currently available in Amazon EKS standard support: 1.36, 1.35, 1.34"
- Cita (calendario): "`1.36` | April 22, 2026 | June 2, 2026 | August 2, 2027 | August 2, 2028"
- Estado: **VERIFICADO**.
- Caveat: 1.36 es la versión más nueva en EKS a la fecha.

#### 11.2 **Bottlerocket en EKS: distribución Linux open source de AWS, hecha para contenedores; managed node groups y Karpenter; x86_64 y arm64**
- Fuente: Amazon EKS User Guide, "Create nodes with optimized Bottlerocket AMIs".
- URL: https://docs.aws.amazon.com/eks/latest/userguide/eks-optimized-ami-bottlerocket.html
- Verificado: 2026-09-29.
- Cita: "Bottlerocket is an open source Linux distribution that's sponsored and supported by AWS. Bottlerocket is purpose-built for hosting container workloads."
- Cita: "In addition to managed node groups and self-managed nodes, Bottlerocket is also supported by Karpenter."
- Cita: "Bottlerocket supports Amazon EC2 instances with `x86_64` and `arm64` processors."
- Estado: **VERIFICADO**.

---

### 12. Apéndice: nombres de instancia

#### 12.1 **Cómo se lee `c7gn.2xlarge`: serie `c`, generación `7`, opciones `gn` (g = Graviton, n = red y EBS), tamaño `2xlarge`; en el lab, `g` = Graviton, `a` = AMD, `i` = Intel**
- Fuente: Amazon EC2 Instance Types, "Amazon EC2 instance type naming conventions".
- Fecha: sin fecha visible en la página.
- URL: https://docs.aws.amazon.com/ec2/latest/instancetypes/instance-type-names.html
- Verificado: 2026-09-29 (HTML leído en crudo con curl).
- Cita: "Instance types are named based on their instance family and instance size. The first position of the instance family indicates the series, for example c. The second position indicates the generation, for example 7. The third position indicates the options, for example gn. After the period (.) is the instance size, such as small or 4xlarge, or metal for bare metal instances."
- Cita (Series): "C – Compute optimized", "M – General purpose"
- Cita (Options): "a – AMD processors", "g – AWS Graviton processors", "i – Intel processors", "n – Network and EBS optimized"
- Estado: **VERIFICADO**.
- Caveat: la doc no usa el ejemplo completo `c7gn.2xlarge` (solo c, 7, gn y 4xlarge); el "tipo = familia + tamaño" sale de la primera frase. En la slide 05 se tradujo "Compute optimized" como "optimizada para cómputo", "General purpose" como "uso general" y "Network and EBS optimized" como "optimizada para red y EBS". La doc también lista la serie "A – Powered by Arm-based AWS Graviton processors" (a1): no confundirla con la opción `a` (AMD).

---

### Discrepancias con nuestros documentos

1. **Spot de m9g (spec §9, línea de precios):** "m9g.4xlarge $0.783/h (Spot $0.314)" → hoy la mediana de 7 días es $0.346 (+10%). m8i: $0.366 → $0.3695 (sin cambio real). Actualizar la cifra de Spot y decir "mediana semanal, us-east-1".
2. **Fuente de precios (spec §9):** los precios on-demand de la spec se tomaron de instances.vantage.sh; los valores coinciden con la Pricing API oficial (m8i 0.84672, m9g 0.78272, m7i 0.8064, m8a 0.97376). En la slide citar la Pricing API o aws.amazon.com/ec2/pricing, no Vantage.
3. **EBS "10,000 vs 12,000 Mbps" (spec §9, facts-setup §1.1):** son máximos de ráfaga ("up to"). La base sostenida es 5,000 (m8i) vs 6,000 Mbps (m9g). Igual con la red: "up to" 15 vs 17 Gbps, base 7.5 vs 8.5 Gbps.
4. **m8a "4.5 GHz sostenidos" (spec línea 66, facts-setup §1.1):** AWS escribe "maximum frequency of 4.5 GHz" y la Pricing API "Up to 4.5 GHz". Solo el nombre del campo de la API (`SustainedClockSpeedInGhz`) respalda "sostenido". En la slide: "hasta 4.5 GHz".
5. **DRAM de m8a (facts-setup §1.1, "not recorded in repo"):** AWS no publica la velocidad DDR5 de M8a (NO ENCONTRADO). Lo citable es "45% más ancho de banda de memoria que M7a".
6. **EBS de m8a (facts-setup §1.1, "not recorded in repo"):** 5,000 Mbps base / 10,000 Mbps máx; red base 7.5 Gbps, máx 15.
7. **Neoverse V3 y 3.3 GHz (spec §9, facts-setup §1.1):** no están en el blog de lanzamiento ni en la página de producto. Salen de aws-graviton-getting-started (GitHub de AWS) y de la API. Citar esa fuente en la slide 4.
8. **CPU options "configurable al lanzar" (spec §9):** la doc hoy dice "during and after instance launch". El resto (exclusiones T2, C7a/M7a/R7a, Mac, Graviton; mismo precio) coincide. Agregar que en M8a no hay nada que apagar (`ValidThreadsPerCore [1]`).
9. **decision-guide, burstable: "t2 runs Broadwell E5-2686 v4 (as m4)":** t2.xlarge/2xlarge sí son Broadwell E5-2686v4, pero m4 (large a 10xlarge) es Haswell E5-2676v3; solo m4.16xlarge es E5-2686v4. El factor 0.91 de t2 usa el +14% por núcleo de M5 sobre M4 (Haswell), así que la base de t2 ≠ la de m4. Quitar "(as m4)" o marcar el factor como estimación con esa diferencia.
10. **decision-guide: "t3 runs the same Skylake 8175 as m5":** `gp.html` lo confirma (t3 "Intel Skylake P-8175", m5 "Intel Xeon Platinum 8175"), pero las páginas de producto de t3 y m5 dicen "Skylake-SP or Cascade Lake". MATIZ: la misma familia, no garantía de mismo silicio.
11. **decision-guide: "m6g (cheapest, 2019)":** M6g se anunció en preview en re:Invent 2019 y quedó GA en mayo de 2020. Poner 2020.
12. **decision-guide, per $ de t3/t2:** results/cost.md no tiene precios de t3/t2, aunque el decision guide calcula per $ con ellos. Valores de hoy: t3.xlarge 0.1664, t3.2xlarge 0.3328, t2.xlarge 0.1856, t2.2xlarge 0.3712. Si se agregan a cost.md, `captured` = 2026-09-29, Pricing API.
13. **Clock de Graviton en la Pricing API:** m7g "2.5 GHz" y m8g "2.7 GHz" vs 2.6 y 2.8 en la API de EC2 y en Getting Started. Si la slide del arco pone clocks, usar la API de EC2.
14. **m5 en el arco:** la página de producto admite Skylake-SP o Cascade Lake. Si la slide dice "Skylake", respaldarlo con lo leído en el nodo (lscpu) o con `gp.html` ("Intel Xeon Platinum 8175").
15. **Sin discrepancias** en: GA de M9g (2026-06-10), 25/35/35/30%, DDR5-8800 y "fastest memory", 5x L3, 192 núcleos, Nitro de sexta generación, regiones de lanzamiento, m9g.4xlarge 16/64, m8i (Xeon 6, 3.9 GHz, DDR5-7200, 2.5x, 20%, ago-2025, 16/64, SMT), m7i de 2023, lista "C-states only" (m7i/m8i/m8a/c8i completas), Graviton sin C/P-states, baselines burstable, +14% por núcleo de M5, los 12 precios de results/cost.md, EKS $0.10/h y 1.36 en soporte estándar.

---

## Parte 3. Terceros (publicaciones originales)


> Verificadas 2026-09-29 con fetch directo de la publicación original (curl, WebFetch, lector r.jina.ai o copia de web.archive.org cuando el sitio devolvía 403), nunca con memoria de entrenamiento.
> Formato: **dato citable** → fuente, fecha, URL, cita textual (idioma original), estado, caveat.
> Estados: VERIFICADO (la fuente dice eso), CAMBIÓ (la cifra cambió respecto de lo que teníamos), NO ENCONTRADO (no hay fuente o no se pudo leer), MATIZ (la fuente lo dice, pero con un alcance distinto al que usábamos).
> Nuestro lab, para comparar: EKS, nodos **.4xlarge (16 vCPU, 64 GiB)**, us-east-1, on-demand m9g $0.78272/h, m8a $0.97376/h, m8i $0.84672/h (`headline.md`).

---

### 1. Spare Cores: "AWS Graviton5 Benchmarks"

Fuente general: Spare Cores, *AWS Graviton5 Benchmarks*, Gergely Daroczi. Publicado 2026-06-12. https://sparecores.com/article/aws-graviton5-benchmarks · verificado 2026-09-29 (texto completo leído).
Método (del artículo): "running 500+ benchmark workloads on each"; todas las tallas medium→48xlarge y metal de m6g/m7g/m8g/m9g; **los gráficos y tablas del artículo usan 2xlarge (8 vCPU, 32 GiB)**: "For demo purposes, I'll refer to the large 2xlarge instance sizes in the charts below." El artículo no compara contra x86 (ni AMD ni Intel) y no menciona SO ni kernel.

#### 1.1 PassMark CPU Mark: m9g +40% sobre m8g
- **Dato citable:** en 2xlarge, PassMark CPU Mark m6g 5.22K → m7g 6.07K → m8g 7.68K → **m9g 10.87K** (+40% sobre m8g, ~2× sobre m6g).
- Cita: "The overall PassMark score shows that the performance has doubled since the m6g generation, and increased by 40% since the previous (m8g) gen." / "Benchmarking suites, such as PassMark, show the newest gen instance winning across the board with 16-50% performance improvement, even when comparing to the recent m8g.2xlarge"
- Otros subtests PassMark 2xlarge (m8g → m9g): Single Threaded 1.94K → 2.46K; Integer Maths 41.72K → 49.01K; Floating Point 48.48K → 61.26K; Compression 53.12K → 74.64K; Encryption 1.50K → 2.36K.
- Estado: **VERIFICADO**
- Caveat: 2xlarge, no 4xlarge. PassMark es un benchmark sintético de CPU, no una aplicación.

#### 1.2 SCore (stress-ng div16): +16.5% single-core, +17.5% multi-core
- **Dato citable:** en el mismo número de vCPU, m9g sube 16.5% en single-core y 17.5% en multi-core sobre m8g según la métrica SCore de Spare Cores.
- Cita: "The new generation instance is a massive winner when looking at both the single-core and multi-core "SCore" (basically a CPU-only stressing metric of div16 ops): 16.5% improvement in the single-core, and 17.5% boost over the multi-core score at the same number of vCPUs."
- Estado: **VERIFICADO**
- Caveat: operaciones enteras de división (div16); es el número más bajo del artículo. Sirve para decir "de CPU pura, ~17%; lo demás viene de memoria y caché".

#### 1.3 Memoria: latencia −37%, "30+ percent" sobre m8g, con una anomalía
- **Dato citable:** PassMark Memory Latency 48.88 (m8g) → 30.71 (m9g); Memory Mark 3.08K → 4.06K; el autor resume "30+ percent improvement over the m8g".
- Cita: "Note the massive reduction in the memory latency metric, which is well aligned with the AWS announcement. Overall, we measured 30+ percent improvement over the m8g."
- Cita de la anomalía: "The newest gen is the clear winner for all read, write, and mixed operations in terms of memory bandwidth at lower block sizes, but surprisingly underperforms previous generations when the block size reaches the L3 cache size, so the CPU is forced to interact with RAM. This might be valid due to the dual-NUMA design, or a methodology detail"
- Estado: **MATIZ**
- Caveat: con `bw_mem`, m9g **pierde** contra generaciones anteriores cuando el bloque supera la L3 (acceso a RAM). El autor no lo resolvió al publicar. No decir "DDR5-8800 = más ancho de banda medido en todos los casos" citando a Spare Cores.

#### 1.4 llama.cpp: "15+ tok/s" y "well over 30%"
- **Dato citable:** m9g sirvió Llama 7B con 20+ tok/s de prompt processing y 15+ tok/s de generación, "well over 30%" sobre m8g y a menudo 2-3× sobre m6g.
- Cita: "Although the above screenshot is on Gemma (a 2B parameter LLM), these instances managed to also load and serve the 7B Llama model as well, with 20+ tokens/sec for prompt processing, and 15+ tokens/sec for text generation -- well over 30% improvement compared to m8g, and oftentimes 2-3x speed boost compared to m6g."
- Estado: **MATIZ**
- Caveat: el "15+ tok/s" es **Llama 7B (Q4_K_M)** y no Gemma 2B. La talla implícita es la de los gráficos (2xlarge, 8 vCPU); el texto no lo dice explícitamente para el 7B. Es un stream único a baja concurrencia, no un servidor bajo carga como nuestro k6. Nuestro modelo es Llama 3.1 8B Q4_0 a 16 vCPU: las cifras absolutas no se comparan.

#### 1.5 Precio: m9g cuesta más por hora, pero rinde más por dólar
- **Dato citable:** en us-east-1, m9g.2xlarge ~39 ¢/h frente a 31-36 ¢/h de las generaciones previas, "overall resulting in higher "$Core"".
- Cita: "the ~39 US cents of the newest gen compares to the 31-36 US cents of the previous gens at much better performance, overall resulting in higher "$Core" (SCore divided by the price showing the amount of SCore you can buy with $1/hr), so higher performance at the unit price."
- Estado: **VERIFICADO**
- Caveat: $Core usa SCore (CPU sintético). En 4xlarge nuestros precios coinciden con los de Phoronix (m9g $0.78272 vs m8g $0.71808, +9%).

#### 1.6 Datos de Spare Cores en 4xlarge (API pública, misma talla que nuestro lab)
- **Dato citable:** en la API de Spare Cores, a la misma talla que nuestro lab, m9g.4xlarge supera a m8i.4xlarge en casi todo, pierde contra m8a.4xlarge en CPU pura y en prompt processing, y gana en generación de texto y ancho de banda de memoria.
- Fuente: Spare Cores Keeper API, `https://keeper.sparecores.net/server/aws/{m9g,m8g,m8a,m8i}.4xlarge/benchmarks` (JSON). Consultado 2026-09-29. Páginas humanas: https://sparecores.com/server/aws/m9g.4xlarge (y equivalentes).
- Kernels reportados: m9g 6.17.0-1019-aws (observado 2026-08-28), m8g 7.0.0-1011-aws (2026-08-29), m8a 6.14.0-1014-aws (2025-10-08), m8i 6.14.0-1011-aws (2025-08-28). **Corridas en fechas y kernels distintos.**

| benchmark (4xlarge) | m9g | m8g | m8a | m8i | m9g/m8g | m9g/m8a | m9g/m8i |
|---|---|---|---|---|---|---|---|
| Geekbench 6 multi | 19,580 | 15,800 | 21,870 | 13,260 | 1.24 | 0.90 | 1.48 |
| Geekbench 6 single | 2,334 | 1,867 | 2,835 | 2,118 | 1.25 | 0.82 | 1.10 |
| stress-ng div16, 16 núcleos | 32,100 | 27,290 | 60,200 | 17,240 | 1.18 | 0.53 | 1.86 |
| PassMark Memory Mark | 4,553 | 3,214 | 2,778 | 2,544 | 1.42 | 1.64 | 1.79 |
| llama.cpp Llama 7B Q4_K_M, generación 128 tok (tok/s) | 30.2 | 17.1 | 24.2 | 15.4 | 1.77 | 1.25 | 1.96 |
| llama.cpp Llama 7B Q4_K_M, prompt 128 tok (tok/s) | 45.2 | 31.2 | 112.4 | 123.9 | 1.45 | **0.40** | **0.37** |
| llama.cpp Gemma 2B Q4_K_M, generación 128 tok (tok/s) | 73.4 | 47.3 | 59.0 | 41.3 | 1.55 | 1.24 | 1.78 |
| workload profile "web" | 2.72 | 1.78 | 2.24 | 1.53 | 1.53 | 1.21 | 1.78 |
| workload profile "cache" | 2.47 | 1.52 | 2.39 | 1.59 | 1.62 | 1.03 | 1.55 |
| pgbench heavy read-only, pico (TPS) | 3,278 | 2,604 | sin dato | sin dato | 1.26 | n/a | n/a |

- Estado: **VERIFICADO** (datos leídos del API; los cocientes son cálculo nuestro).
- Caveat: PassMark CPU Mark y "Extended Instructions" usan binarios distintos por arquitectura; no los comparo entre ARM y x86 (por eso no están en la tabla). Los "workload profile" son índices compuestos de Spare Cores, no aplicaciones. No hay pgbench para m8a/m8i en 4xlarge, así que Spare Cores no sirve para contrastar nuestro resultado de PostgreSQL.

---

### 2. Phoronix: Graviton4 vs Graviton5 (+30% geomean)

- **Dato citable:** en m8g.4xlarge vs m9g.4xlarge, 140+ benchmarks, la media geométrica sube **30%**; con +9% de precio por hora.
- Fuente: Phoronix, *Graviton5 CPU Benchmarks: 30% Geo Mean Improvement Over Graviton4*, Michael Larabel. Publicado 2026-07-09. https://www.phoronix.com/review/aws-graviton5 (8 páginas; phoronix.com devolvió 403 a curl/WebFetch, leído vía web.archive.org y r.jina.ai el 2026-09-29).
- Cita (método): "The M8g Graviton4 and M9g Graviton5 benchmarking was done on Ubuntu 26.04 LTS with the Linux 7.0 kernel, GCC 15, and other defaults of that current Ubuntu LTS release. [...] this M8g and M9g testing was done with the "4xlarge" size providing 16 vCPUs/cores for both Graviton4 and Graviton5."
- Cita (precio): "The m9g.4xlarge was priced on-demand in Ohio art $0.78272 USD per hour. The m8g.4xlarge in the same region was priced at $0.71808 per hour on-demand. Or about a 9% premium opting for Graviton5 rather than Graviton4 at the 4xlarge size."
- Cita (resultado): "Maintaining the same 16 vCPU "4xlarge" count, there was 30% geo mean uplift from Graviton4 to Graviton5 across all of these independent benchmarks carried out using m8g.4xlarge to m9g.4xlarge."
- Sub-resultados citables: GROMACS "saw 20% faster performance going from Graviton4 to Graviton5"; nginx HTTPS "up to that 30% uplift"; PostgreSQL (pgbench SF 100, 500/800 clientes, read-only) "yet another database server showing off great performance benefits of using Graviton5 over Graviton4" (sin porcentaje en el texto); ClickHouse, CockroachDB, Pogocache y PyPerformance también ganan en m9g.
- Java/JVM: **no hay** pruebas Java (ni Renaissance, DaCapo o SPECjbb) en la lista de páginas: 1 intro, 2 xfr/libxsmm/MT-DGEMM/QuantLib/OpenFOAM, 3 JSON/OCUDU, 4 Botan/video/7-Zip, 5 compilación, 6 DSP/ClickHouse/Cockroach/Pogocache, 7 PostgreSQL/GROMACS/sysbench/ASTC, 8 AI/Python/Nginx.
- Estado: **VERIFICADO**
- Caveat: es la comparación más parecida a nuestro lab (misma talla 4xlarge, mismos precios). Es una VM sola sin Kubernetes, con compilación GCC 15 y sin JVM. Los valores por prueba están en gráficos (imágenes) y en OpenBenchmarking, que bloqueó el acceso con un captcha: **no pude leer los números por prueba**.

### 3. Phoronix: Graviton5 vs EPYC Turin vs Xeon 6 (m9g, m8a, m8i)

- **Dato citable:** en geomean de 120+ benchmarks, **m8a.4xlarge es 17% más rápido que m9g.4xlarge**, y **m9g es 19% más rápido que m8i.4xlarge**; m8a cuesta ~24% más por hora que m9g.
- Fuente: Phoronix, *Graviton5 Outperforming Intel Xeon Granite Rapids But Falls Short Of AMD EPYC Turin*, Michael Larabel. Publicado 2026-07-13. https://www.phoronix.com/review/graviton5-epyc-xeon (10 páginas; leído vía web.archive.org y r.jina.ai el 2026-09-29).
- Cita (instancias): "here are the numbers now with including m8a.4xlarge and m8i.4xlarge [...] AMD EPYC 9R45 SKU with a maximum frequency of 4.5GHz for M8a instances. Each vCPU with M8a is backed by a physical CPU core (no SMT). [...] So for the m8i.4xlarge it's made up of eight physical CPU cores plus the HT sibling." / "I benchmarked all four instance types while running Ubuntu 26.04 LTS with the Linux 7.0 kernel and GCC 15.2 compiler."
- Cita (geomean): "Graviton5 with the m9g.4xlarge instance was around 19% faster than the m8i.4xlarge instance type, although it's important to reiterate that with the Intel Xeon instance AWS opted for a combination of physical cores plus SMT/HT. Besides Graviton5 being 19% faster than Xeon 6 in this geo mean comparison, the hourly on-demand pricing was about 8% cheaper than the Granite Rapids instance." / "The m8a.4xlarge AMD EPYC Turin instance was delivering 17% faster performance than the Graviton5 instance of the same size. Though with the current on-demand pricing, the m8a.4xlarge instance is around 24% more per hour than Graviton5 with m9g.4xlarge, so there is still a pricing advantage to Graviton5 [...] Though for some of the workloads at least, the m8a.4xlarge instance was delivering both the best raw performance and performance-per-dollar."
- PostgreSQL: "The m8a.4xlarge was also delivering the best performance for the PostgreSQL database server performance." (pgbench SF 100, read-only, 500 y 800 clientes; el orden m9g vs m8i no está en el texto).
- CockroachDB: "Graviton5 was leading across the CockroachDB in-memory database benchmarks. Graviton5 benefits here from the DDR5-8800 memory."
- Memoria vs CPU: "The memory bandwidth intensive benchmarks do great with Graviton5 thanks to the DDR5-8800 memory." / "While in the pure CPU core benchmarks, AMD EPYC Turin with its Zen 5 cores typically deliver much better performance than the Neoverse-V3 cores powering Graviton5."
- nginx: "Lastly were some Nginx HTTPS web server benchmarks with the AMD EPYC Turin powered m8a.4xlarge leading the race in both raw performance and performance-per-dollar based on current on-demand instance hourly pricing."
- NCNN (inferencia CNN): m9g gana 9 de 10 modelos.
- Java/JVM: no hay pruebas Java.
- Estado: **VERIFICADO**
- Caveat: es la misma talla y los mismos precios que nuestro lab ($0.97376 / $0.84672 / $0.78272). En la página 1 hay una errata ("m8g.4xlarge powered by Graviton5", debe decir m9g). No leí la cifra geomean por dólar (OpenBenchmarking bloqueado); el texto solo dice que m8a gana perf/$ en "some of the workloads".

---

### 4. Honeycomb: m8g → m9g en producción

- **Dato citable:** en 60 días con ambas generaciones corriendo en paralelo (m8g.8xlarge vs m9g.8xlarge, mismo namespace de Kubernetes), cada servicio medido usó **11-26% menos CPU** para el mismo trabajo; P99 de ingest −28%; P99 del pipeline de métricas a la mitad; colas de sampling 44-73% más cortas a P95. "Nothing in the fleet regressed."
- Fuente: Honeycomb, *Graviton5 in Production at Honeycomb: Per-service Results From the m8g to m9g Migration*, Liz Fong-Jones. Publicado 2026-06-10. https://www.honeycomb.io/blog/graviton5-honeycomb-per-service-results-m8g-m9g-migration · verificado 2026-09-29.
- Cita (TL;DR): "Honeycomb migrated a portion of our production shared compute pool from m8g.8xlarge (AWS Graviton4) to m9g.8xlarge (AWS Graviton5). Over 60 days running both generations side by side, every measured service used 11-26% less CPU on Graviton5 for identical work. Ingest P99 latency dropped 28%, the metrics ingest pipeline P99 halved, and tail-based sampling queues ran 44-73% shorter at P95. Nothing in the fleet regressed."
- Por servicio (texto): beagle "AVG CPU drops 11% and P99 CPU drops 31%" (P99 CPU 94% → 65%); newf "AVG CPU drops 23%" (P99 142% → 114% del request); kelpie "26% lower AVG and P99 CPU"; métricas write-to-Kafka P99 880 µs → 440 µs. Resumen: "Compute-bound services see 16-22% lower CPU and 16-28% lower P99 latency on Graviton5 compared to Graviton4."
- El 36%: "We did such a pass on shepherd alone in the week before re:Invent. That's where the 36% per-core throughput number came from." (un solo servicio, shepherd, ajustado al límite; no es el promedio de la flota).
- Estado: **VERIFICADO** / **MATIZ** para el 36%.
- Caveat: la tabla completa por servicio es una imagen o un Canvas embebido y no pude extraerla como texto; solo cito lo que está en prosa. **El post no dice el lenguaje ni el runtime** de los servicios: no afirmar "Go" ni "Java" citándolo. Talla 8xlarge; A/B pasivo con la misma cantidad de pods ("a floor—not a ceiling").

#### 4.1 El 36% en la página de AWS (voz del cliente, publicada por el proveedor)
- Cita (página M9g): "Honeycomb achieved 36% better throughput per core on Graviton5 compared to Graviton4. We saw 28% lower latency and up to 26% less CPU utilization out of the box — and after optimizing CPU per task until latency matched across generations, we unlocked the full 36% throughput gain over 60 days of production ingest workloads." También ClickHouse: "Early benchmarking of Graviton5-based instances shows a 36% performance boost and 16% higher concurrency compared to Graviton4."
- Fuente: AWS, página de producto M9g, https://aws.amazon.com/ec2/instance-types/m9g/ y blog de lanzamiento https://aws.amazon.com/blogs/aws/now-available-amazon-ec2-m9g-and-m9gd-instances-powered-by-new-aws-graviton5-processors/ (verificado 2026-09-29).
- Estado: **VERIFICADO**
- Caveat: son testimonios de clientes en la página del proveedor, así que se presentan como tales y no como medición independiente.

---

### 5. RunsOn: runners M9g ~27% más rápidos en single-thread

- **Dato citable:** en m*.large (2 vCPU), PassMark single-thread m9g 2450 vs m8g 1929 (~27%) vs runner ARM64 hospedado por GitHub 1873 (~31%).
- Fuente: RunsOn, *M9g ARM64 runners: ~30% faster single-thread than Graviton4 or GitHub's runners*, Cyril Rohr. Publicado 2026-06-11. https://runs-on.com/blog/m9g-arm64-runners/ · verificado 2026-09-29.
- Cita: "on our CPU benchmark it is the fastest ARM64 runner we have measured: roughly 27% faster single-thread than the previous Graviton generation (m8g) and ~31% faster than GitHub's own hosted ARM64 runners."
- Estado: **MATIZ**
- Caveat: el título dice "~30%", pero la cifra contra m8g es **27%**. Es single-thread, talla large y PassMark.

---

### 6. Java específico en Graviton5 (SPECjbb, Renaissance, DaCapo, Spring, Quarkus)

- **Dato citable:** ninguno. No encontré ningún resultado Java/JVM publicado para m9g vs m8g, ni de AWS ni de terceros.
- Búsqueda (2026-09-29): "Graviton5 m9g Java benchmark SPECjbb/Renaissance/DaCapo/Spring Boot", "Graviton5 Java performance Corretto m9g vs m8g JVM". Phoronix (ambos artículos) no incluye pruebas Java. Spare Cores no tiene benchmarks JVM. AWS solo dice que M9g sirve para "large-scale Java applications" (sin cifra).
- Lo más cercano: Spare Cores 4xlarge (§1.6) "web" m9g/m8g 1.53×, Geekbench multi 1.24×; Phoronix geomean 1.30×; Honeycomb 11-26% menos CPU (runtime no declarado) y 36% por núcleo en un servicio ajustado.
- Estado: **NO ENCONTRADO**
- Caveat: nuestro ~2.0× m9g vs m8g en Spring REST/JDK 25 (arco Task 8, 1 corrida por familia, m8g repetido en 2 nodos) **no tiene respaldo externo**. Tampoco lo contradice nadie con Java, pero está bastante por encima de todo lo publicado para cargas generales (1.2-1.5×). En escena hay que decirlo como resultado de nuestra carga y no como propiedad del chip.

---

### 7. re:Invent 2025 CMP333: "Maximizing EC2 performance: a hands-on guide to instance optimization"

Fuente: AWS re:Invent 2025, code talk CMP333, Toby Buckley y Jeff Blake. Video oficial (canal AWS Events): https://www.youtube.com/watch?v=mSrDZuxWFtw (título confirmado por oEmbed 2026-09-29). Transcripción usada: dev.to/kazuya_dev, *AWS re:Invent 2025 - Maximizing EC2 Performance: A Hands-on Guide to Instance Optimization (CMP333)*, publicado 2025-12-05, https://dev.to/kazuya_dev/aws-reinvent-2025-maximizing-ec2-performance-a-hands-on-guide-to-instance-optimization-cmp333-338f. Aviso del recap: "This article is entirely auto-generated [...] there may be typos or inaccuracies." No hay slides públicas.
Marcas de tiempo: aproximadas (±1 min), tomadas de los enlaces de fotogramas del recap. Conviene confirmarlas en el video.

#### 7.1 Groovy/Tomcat: 4,000 → 4,750 → 7,000 (m8g) → 11,000 (código, en m7g)
- **Dato citable:** con SLO de p99 < 100 ms, la app Groovy en m7g rompía en ~4,000 rps; los flags de JVM la llevaron a 4,750 (~+20%); pasar a m8g con los mismos flags dio 7,000; quitar aspectos AOP del código dio 11,000 **en m7g**.
- Citas: "If we went past 4,000 requests per second [...] we went well past 100 milliseconds past 4,000 RPS." (~17:10) · "The final results show that we got almost 20 percent more throughput at 4750 requests per second." (~33:10) · "m8g is getting 7000 requests per second for the same code with the same optimizations [...] We got 60 to 70% more performance with 10% higher cost. That's a 60% price-performance benefit from going from m7g to m8g" (~37:50) · "We're up to 11,000 requests per second and still under our SLO of 100 milliseconds at 28 milliseconds. That's on 7G. So from 7G to 7G, we can increase performance by almost 3X just by rearranging parts of our code." (~43:30)
- Setup: "three node groups: one dedicated to our load generator, and we're using wrk2" · "Amazon Linux 2023. We put Corretto 21 on there [...] Tomcat [...] 8 gigabytes of heap and G1 GC". Flags: tiered compilation off, tamaño de code cache y THP.
- Estado: **MATIZ**
- Caveat: los 11,000 rps son en **m7g** y no se suman a m8g. Son "tres node groups", no "3 nodos". Es Corretto **21**, no 25. El pod del demo tenía 3 CPU en un nodo de 4 (tallas chicas).

#### 7.2 TLB misses −60%, IPC +12% (m7g, flags de JVM)
- Citas: "Instructions per cycle improved by 12% on average, so we delivered on what we said we could do." (~36:00) · "It actually tries to cache those translations, and we can see this went down by 60%, which is a big decrease." (~37:10; se refiere a misses de la caché de traducción de direcciones, es decir, el TLB). Además, de m7g a m8g con el mismo código: "we get 38% more IPC".
- Estado: **VERIFICADO** (transcripción automática)
- Caveat: la palabra "TLB" no aparece en la transcripción; dice "the cache that translates from virtual addresses to physical addresses". Conviene confirmar la cifra en el video.

#### 7.3 MongoDB 8 + YCSB: EBS gp2 4,000 rps con iowait 65-80% → NVMe 12,000
- Citas: "we took MongoDB 8 and said we want to run MongoDB 8 on 3 cores [...] persistent volume claim on GP2 [...] we come out with a score of only 4000 requests per second." (~47:10) · "We're in IO wait most of the time, 65 to 80% of the time." (~48:00) · "If we run YCSB with i3d, we see a 3X performance increase. We're up to 12,000 requests per second" (~50:50). Setup: "The two node groups are M7G extra large and M7GD extra large, both running MongoDB."
- Estado: **MATIZ**
- Caveat: m7g.xlarge vs m7gd.xlarge (NVMe local). La transcripción automática dice "i3d" en la frase del resultado, así que hay que confirmar en el video qué dijo. Es un problema de disco y no de CPU; nuestro Mongo corre en caché, así que no es comparable.

---

### 8. Tendencias de la industria

#### 8.1 Cast AI: ARM ≈ 9% de los CPUs en Kubernetes, creciendo 3.5× más rápido que x86
- **Dato citable:** ARM es ~9% de todos los CPUs en clústeres Kubernetes analizados por Cast AI y creció 3.5× más rápido que x86 entre Q2 2024 y Q4 2025.
- Fuente: Cast AI, *2026 State of Kubernetes Optimization Report*. Nota de prensa 2026-04-21 (https://cast.ai/press-release/2026-state-of-kubernetes-optimization-report/); página del reporte (https://cast.ai/reports/kubernetes-optimization-report/, fechada 2026-06-17); blog *Graviton and ARM Nodes for Kubernetes*, Kunal Das, 2026-07-22 (https://cast.ai/blog/kubernetes-arm-graviton-nodes/). Verificado 2026-09-29.
- Cita (reporte): "ARM CPU nodes grew at a rate 3.5 times that of x86 between Q2 2024 and Q4 2025." / "It now accounts for 9% of the total CPU fleet, up from a near-negligible share just a year ago."
- Estado: **VERIFICADO** (misma cifra; la edición 2026 es la vigente y no encontré otra más nueva).
- Caveat: la muestra son los clientes de Cast AI ("tens of thousands of Kubernetes workloads"), no el mercado entero. "3.5× más rápido" es tasa de crecimiento relativa, no participación.

#### 8.2 "Arm: hasta 65% mejor precio-rendimiento"
- **Dato citable:** Arm (no AWS) afirma "Up to 65% better price performance" para instancias Arm en la nube.
- Fuente: Arm, página *Arm Cloud Migration Program*, https://www.arm.com/markets/cloud-ai/arm-cloud-migration · verificado 2026-09-29.
- Cita: "Up to 65% better price performance*" / "* Representative performance of various workloads measured on Arm-based platforms with major cloud providers including Amazon Web Services, Google Cloud, and Microsoft Azure."
- Estado: **MATIZ**
- Caveat: es marketing del proveedor, con una nota al pie sin metodología. La página de Arm específica de AWS (https://www.arm.com/markets/cloud-ai/cloud-computing/aws) dice "**Up to 40%** Better Price-Performance", y Cast AI repite que AWS cita "up to 40%". Para Graviton, la cifra propia del proveedor es 40%, no 65%.

#### 8.3 Datadog: participación de Arm en instancias cloud
- **Dato citable:** según Datadog, la proporción de instancias cloud en Arm pasó de 9% a 15% en dos años, y la de funciones Lambda de 9% a 19%.
- Fuente: Datadog, *State of Containers and Serverless* (edición 2025), https://www.datadoghq.com/state-of-containers-and-serverless/ ; blog de hallazgos 2025-11-06, https://www.datadoghq.com/blog/containers-and-serverless-2025-study-learnings/. Verificado 2026-09-29.
- Cita: "Our research shows that the share of AWS Lambda functions running on Arm—rather than x86—grew from 9% to 19% over the past 2 years. Arm-based cloud instances also showed a substantial increase, rising from 9% to 15%."
- Estado: **VERIFICADO**
- Caveat: es la edición 2025; no encontré una edición 2026. Mide instancias cloud (EC2, GCE, Azure) de clientes de Datadog, no CPUs dentro de Kubernetes. No lo encontré para CNCF: la encuesta anual de CNCF no publica participación de Arm.

---

### 9. AMD EPYC Turin (m8a) e Intel Xeon 6 (m8i) frente a Graviton5: contraste con nuestro lab

- Única comparación directa independiente encontrada: Phoronix §3 (misma talla y precios) y los datos del API de Spare Cores §1.6. No encontré nada de ServeTheHome sobre m9g/m8a/m8i en la nube.
- Estado: **VERIFICADO** (ver §3 y §1.6)
- Cruce con nuestros resultados en la sección "Cruce" al final.

---

### 10. JDK 25 y aarch64 (inside.java)

- **Dato citable:** JDK 25 trae mejoras puntuales para AArch64: intrínseco para `Unsafe::setMemory` (~2.5× en su microbenchmark) y ML-KEM/ML-DSA cuyo rendimiento "has doubled on AArch64 and Intel AVX-512" con intrínsecos nuevos, además de optimizar las actualizaciones de perfil del intérprete en AArch64. Shenandoah generacional pasa a ser una función de producto.
- Fuente: Inside.java, *Performance Improvements in JDK 25*, Claes Redestad y Per-Ake Minborg. Publicado 2025-10-20. https://inside.java/2025/10/20/jdk-25-performance-improvements/ · verificado 2026-09-29.
- Citas: "JDK-8354674 AArch64: Intrinsify Unsafe::setMemory [...] The supplied microbenchmark showcases a ~2.5x speed-up when writing chunks of data" / "In JDK 25, the performance of many of these new APIs has doubled on AArch64 and Intel AVX-512 platforms thanks to specialized intrinsics." / "A similar change was attempted on AArch64 but failed to show any benefit there." (sobre `Math.cbrt`) / "The generational mode of the Shenandoah garbage collector, introduced in JDK 24, has transitioned to a product feature in JDK 25."
- Estado: **MATIZ**
- Caveat: son microbenchmarks e intrínsecos puntuales, casi todos también para x86. **El artículo no dice que JDK 25 mejore Java en ARM más que en x86**, ni da una cifra general de throughput en aarch64.

#### 10.1 Arm: vectorización en JDK 21/25 vs JDK 17 en AArch64
- Fuente: Arm Community, *Vector-related improvements in JDK 21 and JDK 25 compared with JDK 17 on AArch64*, 2026-08-05. https://developer.arm.com/community/arm-community-blogs/b/tools-software-ides-blog/posts/vector-related-improvements-in-jdk-21-and-jdk-25-compared-with-jdk-17-on-aarch64
- Cita: "Compared with JDK 17, JDK 21 and JDK 25 enable HotSpot to generate more efficient AArch64 code through improved C2 auto-vectorization and new NEON- and SVE-accelerated intrinsics, often without requiring any application source changes."
- Estado: **VERIFICADO**
- Caveat: son microbenchmarks JMH (por ejemplo, compareTo de arrays hasta +530% en 512 elementos), no aplicaciones.

#### 10.2 "~3.5× de rendimiento ARM desde JDK 8" (recap §8)
- Estado: **NO ENCONTRADO**. No está en inside.java ni en el blog de Arm. Una búsqueda web con la frase exacta no dio fuente. Lo más cercano es la guía de AWS, que recomienda JDK 11+ (idealmente 17+) en Graviton, sin esa cifra.

---

### 11. KleidiAI en llama.cpp (Arm) y AMX en llama.cpp (Intel)

#### 11.1 KleidiAI: qué se afirma y dónde
- **Dato citable:** Arm afirma que KleidiAI acelera el time-to-first-token de Llama 3 en llama.cpp un **190%**, pero en **Cortex-X925 (móvil/cliente)**, no en Graviton. En Graviton, la cifra de Arm (2.5× en TTFT) es con **PyTorch**, no con llama.cpp.
- Fuente: Arm Newsroom, *Accelerating and Scaling AI Inference Everywhere with New Llama LLMs on Arm*, 2024-09-25. https://newsroom.arm.com/news/ai-inference-everywhere-with-new-llama-llms-on-arm
- Cita: "The Kleidi integration with PyTorch leads to a 2.5x faster time-to-first token on Arm-based AWS Graviton processors when running the Llama 3 LLM. Meanwhile at the edge, the KleidiAI libraries are accelerating the time-to-first token for Llama 3 using llama.cpp by 190 percent on the Arm Cortex-X925 CPU compared with the reference implementation."
- PR de integración en llama.cpp: ggml-org/llama.cpp #11390 *ggml-cpu: Add CPU backend support for KleidiAI library* (chaxu01, merge 2025-02-20), https://github.com/ggml-org/llama.cpp/pull/11390. No trae cifras de speedup. Cita: "The feature can be enabled with the build option GGML_CPU_KLEIDIAI."
- Estado: **MATIZ**
- Caveat: no encontré una cifra publicada de KleidiAI + llama.cpp **en Graviton**. KleidiAI apunta a matmul (prefill); nuestro propio intento (O-35) dio 105 vs 109 tok/s en decode.

#### 11.2 Los kernels Arm que la imagen oficial SÍ usa en Graviton
- **Dato citable:** los kernels GEMM/GEMV int4/int8 de Arm para AArch64 dieron 2.5× en evaluación de prompt y 2× en generación en Graviton3, y hoy se activan por defecto vía "runtime repack" de Q4_0.
- Fuente: ggml-org/llama.cpp PR #5780 *Arm AArch64: optimized GEMV and GEMM kernels for q4_0_q8_0, and q8_0_q8_0 quantization* (David Mansell, Dibakar Gope, Arm; merge 2024-07-10). https://github.com/ggml-org/llama.cpp/pull/5780
- Cita: "On AWS Graviton3 processors, these kernels resulted in a 2.5x improvement in prompt evaluation over the existing GEMM mmla kernels, as well as a 2x improvement in text generation over the default vec_dot kernel"
- Código de nuestra versión (llama.cpp b10775, `ggml/CMakeLists.txt:151-152`): `option(GGML_CPU_REPACK "ggml: use runtime weight conversion of Q4_0 to Q4_X_X" ON)` y `option(GGML_CPU_KLEIDIAI "ggml: use KleidiAI optimized kernels if applicable" OFF)`; `ggml/src/ggml-cpu/repack.cpp` elige `q4_0_4x8_q8_0` con NEON + MATMUL_INT8 (lo que reporta m9g).
- Estado: **VERIFICADO**
- Caveat: "sin KleidiAI" no significa "sin kernels optimizados para Arm". Nuestro modelo Q4_0 en m9g usa los kernels i8mm de Arm por repack. La asimetría real es AMX (Xeon) vs NEON/SVE/i8mm sin KleidiAI (Graviton).

#### 11.3 AMX en llama.cpp
- **Dato citable:** el PR original de Intel reporta ~2× en generación de texto (llama2-7B Q4_0) con AMX en un Xeon Max 9480: 21.3 → 42.3 tok/s.
- Fuente: ggml-org/llama.cpp PR #7707 *Add Intel Advanced Matrix Extensions (AMX) support to ggml* (mingfeima, abierto 2024-06-03; reemplazado por #8998, merge 2024-10-18). https://github.com/ggml-org/llama.cpp/pull/7707 · https://github.com/ggml-org/llama.cpp/pull/8998
- Cita: "results from llama2-7b-q4_0, about **2x speed up** for the text generation. Collected on Intel (R) Xeon (R) CPU Max 9480" (eval 21.32 → 42.30 tokens per second). También: "implement a fast path when batch dimension is 1 for gemv, when batch dimension is small vnni is usually faster than amx because amx has larger overhead."
- Phoronix, *The Massive AI Performance Benefit With AMX On Intel Xeon 6 "Granite Rapids"*, Michael Larabel (2× Xeon 6980P bare metal, Ubuntu 25.10, Linux 6.17; fecha no visible en la copia obtenida). https://www.phoronix.com/review/intel-xeon-6-granite-rapids-amx/4 — Cita: "For Llama.cpp too, Advanced Matrix Extensions (AMX) continued to prove to be a massive benefit for faster prompt processing with large language models like Qwen3."
- Estado: **VERIFICADO**
- Caveat: el 2× del PR es de 2024, en otro Xeon, y frente a los kernels AVX de entonces. Phoronix mide Q8_0 en bare metal de 256 núcleos y no publica porcentajes en texto (están en gráficos). AMX favorece sobre todo el **prompt processing**, lo que calza con Spare Cores 4xlarge: en prompt de Llama 7B, m8i 124 tok/s vs m9g 45 tok/s.

---

### 12. Contexto oficial AWS M9g (para la slide de la promesa)

- Cita (página M9g, 2026-09-29): "M9g instances deliver up to 25% better compute performance, higher networking bandwidth, and more Amazon EC2 Elastic Block Store (Amazon EBS) bandwidth than previous generation AWS Graviton4-based M8g instances. M9g instances are up to 30% faster for databases, and up to 35% faster for web applications and machine learning workloads compared to M8g instances."
- URL: https://aws.amazon.com/ec2/instance-types/m9g/
- Estado: **VERIFICADO**
- Caveat: son cifras del proveedor ("up to"). Phoronix (+30% geomean) y Spare Cores (+17% a +40% según prueba) quedan en ese rango.

---

### Cruce: Spare Cores y Phoronix frente a nuestros resultados

Todo en 4xlarge. Nuestro lab = `headline.md` (Task 7, 2 días × 3 corridas) y arco Task 8 (Java stock, 1 corrida por familia).

| clase | nuestro lab (raw) | terceros (raw) | ¿coincide? |
|---|---|---|---|
| m9g vs m8i, general | Go 1.82×, Java stock 1.74×, inference 2.2× | Phoronix geomean 1.19×; Spare Cores GB6 multi 1.48×, "web" 1.78× | Dirección sí; magnitud mayor en nuestro lab. m8i.4xlarge = 8 núcleos + SMT, igual que dice Phoronix |
| m9g vs m8a, general | Go 1.26×, Java ≈1.0× (empate), inference ~1.5× | Phoronix: m8a 17% **más rápido** en geomean; Spare Cores GB6 multi 0.90×, stress-ng 0.53×, "web" 1.21× | Compatible: m8a gana en CPU pura y m9g gana cuando pesa la memoria o la red. Nuestro Java empatado cae entre ambos |
| PostgreSQL | m8a ~1.8× m9g; m9g ≈ m8i | Phoronix: m8a el más rápido en pgbench read-only (sin cifra en texto) | **Coincide** en el ganador. La magnitud no se puede contrastar (OpenBenchmarking bloqueado; Spare Cores no tiene pgbench x86 en 4xlarge) |
| Inferencia llama.cpp (generación) | m9g > m8a > m8i (97 / 65 / 44 tok/s agregados) | Spare Cores Llama 7B tg128: 30.2 / 24.2 / 15.4 (mismo orden; m9g/m8i 1.96×, m9g/m8a 1.25×) | **Coincide** en el orden y en m9g/m8i. Nuestro m9g/m8a es mayor |
| Inferencia (prompt processing) | no se midió aparte | Spare Cores: m8a y m8i ~2.5× m9g (AMX/AVX-512) | Advertencia: con prompts largos o RAG, el ranking se invierte |
| MongoDB / memoria | m9g 1.26× m8i/m8a; m8a = m8i | Spare Cores Memory Mark m9g 1.64× m8a, 1.79× m8i; Phoronix: CockroachDB en memoria gana m9g "thanks to DDR5-8800" | Dirección coincide (nuestro Mongo no es CPU-bound en el knee) |
| Web/HTTP | no medido con nginx | Phoronix nginx HTTPS: m8a gana en raw **y** en perf/$ | Contradice un "m9g gana por $ en todo lo web" genérico |
| m9g vs m8g | Java 2.0× (arco, 2 nodos m8g) | Phoronix 1.30×; Spare Cores 1.18-1.53× (CPU/web), 1.77× Llama 7B tg; Honeycomb 11-26% menos CPU, 36% por núcleo en un servicio; RunsOn 1.27× single-thread | **Sin respaldo externo para 2×**. Lo más alto publicado es generación LLM (~1.8×) y "web" (~1.5×) |

---

### Discrepancias / cosas que NO decir en escena

1. **"Graviton5 es 2× Graviton4 en Java."** Solo lo medimos en una carga (Spring REST, JDK 25, arco con 1 corrida por familia). Nadie publicó Java en m9g, y todo lo general da 1.2-1.5×. Decir: "en nuestra carga 2×; en suites amplias ~30%; decide tu carga" (como ya dice `decision-guide.md`).
2. **"Spare Cores: Gemma 2B a 15+ tok/s."** El 15+ tok/s es **Llama 7B**, y en la talla de los gráficos (2xlarge), no 4xlarge. Tampoco decir que DDR5-8800 gana siempre en ancho de banda: Spare Cores vio a m9g perder con bloques mayores que la L3.
3. **"Honeycomb: 36% más throughput."** El 36% por núcleo es de **un solo servicio (shepherd) ajustado al límite**; el resultado de flota es 11-26% menos CPU. Tampoco decir el lenguaje de sus servicios: el post no lo dice.
4. **"RunsOn: 30% más rápido."** Contra m8g es **27%** single-thread (el ~30%/31% es contra el runner ARM de GitHub).
5. **CMP333 "4,000 → 4,750 → 7,000 → 11,000" como una escalera.** Los 11,000 rps son refactor de código **en m7g**, no sobre m8g; son "tres node groups", no "k8s de 3 nodos"; es Corretto 21. MongoDB fue m7g.xlarge vs m7gd.xlarge (confirmar en el video, porque la transcripción dice "i3d"). La cifra de TLB −60% está en la transcripción automática sin la palabra "TLB": verificar en el video (~37:10) antes de ponerla en una slide.
6. **"Arm promete hasta 65%" presentado como si fuera de AWS o de Graviton.** El 65% es de Arm (Cloud Migration Program, multi-nube, nota al pie sin método). Para Graviton, Arm y AWS dicen "up to 40%".
7. **"~3.5× de rendimiento ARM desde JDK 8"** (recap §8): no encontré fuente. No decirlo.
8. **"JDK 25 cambia la respuesta en ARM"** citando inside.java: el artículo lista intrínsecos puntuales, casi todos también para AVX-512; no hay una ganancia general específica de ARM.
9. **"La imagen oficial no tiene optimizaciones Arm."** Sí las tiene: el repack Q4_0 con kernels i8mm de Arm está activo por defecto (b10775). Lo que falta es KleidiAI, y Arm no publicó una cifra de KleidiAI + llama.cpp en Graviton (su 190% es Cortex-X925; su 2.5× en Graviton es PyTorch).
10. **"m9g gana por dólar en web."** Phoronix midió nginx HTTPS con m8a ganando en raw y en perf/$ a la misma talla y los mismos precios. Nuestro "5 de 6 clases" es para nuestras cargas.
11. **"Primera evidencia pública de inferencia en Graviton5"** (recap viejo): falso desde el 2026-06-12 (Spare Cores). Ya estaba marcado en `facts-talk-scope.md`.
12. **Cast AI "9% del mercado".** Es 9% de los CPUs en clústeres de clientes de Cast AI, no del mercado; y "3.5× más rápido" es una tasa de crecimiento.

---

## Parte 4. Software, documentación y versiones


> Verificadas 2026-09-29 contra fuentes oficiales descargadas ese día (GitHub releases/tags vía `gh api`, raw de repos oficiales en el tag correspondiente, Docker Hub / GHCR registry API, docs de proveedores). Nada sale de memoria de entrenamiento.
> Formato: **dato citable** → fuente, fecha, URL, verificado 2026-09-29, cita textual (idioma original), estado, caveat.
> Estados: **VERIFICADO** (coincide) · **CAMBIÓ** (la fuente dice otra cosa hoy o hay versión más nueva que importa) · **MATIZ** (correcto con una condición que hay que decir) · **NO ENCONTRADO** (no hay fuente oficial pública que lo respalde).
> Las fechas de GitHub están en UTC; algunas figuran como 2026-09-30 UTC aunque en Perú todavía sea 29.

---

### A. Versiones

#### A.1 Plataforma

- **EKS Kubernetes 1.36**: en standard support hasta el 2027-08-02; es la versión más nueva que ofrece EKS hoy.
  - Pinneado: `infra/variables.tf:47` (`default = "1.36"`). Observado: kubelet `v1.36.2-eks-bca9cf6` (`results/2026-09-24/inventory/nodes-all.json:229`).
  - Fuente: Amazon EKS User Guide, "Understand the Kubernetes version lifecycle on EKS". https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions.html · verificado 2026-09-29.
  - Cita: "| `1.36` | April 22, 2026 | June 2, 2026 | August 2, 2027 | August 2, 2028 |" y "The following Kubernetes versions are currently available in Amazon EKS standard support: `1.36` `1.35` `1.34`".
  - Estado: **VERIFICADO**.
  - Caveat: upstream ya publicó 1.37 (v1.37.0 2026-08-26, v1.37.1 2026-09-23; https://github.com/kubernetes/kubernetes/releases) y Bottlerocket 1.66.0 ya trae variantes `aws-k8s-1.37`, pero EKS todavía no lista 1.37. Si en Q&A preguntan "¿por qué no 1.37?", la respuesta es que EKS no la ofrece.

- **Bottlerocket 1.64.0 (09-04) y 1.66.0 (09-24)**: 1.66.0 es la última versión.
  - Pinneado: no se pinnea. AMI "latest" vía SSM al hacer apply (`infra/main.tf:74-94`, gate de versión >= 1.64.0). Observado: `results/profiler-gate.md:3` (1.64.0) y `results/2026-09-24/inventory/nodes-all.json:232` ("Bottlerocket OS 1.66.0 (aws-k8s-1.36)").
  - Fuente: CHANGELOG oficial y GitHub releases. https://github.com/bottlerocket-os/bottlerocket/blob/develop/CHANGELOG.md · https://github.com/bottlerocket-os/bottlerocket/releases · verificado 2026-09-29.
  - Cita: "# v1.66.0 (2026-09-18)" · "# v1.65.0 (2026-09-04)" · "# v1.64.0 (2026-07-27) … Add support for static and transparent hugepages". Release en GitHub: v1.64.0 2026-07-29, v1.65.0 2026-09-09, v1.66.0 2026-09-22.
  - Estado: **VERIFICADO**.
  - Caveat: los días de Task 7 (d1/d2/d3) pudieron correr con 1.65.0 o con 1.66.0; `cluster.json` no lo registra (facts, pregunta abierta 7). La documentación en bottlerocket.dev llega solo hasta `1.65.x`: `/en/os/1.66.x/` devuelve 404.

- **Kernel 6.18.48**: la serie 6.18 es longterm y la última es 6.18.54.
  - Observado: `results/2026-09-24/inventory/nodes-all.json:227` (6.18.48). El 09-04 fue 6.18.38.
  - Fuente: kernel.org releases.json. https://www.kernel.org/releases.json · https://www.kernel.org/category/releases.html · verificado 2026-09-29.
  - Cita: `longterm 6.18.54 iseol=False released 2026-09-25`. La tabla de longterm lista "6.18 … 2025-11-30" como fecha de primera versión.
  - Estado: **VERIFICADO** (la serie tiene soporte). Bottlerocket: "All non-FIPS k8s-1.36 variants will use `kernel-6.18`" (CHANGELOG).
  - Caveat: 6.18.48 está 6 parches por detrás del upstream, algo normal en una distro.

- **terraform-aws-modules/eks `~> 21.25`, resuelto a 21.25.0**: hoy la última es v21.26.0.
  - Pinneado: `infra/main.tf:222`, `infra/karpenter.tf:7`. Resuelto: `infra/.terraform/modules/modules.json`.
  - Fuente: GitHub releases. https://github.com/terraform-aws-modules/terraform-aws-eks/releases · verificado 2026-09-29.
  - Cita (API): `v21.25.0 2026-08-14T20:49:44Z` · `v21.25.1 2026-09-18` · `v21.25.2 2026-09-22` · `v21.25.3 2026-09-22` · `v21.26.0 2026-09-23`.
  - Estado: **CAMBIÓ** (hay 4 releases nuevas).
  - Caveat: `.terraform.lock.hcl` no fija las versiones de los módulos, solo las de los providers. Con `~> 21.25`, un `terraform init` en un checkout limpio resuelve hoy a **21.26.0**, no a 21.25.0. Para que el lab sea reproducible hay que fijar `version = "21.25.0"`.

- **hashicorp/aws `~> 6.63` (lock 6.63.0)**: la última es v6.66.0.
  - Pinneado: `infra/versions.tf:34`, `infra/.terraform.lock.hcl:4-5`.
  - Fuente: https://github.com/hashicorp/terraform-provider-aws/releases · verificado 2026-09-29.
  - Cita (API): `v6.63.0 2026-09-03` · `v6.64.0 2026-09-09` · `v6.65.0 2026-09-16` · `v6.66.0 2026-09-21`.
  - Estado: **VERIFICADO** (el lock fija 6.63.0, así que el lab es reproducible).
  - Caveat: el spec (líneas 58 y 190) todavía dice `~> 6.53`. Ver Discrepancias.

- **Karpenter 1.14.1 (chart)**: sigue siendo la última versión y es compatible con Kubernetes 1.36.
  - Pinneado: `manifests/base/README.md:42-43`, `manifests/base/karpenter-values.yaml:8-9`.
  - Fuente: https://github.com/aws/karpenter-provider-aws/releases · matriz de compatibilidad v1.14: https://github.com/aws/karpenter-provider-aws/blob/main/website/content/en/v1.14/upgrading/compatibility.md · verificado 2026-09-29.
  - Cita: `v1.14.1 2026-08-21T22:39:31Z` (provider-aws), `v1.14.1 2026-08-21T22:35:25Z` (kubernetes-sigs/karpenter). Matriz: "| Kubernetes | … | 1.36 |" / "| karpenter | … | \>= 1.13 |".
  - Estado: **VERIFICADO**.

#### A.2 Observabilidad y herramientas de medición

- **Pyroscope: chart 2.2.1 con appVersion 2.2.1**: hoy hay chart 2.3.1 con app 2.3.1 y un parche 2.2.2 con CVEs corregidos.
  - Pinneado: `manifests/base/pyroscope-values.yaml:3-8`, `manifests/base/README.md:23-24`, `README.md:17`.
  - Fuente: índice oficial de Helm de Grafana, https://grafana.github.io/helm-charts/index.yaml · releases, https://github.com/grafana/pyroscope/releases · verificado 2026-09-29.
  - Cita (index.yaml): `version: 2.3.1 appVersion: 2.3.1 created: "2026-09-08T16:50:33Z"` · `version: 2.2.1 appVersion: 2.2.1 created: "2026-08-09T00:54:18Z"`. Releases: `v2.3.1 2026-09-08` · `v2.2.2 2026-09-08` · `v2.3.0 2026-08-24` · `v2.2.1 2026-08-06`. Notas de v2.2.2: "Updated `google.golang.org/grpc` to v1.83.1, addressing CVE-2026-84304".
  - Estado: **CAMBIÓ**.
  - Caveat: el comentario "no chart ships it yet" era cierto para v2.3.0 el 09-04. Hoy el chart 2.3.1 ya trae la app 2.3.1. Nunca hubo un chart 2.3.0. El spec (líneas 140 y 192) dice "Pyroscope 2.3.0", pero lo que corrió fue 2.2.1.

- **Imagen del profiler OTel eBPF `0.160.0`**: la última es 0.162.0. El profiler sigue en Alpha.
  - Pinneado: `manifests/base/ebpf-profiler.yaml:72`. El comentario en `:18-21` todavía dice 0.147.0.
  - Fuente: Docker Hub API (`otel/opentelemetry-collector-ebpf-profiler`), README del profiler y manifest de la distribución. https://hub.docker.com/r/otel/opentelemetry-collector-ebpf-profiler/tags · https://github.com/open-telemetry/opentelemetry-ebpf-profiler · https://github.com/open-telemetry/opentelemetry-collector-releases/blob/v0.160.0/distributions/otelcol-ebpf-profiler/manifest.yaml · verificado 2026-09-29.
  - Cita: tag `0.160.0` last_updated `2026-09-02T22:47:30Z`, arquitecturas `['amd64','arm64']`. Tag `0.162.0` del 2026-09-29. El manifest de 0.160.0 trae `go.opentelemetry.io/ebpf-profiler v0.0.202633`. README: "Implements the [Alpha OTel Profiles signal]" y "The agent comes with a functional but work-in-progress / evolving implementation of the recently released Alpha OTel Profiles signal."
  - Estado: **VERIFICADO** (0.160.0 existe y es multi-arch; sigue en Alpha).
  - Caveat: la doc de Grafana todavía muestra `image: otel/opentelemetry-collector-ebpf-profiler:0.147.0`, que no arranca en kernel 6.18 (`results/profiler-gate.md:31`). Grafana agrega: "Protocol stability: The OpenTelemetry profiles signal is under active development. Breaking changes have occurred and may continue. … Symbolization: Function names may not resolve in flamegraphs for some programs. … This feature is suitable for development and testing. Evaluate carefully before production use." (https://grafana.com/docs/pyroscope/latest/configure-client/opentelemetry/ebpf-profiler/).

- **La especificación de OTel Profiles NO es estable**: está en Alpha y el proto en Development.
  - Fuente: https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/profiles/README.md · https://github.com/open-telemetry/opentelemetry-proto/blob/main/README.md · verificado 2026-09-29.
  - Cita: "# OpenTelemetry Profiles **Status**: [Alpha]" · "| OTLP | profiles/\*<br>collector/profiles/* | Development |".
  - Estado: **CAMBIÓ**. El spec, línea 140, dice "la especificación de la señal es estable desde 2025", y eso es falso.

- **APerf v1.2.3**: hoy existe v1.3.0, que amplía la cobertura de PMU.
  - Pinneado: `runner/capture.py:74`, `runner/README.md:25`.
  - Fuente: https://github.com/aws/aperf/releases · verificado 2026-09-29.
  - Cita: `v1.2.3 2026-06-08` · `v1.3.0 2026-09-05`. Notas de 1.3.0: "Extend default PMU config to cover processors of all EC2 instance types." · "Optimize system file read and reduce APerf's collection CPU usage by 10%."
  - Estado: **CAMBIÓ**.
  - Caveat: es relevante para la pregunta abierta 5 (cobertura de PMU en m8a). Si faltan métricas PMU de m8a o m9g en los reportes 1.2.3, la causa probable es esta.

- **k6 2.2.0**: hoy existe 2.3.0.
  - Pinneado: `runner/cell.py:35` (`grafana/k6:2.2.0`), `runner/README.md:49`.
  - Fuente: https://github.com/grafana/k6/releases · Docker Hub `grafana/k6` · verificado 2026-09-29.
  - Cita: `v2.2.0 2026-08-10T14:01:35Z` · `v2.3.0 2026-09-21T15:17:03Z`. Imagen `2.2.0` last_updated 2026-08-10.
  - Estado: **VERIFICADO** (existe; hay una versión más nueva, sin impacto en la medición).

- **metrics-server, aws-ebs-csi-driver y VPC CNI (add-ons de EKS, sin pin)**: las versiones observadas coinciden con las últimas de upstream.
  - Observado: `results/2026-09-24/inventory/addons/*.json`: metrics-server `v0.9.0-eksbuild.11`, aws-ebs-csi-driver `v1.66.0-eksbuild.1`, vpc-cni `v1.23.1-eksbuild.1`, coredns `v1.14.6-eksbuild.4`, kube-proxy `v1.36.0-eksbuild.25`, eks-pod-identity-agent `v1.4.0-eksbuild.2`. Configuración: `infra/main.tf:258-289`.
  - Fuente: https://github.com/kubernetes-sigs/metrics-server/releases (`v0.9.0 2026-07-13`) · https://github.com/kubernetes-sigs/aws-ebs-csi-driver/releases (`v1.66.0 2026-09-10`) · https://github.com/aws/amazon-vpc-cni-k8s/releases (`v1.23.1 2026-09-11`) · verificado 2026-09-29.
  - Estado: **MATIZ**.
  - Caveat: esto confirma que son las últimas de upstream. Cuál es el último `eksbuild` para 1.36 solo se ve con `aws eks describe-addon-versions`, y esta verificación no hizo llamadas a AWS. Las versiones de los días d1-d3 tampoco quedaron registradas.

#### A.3 Runtimes y workloads

- **JDK: Eclipse Temurin `25.0.4_7-jre-noble`**: la distribución es Eclipse Temurin (Adoptium), imagen oficial de Docker Hub. Existe una re-release de seguridad, 25.0.4.1+1.
  - Pinneado: `apps/java/Dockerfile:29`. Build: `maven:3.9.16-eclipse-temurin-25-noble` (`:9`).
  - Fuente: Adoptium API y GitHub releases. https://api.adoptium.net/v3/info/release_names?release_type=ga&version=[25,26) · https://github.com/adoptium/temurin25-binaries/releases · Docker Hub `library/eclipse-temurin` · verificado 2026-09-29.
  - Cita: `jdk-25.0.4+7 2026-07-27` · `jdk-25.0.4.1+1 2026-08-19`. Notas de 25.0.4.1: "Improve Resource Resolving", "Enhance HTTP Connections", "Enhance TLS server", "Improve font loading". Tag `25.0.4_7-jre-noble` last_updated 2026-09-18, arquitecturas amd64 y arm64 (entre otras). Adoptium: `most_recent_lts: 25`, `most_recent_feature_release: 27`.
  - Estado: **CAMBIÓ**.
  - Caveat: 25.0.4.1 corrige vulnerabilidades (TLS/HTTP) que no afectan la medición, pero el tag `25.0.4.1_1-jre-noble` ya existe. JDK 25 sigue siendo el LTS más reciente.

- **Spring PetClinic REST: commit `4cd8e1b0cd42` (pom 4.0.2, Spring Boot 4.1.1)**: no es el tag v4.0.2.
  - Pinneado: `apps/java/Dockerfile:3,10`, `apps/java/README.md:10-12`.
  - Fuente: GitHub API. https://github.com/spring-petclinic/spring-petclinic-rest · pom del commit: https://raw.githubusercontent.com/spring-petclinic/spring-petclinic-rest/4cd8e1b0cd42578e882247d8801f6be5d402f118/pom.xml · verificado 2026-09-29.
  - Cita: el tag `v4.0.2` es el commit `d8026bb5…` (release 2026-02-01). `4cd8e1b0cd42…` es el HEAD de master (2026-09-01) y está `ahead_by=62` respecto del tag. pom: `<version>4.0.2</version>`, `spring-boot-starter-parent` `<version>4.1.1</version>`. Spring Boot: `v4.1.1 2026-08-20` es la GA más reciente (`v4.2.0-M2` es milestone).
  - Estado: **MATIZ**. `apps/java/README.md` lo explica bien. La tabla de facts §7, que dice "(v4.0.2, Boot 4.1.1)", se puede leer como si fuera el tag.

- **Go 1.27.1**: es la versión estable más reciente.
  - Pinneado: `apps/go/Dockerfile:6`, `apps/ycsb/Dockerfile:10` (`golang:1.27.1`).
  - Fuente: https://go.dev/doc/devel/release · https://go.dev/dl/?mode=json · verificado 2026-09-29.
  - Cita: "go1.27.1 (released 2026-09-01)" · "go1.27.0 (released 2026-08-19)". JSON de estables: `go1.27.1`, `go1.26.8`.
  - Estado: **VERIFICADO**.

- **PostgreSQL 18.6**: es la última versión menor de 18, con soporte hasta 2030-11-14.
  - Pinneado: `postgres/base/statefulset.yaml:75` (`postgres:18.6`), `postgres/README.md:31`.
  - Fuente: https://www.postgresql.org/versions.json · verificado 2026-09-29.
  - Cita: `{'current': True, 'eolDate': '2030-11-14', 'firstRelDate': '2025-09-25', 'latestMinor': '6', 'major': '18', 'relDate': '2026-08-13', 'supported': True}`. Imagen `postgres:18.6` last_updated 2026-09-24.
  - Estado: **VERIFICADO**.

- **MongoDB 8.0.32**: es la última versión 8.0.x. La serie 8.0 tiene soporte hasta 2029-10-31. MongoDB 9.0 salió en septiembre de 2026.
  - Pinneado: `mongo/base/statefulset.yaml:67` (`mongo:8.0.32`).
  - Fuente: release notes, https://www.mongodb.com/docs/manual/release-notes/8.0/ · lifecycle, https://www.mongodb.com/legal/support-policy/lifecycles · verificado 2026-09-29.
  - Cita: "### 8.0.32 - Sept 11, 2026". Lifecycle: "MongoDB 8.0 | October 2024 | October 31, 2029" · "MongoDB 9.0 | September 2026 | October 31, 2031" · "MongoDB 8.3 | May 2026 | October 31, 2029".
  - Estado: **VERIFICADO**.
  - Caveat: el manual "current" ya es 9.0. En Q&A pueden preguntar "¿por qué no 9.0?". La respuesta es que 8.0 es la versión que usa CMP333 y la que cambió la recomendación de THP.

- **go-ycsb v1.0.3 = commit `f030f9942393`**: es la última versión.
  - Pinneado: `apps/ycsb/Dockerfile:3,12`.
  - Fuente: https://github.com/pingcap/go-ycsb/releases · verificado 2026-09-29.
  - Cita: `v1.0.3 2025-12-31T05:50:57Z`. El tag resuelve a `f030f9942393a8febbf4365c2d582711723159f5`.
  - Estado: **VERIFICADO**.

- **llama.cpp `server-b10775`**: la imagen oficial es multi-arch (amd64/arm64/s390x). El tag b10775 es del 2026-09-03 y hoy la rama va por b11269.
  - Pinneado: `manifests/workloads/inference/base/deployment.yaml:3` (y la imagen en el mismo archivo); build propio `apps/llama/build-kleidiai.sh:16-17`; `results/images.json:15-18`.
  - Fuente: GitHub release `b10775` y manifest index en GHCR. https://github.com/ggml-org/llama.cpp/releases/tag/b10775 · `ghcr.io/v2/ggml-org/llama.cpp/manifests/server-b10775` · verificado 2026-09-29.
  - Cita: `b10775 2026-09-03T02:16:38Z`. Index OCI: `[{'architecture': 'amd64'}, {'architecture': 'arm64'}, {'architecture': 's390x'}]`.
  - Estado: **VERIFICADO**.
  - Caveat: llama.cpp publica varios builds por día. Estar ~500 builds atrás es normal para un lab pinneado.

- **Modelo `Llama-3.1-8B-Instruct-Q4_0.gguf`**: viene de `unsloth/Llama-3.1-8B-Instruct-GGUF` en Hugging Face, con licencia Llama 3.1 Community License. El sha256 coincide.
  - Pinneado: `manifests/workloads/inference/base/deployment.yaml:30, 66-71`.
  - Fuente: HF API, https://huggingface.co/api/models/unsloth/Llama-3.1-8B-Instruct-GGUF · headers del archivo · licencia, https://github.com/meta-llama/llama-models/blob/main/models/llama3_1/LICENSE · verificado 2026-09-29.
  - Cita: HF `license: llama3.1`, `base_model:meta-llama/Llama-3.1-8B-Instruct`, `gated: False`. Headers: `x-linked-size: 4675896704` y `x-linked-etag: "88e2c6002459f892d77c7e5e219868ef08a57c4e92354c7271aaf64f47ab0eaa"`. Licencia: "Llama 3.1 Version Release Date: July 23, 2024" · "prominently display “Built with Llama” on a related website, user interface, blogpost, about page, or product documentation" · el umbral comercial es "greater than 700 million monthly active users".
  - Estado: **VERIFICADO**.
  - Caveat: unsloth es una re-cuantización de terceros; el modelo original de Meta (`meta-llama/…`) es gated. Si se distribuyen resultados o slides que usan el modelo, conviene poner "Built with Llama" en la slide de inference o en el README.

- **iperf3 3.20 (Alpine 3.24 `3.20-r0`)**: upstream publicó 3.22 hoy, con CVEs.
  - Pinneado: `apps/iperf3/Dockerfile:6-7`.
  - Fuente: https://github.com/esnet/iperf/releases · verificado 2026-09-29.
  - Cita: `3.20 2025-11-14` · `3.21 2026-04-09` · `3.22 2026-09-29`. Notas de 3.22: "a remote use-after-free in iperf_server_api.c (… CVE-2026-101283) and the other is a heap buffer overflow in iperf_auth.c (… CVE-2026-101276)". Notas de 3.16 (el modelo de hilos que usa el lab): "serviced by different threads".
  - Estado: **CAMBIÓ**.
  - Caveat: no pude volver a verificar que el paquete Alpine `3.20-r0` existe, porque pkgs.alpinelinux.org no devolvió contenido legible. El build del 09-24 lo instaló, así que existía entonces. El server iperf3 solo escucha dentro del cluster y el cluster se destruye cada día, así que el riesgo real es bajo; igual conviene mencionarlo si alguien pregunta por CVEs.

---

### B. Claims de documentación usados en la charla

#### B.1 AWS Graviton Getting Started

- **Loader: instancia grande aparte, sin saturar.** El runbook pide 12xlarge o más y que el loader dedique menos del 50% de su tiempo a generar carga.
  - Fuente: perfrunbook/configuring_your_loadgen.md (último commit en perfrunbook: 2026-07-24). https://github.com/aws/aws-graviton-getting-started/blob/main/perfrunbook/configuring_your_loadgen.md · verificado 2026-09-29.
  - Cita: "Ensure the load generator instance is large enough for driving traffic to the Systems-under-test (SUTs), we recommend using 12xl instances or larger." · "verify the load-generator instance is not using 100% CPU for load-generators that use blocking IO." · "A load-generator that is spending less than 50% of its time generating load is a good target to ensure you are measuring the SUT."
  - Estado: **MATIZ**. El lab usa `c8i.16xlarge` (`infra/nodegroups.tf:132`), que cumple el "12xl or larger". El guard del lab es CPU < 70% (`nodegroups.tf:126`), más laxo que el objetivo de "<50% of its time" del runbook. Hay que decirlo como decisión propia.

- **"Misma AZ".** El runbook recomienda un cluster placement group y, como mínimo, la misma subnet.
  - Fuente: perfrunbook/configuring_your_sut.md. https://github.com/aws/aws-graviton-getting-started/blob/main/perfrunbook/configuring_your_sut.md · verificado 2026-09-29.
  - Cita: "We recommend putting all testing environment instances inside a [cluster placement group], or at a minimum confirm that all instances are in the same subnet (i.e. us-east-1a)." · "A difference of +/-50us is acceptable, differences of >+/-100us can adversely affect testing results."
  - Estado: **MATIZ**. El spec (línea 58) lo llama "requisito del runbook". Es el mínimo aceptable del runbook, no su recomendación: el lab omite el placement group a propósito.

- **Punto de carga: 100% de vCPU o "breaking latency".**
  - Fuente: perfrunbook/defining_your_benchmark.md. https://github.com/aws/aws-graviton-getting-started/blob/main/perfrunbook/defining_your_benchmark.md · verificado 2026-09-29.
  - Cita: "have the load-generator increase load until all vCPUs on the SUT are operating at 100%" · "Breaking latency is the point when the machine can no longer serve more throughput and maintain acceptable response times … find the knee point in the latency/failure/throughput curve".
  - Estado: **VERIFICADO**.

- **THP, huge pages, irqbalance/afinidad de IRQ, `ethtool -C adaptive-rx off`, RPS y LSE.**
  - Fuente: perfrunbook/optimization_recommendation.md y configuring_your_sut.md. https://github.com/aws/aws-graviton-getting-started/blob/main/perfrunbook/optimization_recommendation.md · verificado 2026-09-29.
  - Cita: "Enable Transparent Huge Pages (THP) `echo always > /sys/kernel/mm/transparent_hugepage/enabled` -or- `echo madvise > …`" · "At runtime: `sysctl -w vm.nr_hugepages=X`" · "`-XX:+UseTransparentHugePages` when THP is set to at least `madvise`" · "Set to `ethtool -C ethN adaptive-rx off` for a latency sensitive workload" · "Disable `irqbalance` from dynamically moving IRQ processing between vCPUs and set dedicated cores to process each IRQ." · "Disable Receive Packet Steering (RPS) to avoid contention and extra IPIs. … In general RPS is not needed on Graviton2 and newer." · LSE: "Use `-moutline-atomics` for code that must run on all Graviton platforms" · "`export RUSTFLAGS="-Ctarget-feature=+lse"`" · "try compiling your code on GCC using `-march=armv8.2-a` instead of using `-moutline-atomics`".
  - Estado: **VERIFICADO**.
  - Caveat: hay algo nuevo que no está en el spec. En kernels >= 6.9, THP incluye folios de 16kB y 64kB: "On Linux kernels >=6.9 Transparent Huge Pages (THP) has been extended with Folios that create 16kB, and 64kB huge pages". Bottlerocket usa 6.18, así que aplica, pero el lab no los tocó. El runbook además advierte: "there can be cases where using exclusively huge-pages may lead to performance degradation".

- **java.md: el bundle de JIT "1.5x en algunos workloads".**
  - Fuente: java.md (último commit 2026-07-07). https://github.com/aws/aws-graviton-getting-started/blob/main/java.md · verificado 2026-09-29.
  - Cita: "Flags `-XX:-TieredCompilation -XX:ReservedCodeCacheSize=64M -XX:InitialCodeCacheSize=64M` have shown large (1.5x) improvements in some Java workloads. Corretto 17 needs two additional flags: `-XX:CICompilerCount=2 -XX:CompilationMode=high-only`. `ReservedCodeCacheSize`/`InitialCodeCacheSize` should be equal and can be in range: 64M...127M." · "These are helpful on some workloads but can hurt on others so testing with and without them is essential."
  - Estado: **VERIFICADO**.

- **java.md: `-XX:+UseTransparentHugePages`.**
  - Cita: "Notice that even if the the default is changed from `always` to `madvise`, the JVM can still use THP for the Java heap and code cache if you specify `-XX:+UseTransparentHugePages` on the command line." También advierte que, con THP en `always`, "the THP page size of 2mb matches exactly with the 2mb default stack size on aarch64 and most stacks will be backed up by a single huge page of 2mb", lo que aumenta la memoria usada cuando hay miles de hilos.
  - Estado: **VERIFICADO**.
  - Caveat: la advertencia sobre stacks es relevante para la escena de virtual threads frente a platform threads con THP=always en arm64.

- **java.md: las excepciones cuestan hasta 2x en Graviton.**
  - Cita: "Throwing exceptions and generating stack-traces has been observed to cost up to 2x more on Graviton platforms compared to x86."
  - Estado: **VERIFICADO**.

- **java.md: probar Graviton a mayor utilización de CPU.**
  - Cita: "Be sure to run Graviton instances “hotter”: vCPUs are mapped to physical cores instead of Hyperthreads and performance often flatlines at a much higher CPU utilization than with x86 based instances. Testing at low levels of load can lead to misleading results. The most realistic test results are usually achieved when testing close to breaking latency."
  - Estado: **VERIFICADO**.

- **machinelearning/llama.cpp.md: `-mcpu=native`, Q4_0, hilos explícitos.**
  - Fuente: https://github.com/aws/aws-graviton-getting-started/blob/main/machinelearning/llama.cpp.md (último commit **2026-09-08**) · verificado 2026-09-29.
  - Cita: "cmake .. -DCMAKE_CXX_FLAGS="-mcpu=native" -DCMAKE_C_FLAGS="-mcpu=native"" · el ejemplo usa `meta-llama-3-8b-instruct.Q4_0.gguf` con `-t 64` · "Note: Set the `n_threads` to number of vcpus explicitly while creating the Llama object. This is required to use all cores(vcpus) on Graviton instances. Without this set, the python bindings use half of the vcpus and the performance is not the best."
  - Estado: **CAMBIÓ**.
  - Caveat 1: la doc ahora abre recomendando una imagen de AWS: "AWS publishes a production-ready Graviton (ARM64) llama.cpp image on the Amazon ECR Public Gallery" (`public.ecr.aws/deep-learning-containers/llama-cpp-arm64:server-cpu-v1`), "a from-source build of upstream llama.cpp for the Graviton3 (Neoverse-V1) baseline". Esta sección se agregó después del spec (commit del 09-08). En Q&A pueden preguntar por qué no se usó esa imagen.
  - Caveat 2: la advertencia sobre "half of the vcpus" se refiere a los python bindings, no a `llama-server`. Para el server, ver B.2.
  - Caveat 3: la doc usa Llama 3 8B de SanctumAI; el lab usa Llama 3.1 8B de unsloth.

#### B.2 llama.cpp: imágenes oficiales, KleidiAI/AMX e hilos por defecto

- **Las imágenes oficiales `ghcr.io/ggml-org/llama.cpp:server` son multi-arch.**
  - Fuente: `docs/docker.md` en el tag b10775. https://github.com/ggml-org/llama.cpp/blob/b10775/docs/docker.md · verificado 2026-09-29.
  - Cita: "`ghcr.io/ggml-org/llama.cpp:server`: This image only includes the `llama-server` executable. (platforms: `linux/amd64`, `linux/arm64`, `linux/s390x`)".
  - Estado: **VERIFICADO**. Coincide con el index OCI del tag `server-b10775` (A.3).

- **La imagen oficial se construye con `GGML_CPU_ALL_VARIANTS` y sin KleidiAI. En x86 incluye una variante con AMX.**
  - Fuente: `.devops/cpu.Dockerfile`, `ggml/CMakeLists.txt` y `ggml/src/CMakeLists.txt` en b10775; `.github/workflows/docker.yml`. https://github.com/ggml-org/llama.cpp/tree/b10775 · verificado 2026-09-29.
  - Cita (Dockerfile): `cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=OFF -DLLAMA_BUILD_TESTS=OFF -DGGML_BACKEND_DL=ON -DGGML_CPU_ALL_VARIANTS=ON`. (CMake): `option(GGML_CPU_KLEIDIAI "ggml: use KleidiAI optimized kernels if applicable" OFF)`. Variantes x86: `ggml_add_cpu_backend_variant(sapphirerapids SSE42 AVX F16C FMA AVX2 BMI2 AVX512 AVX512_VBMI AVX512_VNNI AVX512_BF16 AMX_TILE AMX_INT8)` y `zen4 … AVX512_BF16`. Variantes arm: `armv8.6_2 DOTPROD FP16_VECTOR_ARITHMETIC SVE MATMUL_INT8 SVE2`, `armv9.2_1/2 … SME`. Workflow: `"dockerfile": ".devops/cpu.Dockerfile", "platforms": "linux/arm64", … "runs_on": "ubuntu-24.04-arm"`, es decir, build nativo de arm64 y no emulado.
  - Estado: **VERIFICADO**. Coincide con el comentario de `apps/llama/build-kleidiai.sh:4-9`.
  - Caveat: qué variante carga cada nodo (m8i, variante sapphirerapids con AMX INT8; m8a, zen4; m9g, probablemente armv8.6_2, porque Neoverse V3 no tiene SME) se decide en runtime. Es una inferencia a partir del código; para afirmarlo en slide hay que confirmarlo en el log de carga de backends.

- **Hilos por defecto de `llama-server` = núcleos físicos del host, sin mirar el cpuset.** Esto responde la pregunta abierta 4 de facts.
  - Fuente: `common/common.cpp` en b10775. https://github.com/ggml-org/llama.cpp/blob/b10775/common/common.cpp · verificado 2026-09-29.
  - Cita: `cpuparams.n_threads = common_cpu_get_num_math();` → en x86 Linux no híbrido, `return common_cpu_get_num_physical_cores();`, que en Linux hace "enumerate the set of thread siblings, num entries is num cores" leyendo `/sys/devices/system/cpu/cpu<N>/topology/thread_siblings` para todos los CPUs, y devuelve `siblings.size()`.
  - Estado: **VERIFICADO** (código fuente).
  - Caveat: la cuenta se hace sobre `/sys` (todo el host), no sobre la afinidad del contenedor. En m8i.4xlarge (8 núcleos × 2 hilos) da **8**. En m9g.4xlarge y m8a.4xlarge (16 núcleos, sin SMT) da **16**, aunque el cpuset del pod sea de 15 CPUs. Eso coincide con lo que reportó el probe (8 en m8i, 16 en m8a/m9g). La celda stock de m8a/m9g corre 16 hilos sobre 15 CPUs; la de m8i usa la mitad de los vCPUs. Es un hallazgo citable: el default de llama.cpp favorece a x86 con SMT de una forma y castiga a los núcleos sin SMT de otra.

#### B.3 MongoDB 8.0 production notes

- **THP habilitado en 8.0 y deshabilitado en ≤ 7.0.**
  - Fuente: Production Notes (el manual "current" es 9.0) y TCMalloc Performance. https://www.mongodb.com/docs/manual/administration/production-notes/ · https://www.mongodb.com/docs/manual/administration/tcmalloc-performance/ · verificado 2026-09-29.
  - Cita: "If you are running MongoDB 8.0, enable Transparent Hugepages." · "If you are running MongoDB 7.0 or earlier, disable Transparent Huge Pages. In earlier versions, MongoDB performs better with typical (4096 bytes) virtual memory pages." · "In MongoDB 8.0 and later, ensure that THP is enabled before `mongod` starts".
  - Estado: **MATIZ**.
  - Caveat: la receta completa de MongoDB para 8.0+ es `enabled=always`, **`defrag=defer+madvise`**, **`khugepaged/max_ptes_none=0`** y **`vm.overcommit_memory=1`**. El lab solo fija `enabled=always`; `defrag` queda en el default de Bottlerocket (`madvise`, ver B.5). En Q&A pueden señalar que la celda tuned de Mongo no sigue la receta completa de MongoDB. La forma correcta de decirlo: "aplicamos el knob que pide el runbook de Graviton, no la receta completa de MongoDB".

- **Fórmula del caché WiredTiger y `cacheSizeGB` en contenedores.**
  - Cita: "The default WiredTiger internal cache size is the larger of either: 50% of (RAM - 1GB), or 0.256 GB." · "If you run `mongod` in a container (for example, `lxc`, `cgroups`, Docker, etc.) that does _not_ have access to all of the RAM available in a system, you must set `storage.wiredTiger.engineConfig.cacheSizeGB` or `storage.wiredTiger.engineConfig.cacheSizePct` to a value less than the amount of RAM available in the container." · swappiness: "set `vm.swappiness` to either `1` or `0`" · readahead: "Set the readahead setting between 8 and 32".
  - Estado: **VERIFICADO**.

#### B.4 PostgreSQL y THP de shmem

- **`huge_pages` (default `try`) y la postura de PostgreSQL sobre THP.**
  - Fuente: PostgreSQL 18, "Resource Consumption". https://www.postgresql.org/docs/18/runtime-config-resource.html · verificado 2026-09-29.
  - Cita: "Valid values are `try` (the default), `on`, and `off`. … With `huge_pages` set to `try`, the server will try to request huge pages, but fall back to the default if that fails." · "On Linux, this is called "transparent huge pages" (THP). That feature has been known to cause performance degradation with PostgreSQL for some users on some Linux versions, so its use is currently discouraged (unlike explicit use of `huge_pages`)."
  - Estado: **MATIZ**.
  - Caveat: el knob `pg-shmem-thp` del lab (THP de shmem) va en contra de la recomendación oficial de PostgreSQL, que desaconseja THP y prefiere huge pages explícitas. Si la celda tuned de Postgres usa THP de shmem, en la slide hay que decir explícitamente que es contrario a la doc de PostgreSQL y que se midió igual.

- **Guía para `shared_buffers`.**
  - Cita: "a reasonable starting value for `shared_buffers` is 25% of the memory in your system. … it is unlikely that an allocation of more than 40% of RAM to `shared_buffers` will work better than a smaller amount."
  - Estado: **VERIFICADO**.

- **`/sys/kernel/mm/transparent_hugepage/shmem_enabled` controla el tmpfs interno (SysV SHM, memfd, mmap anónimo compartido).**
  - Fuente: doc del kernel, `Documentation/admin-guide/mm/transhuge.rst` (master). https://docs.kernel.org/admin-guide/mm/transhuge.html · verificado 2026-09-29.
  - Cita: "The mount internal tmpfs mount is used for SysV SHM, memfds, shared anonymous mmaps (of /dev/zero or MAP_ANONYMOUS), GPU drivers' DRM objects, Ashmem. To control the THP allocation policy for this internal tmpfs mount, the sysfs knob /sys/kernel/mm/transparent_hugepage/shmem_enabled and the knobs per THP size … can be used." Valores: `always`, `never`, `within_size`, `advise`, más "deny — For use in emergencies, to force the huge option off from all mounts" y "force — Force the huge option on for all - very useful for testing".
  - Estado: **VERIFICADO**. Nota: PostgreSQL usa `shared_memory_type=mmap` por defecto, es decir, memoria compartida anónima, así que queda cubierto por este knob.

#### B.5 Bottlerocket: THP, CPU manager y C-states

- **El `VERIFY` del spec se resuelve así: el setting es `settings.kernel.hugepages.transparent.enabled`. Es de runtime, no requiere reboot y existe desde 1.64.0. El default es `madvise`.**
  - Fuente: bottlerocket.dev, "settings.kernel.*" (1.65.x, la versión más nueva publicada; 1.64.x tiene el mismo contenido; 1.63.x no lo trae). https://bottlerocket.dev/en/os/1.65.x/api/settings/kernel/ · CHANGELOG v1.64.0 · verificado 2026-09-29.
  - Cita: "transparent tunes the kernel’s Transparent Huge Pages (THP) behavior at runtime." · "settings.kernel.hugepages.transparent.enabled Sets the Transparent Huge Pages (THP) policy … Default: madvise Accepted values: always … madvise … never". Defrag: "Default: derived from hugepages.transparent.enabled, which defaults to madvise … When unset, the defrag policy is derived from hugepages.transparent.enabled (always and madvise map to madvise, never maps to never)."
  - Estado: **CAMBIÓ** respecto del spec (línea 196, que proponía `settings.boot.kernel-parameters` + `reboot-to-reconcile`). El lab ya usa el setting correcto (`infra/userdata/thp.toml`).
  - Caveat: esto también responde la pregunta abierta 6 de facts. Según la doc, las celdas stock corrieron con THP `madvise`, no `never`. El gate no lo midió en stock, así que es un dato documental, no observado.

- **`settings.boot.kernel-parameters` + `reboot-to-reconcile` (fallback de THP y única vía para limitar C-states por cmdline).**
  - Fuente: https://bottlerocket.dev/en/os/1.65.x/api/settings/boot/ · verificado 2026-09-29.
  - Cita: "settings.boot.kernel-parameters Kernel parameters expressed as key/value pairs. … During the boot process, the parameters pass via the kernel command line." · reboot-to-reconcile: "settings.boot.kernel-parameters and settings.boot.init-parameters in user data or a bootstrap container without causing a reboot loop."
  - Estado: **VERIFICADO**.
  - Caveat: Bottlerocket no tiene un setting específico para C-states (0 coincidencias de "cstate" en las docs de kernel y boot). La receta de AWS es de cmdline: "add the `intel_idle.max_cstate=1` and `processor.max_cstate=1` options to set `C1` as the deepest C-state for idle cores" · "The `intel_idle.max_cstate=1` option configures the C-state limit for Intel-based instances, and the `processor.max_cstate=1` option configures the C-state limit for AMD-based instances." (https://docs.aws.amazon.com/linux/al2/ug/processor_state_control.html). El lab usa en su lugar `/dev/cpu_dma_latency` en runtime (`manifests/base/cstates-daemonset.yaml:1-45`). La guía de EC2 lista `m8i.4xlarge` y `m8a.4xlarge` en "C-states only" y dice: "AWS Graviton processors have built-in power saving modes and operate at a fixed frequency. Therefore, they do not provide the ability for the operating system to control C-states and P-states." (https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/processor_state_control.html).

- **`settings.kubernetes.cpu-manager-policy = "static"`.**
  - Fuente: https://bottlerocket.dev/en/os/1.65.x/api/settings/kubernetes/ · verificado 2026-09-29.
  - Cita: "settings.kubernetes.cpu-manager-policy Specifies the CPU manager policy. If you want to allow pods with certain resource characteristics to be granted increased CPU affinity and exclusivity on the node, you can set this setting to static. You should reboot if you change this setting after startup … Default: none Accepted values: static none". Opciones: "Accepted values: full-pcpus-only distribute-cpus-across-numa strict-cpu-reservation prefer-align-cpus-by-uncorecache".
  - Estado: **VERIFICADO**. Coincide con `infra/userdata/base.toml:40-53`.

#### B.6 Kubernetes: CPU manager estático

- **CPUs exclusivas solo para pods Guaranteed con requests de CPU enteros.**
  - Fuente: kubernetes/website, `cpu-management-policies.md` (main). https://kubernetes.io/docs/tasks/administer-cluster/cpu-management-policies/ · verificado 2026-09-29.
  - Cita: "Only containers that are both part of a `Guaranteed` pod and have integer CPU `requests` are assigned exclusive CPUs." · "The kubelet requires a CPU reservation greater than zero be made using either `--kube-reserved` and/or `--system-reserved` or `--reserved-cpus` when the static policy is enabled. This is because zero CPU reservation would allow the shared pool to become empty." · "`full-pcpus-only` (GA, visible by default) (1.33 or higher)".
  - Estado: **VERIFICADO**.
  - Caveat: en m8i con SMT, sin `full-pcpus-only`, un pod de 15 CPUs puede recibir hilos hermanos parciales, y de hecho es lo que ocurre, porque 15 es impar. El lab lo decidió a propósito (`base.toml:55`). En la slide hay que decir que "exclusivo" significa vCPU exclusiva, no núcleo físico exclusivo.

#### B.7 Karpenter (v1.14)

- **Requirements de NodePool.**
  - Fuente: https://github.com/aws/karpenter-provider-aws/blob/main/website/content/en/v1.14/concepts/nodepools.md · verificado 2026-09-29.
  - Cita: "Nodes are chosen using both the NodePool's and pod's requirements. If there is no overlap, nodes will not be launched. In other words, a pod's requirements must be within the NodePool's requirements. If a requirement is not defined for a well known label, any value available to the cloud provider may be chosen."
  - Estado: **VERIFICADO**.

- **Selección de instancia: en on-demand equivale a "lowest-price".**
  - Fuente: FAQ v1.14. https://github.com/aws/karpenter-provider-aws/blob/main/website/content/en/v1.14/faq.md · verificado 2026-09-29.
  - Cita: "Karpenter takes 59 other instance types that are larger than the most efficient packing, and passes all 60 instance type options to an API called Amazon EC2 Fleet." · "The EC2 fleet API attempts to provision the instance type based on the Price Capacity Optimized allocation strategy. For the on-demand capacity type, this is effectively equivalent to the `lowest-price` allocation strategy. For the spot capacity type, Fleet will determine an instance type that has both the lowest price combined with the lowest chance of being interrupted. Note that this may not give you the instance type with the strictly lowest price for spot."
  - Estado: **VERIFICADO**.
  - Caveat: Karpenter elige por precio, no por precio-rendimiento. Ese es el punto de la escena del arco: con `m8i` y `m9g` permitidas, Karpenter toma la más barata sin saber cuál rinde más.

- **`consolidationPolicy: WhenEmpty` y `expireAfter`.**
  - Fuente: disruption.md y nodepools.md de v1.14 · verificado 2026-09-29.
  - Cita: "| `WhenEmpty` | Only empty nodes (a node is empty when it has only pods with no disruption cost, such as daemonsets, …) | You want the most conservative behavior …" · "`consolidateAfter` determines how long Karpenter should wait for new work to land on a node before considering it in consolidation." · "Expiration is a forceful disruption method that begins draining a node immediately once its lifetime exceeds the duration set on the owning NodeClaim's `spec.expireAfter` field." · "By default, `expireAfter` is set to `720h` (30 days)."
  - Estado: **VERIFICADO**. Coincide con `infra/karpenter/nodepool.yaml` (`WhenEmpty`, `consolidateAfter: 1m`, `expireAfter: 8h`).
  - Caveat: v1.14 documenta una política nueva, `Balanced`, entre `WhenEmpty` y `WhenEmptyOrUnderutilized`. El default sigue siendo `WhenEmptyOrUnderutilized`.

#### B.8 Imágenes multi-arch y `exec format error`

- **Una imagen multi-plataforma es un manifest list; el runtime elige la variante del host.**
  - Fuente: Docker Docs, "Multi-platform builds" (docker/docs main). https://docs.docker.com/build/building/multi-platform/ · verificado 2026-09-29.
  - Cita: "Single-platform images contain a single manifest that points to a single configuration and a single set of layers. Multi-platform images contain a manifest list, pointing to multiple manifests, each of which points to a different configuration and set of layers." · "When you pull the image, the registry returns the manifest list, and Docker automatically selects the correct variant based on the host's architecture." · "`docker buildx build --platform linux/amd64,linux/arm64 .`" · "Emulation with QEMU can be much slower than native builds".
  - Estado: **VERIFICADO**.

- **`exec format error` = ENOEXEC: el binario es de otra arquitectura.**
  - Fuente: man-pages de Linux, execve(2) y errno(3). https://man7.org/linux/man-pages/man2/execve.2.html · https://man7.org/linux/man-pages/man3/errno.3.html · verificado 2026-09-29.
  - Cita: "ENOEXEC Exec format error (POSIX.1-2001)." La página de execve define ENOEXEC como un ejecutable que no está en un formato reconocido o que es para la arquitectura equivocada.
  - Estado: **MATIZ**.
  - Caveat: no encontré una página oficial de Kubernetes, containerd o Docker que describa explícitamente la escena "imagen single-arch amd64 en nodo arm64 → `exec format error`". El mecanismo se explica combinando la doc de Docker (una imagen single-platform no tiene lista de variantes) con ENOEXEC. Para la escena conviene mostrar el error real capturado en el lab, no una cita.

- **EKS pide verificar que los DaemonSets corran en todas las arquitecturas del cluster.** Es la cita más directa para la escena del "DaemonSet blocker".
  - Fuente: Amazon EKS User Guide, "Amazon EKS-optimized Arm Amazon Linux AMIs". https://docs.aws.amazon.com/eks/latest/userguide/eks-optimized-ami.html · verificado 2026-09-29.
  - Cita: "Applications deployed to Arm nodes must be compiled for Arm." · "If you have DaemonSets that are deployed in an existing cluster, or you want to deploy them to a new cluster that you also want to deploy Arm nodes in, then verify that your DaemonSet can run on all hardware architectures in your cluster." · "consider deploying multi-architecture container images to a container repository such as Amazon Elastic Container Registry and then adding node selectors to your manifests".
  - Estado: **VERIFICADO**.

#### B.9 Red Hat JBoss EAP

- **EAP 7.4: JDK 8/11/17 (17 desde 7.4 Update 7 con Red Hat OpenJDK y desde Update 8 con Oracle JDK), solo x86_64.**
  - Fuente: "Red Hat JBoss EAP 7 Supported Configurations" (Customer Portal, "Updated 2026-02-17"). https://access.redhat.com/articles/2026253 · verificado 2026-09-29. Es **pública**: el contenido se descarga sin login.
  - Cita: "17 ** support only with EAP 7.4 Update 7 and above" · "support only with EAP 7.4 Update 8 and above" (Oracle JDK) · filas de JVM "17 … 11 1.8". Todas las filas de EAP 7.4 (RHEL 9/8/7, Windows Server 2022/2019/2016) listan `x86_64`. No hay filas aarch64.
  - Estado: **VERIFICADO**.

- **EAP 8: en bare metal/VM solo se prueba x86_64; las imágenes de OpenShift sí soportan ARM.**
  - Fuente: "Red Hat JBoss Enterprise Application Platform (EAP) 8 Supported Configurations" (pública, "Updated 2026-09-23"). https://access.redhat.com/articles/6961381 · EAP 8.0 Release Notes, cap. "Supported configurations": https://docs.redhat.com/en/documentation/red_hat_jboss_enterprise_application_platform/8.0/html/release_notes_for_red_hat_jboss_enterprise_application_platform_8.0/supported-configurations-rn_assembly-release-notes · verificado 2026-09-29.
  - Cita (artículo): "Tested Operating Systems … Red Hat Enterprise Linux 10 (latest update) x86_64 Red Hat build of OpenJDK 25 Red Hat build of OpenJDK 21 …". La palabra `x86_64` aparece 35 veces y `aarch64`/ARM ninguna. JVMs: "Red Hat build of OpenJDK 25 21 17". Aviso: "JBoss EAP 8.0 Update 12 will be the last 8.0 Update, you will need to move to EAP 8.1". Release notes 8.0: "Builder and Runtime images are supported for OpenJDK 17 / RHEL 8 on Intel, IBM systems Z & P, and ARM architectures."
  - Estado: **MATIZ**.
  - Caveat: la frase correcta es "EAP 8 en ARM está soportado como imagen de contenedor en OpenShift; en la matriz de SO probados solo aparece x86_64". No hay que decir "EAP 8 no soporta ARM". Ninguna de las dos páginas pidió login.

#### B.10 Virtual threads

- **JEP 444: virtual threads son GA en JDK 21.**
  - Fuente: https://openjdk.org/jeps/444 · verificado 2026-09-29.
  - Cita: "Status Closed / Delivered · Release 21" · "Introduce virtual threads to the Java Platform. Virtual threads are lightweight threads that dramatically reduce the effort of writing, maintaining, and observing high-throughput concurrent applications."
  - Estado: **VERIFICADO**.
  - Caveat, útil para "el twist de JDK 25": JEP 491 (JDK 24) eliminó casi todo el pinning por `synchronized`: "arranging for virtual threads that block in such constructs to release their underlying platform threads … This will eliminate nearly all cases of virtual threads being pinned" (https://openjdk.org/jeps/491, "Release 24"). Con JDK 25, el argumento de "evitar synchronized" ya no aplica.

- **Spring Boot `spring.threads.virtual.enabled`.**
  - Fuente: metadata de configuración y docs de Spring Boot (main). https://github.com/spring-projects/spring-boot/blob/main/core/spring-boot-autoconfigure/src/main/resources/META-INF/additional-spring-configuration-metadata.json · https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html · verificado 2026-09-29.
  - Cita: `"name": "spring.threads.virtual.enabled", "type": "java.lang.Boolean", "description": "Whether to use virtual threads.", "defaultValue": false` · "When virtual threads are enabled (using Java 21+ and spring.threads.virtual.enabled set to `true`) this will be a SimpleAsyncTaskExecutor that uses virtual threads."
  - Estado: **VERIFICADO**. Los overlays `*-vthreads` lo pasan como variable de entorno con relaxed binding.

#### B.11 Linux: doc de THP en el kernel

- **Valores de `enabled` y `defrag`.**
  - Fuente: https://docs.kernel.org/admin-guide/mm/transhuge.html (fuente: `Documentation/admin-guide/mm/transhuge.rst` en master de torvalds/linux) · verificado 2026-09-29.
  - Cita: "echo always >/sys/kernel/mm/transparent_hugepage/enabled · echo madvise … · echo never …". Defrag: "always means that an application requesting THP will stall on allocation failure and directly reclaim pages and compact memory" · "defer means that an application will wake kswapd in the background to reclaim pages and wake kcompactd" · "defer+madvise will enter direct reclaim and compaction like `always`, but only for regions that have used madvise(MADV_HUGEPAGE)" · "madvise will enter direct reclaim like `always` but only for regions that are have used madvise(MADV_HUGEPAGE). This is the default behaviour." · "never should be self-explanatory."
  - Estado: **VERIFICADO**.
  - Caveat: "The transparent_hugepage/enabled and transparent_hugepage/hugepages-<size>kB/enabled values and tmpfs mount option only affect future behavior. So to make them effective you need to restart any application that could have been using hugepages." Esto es lo que respalda el orden de arranque de los DaemonSets de THP antes del SUT.

---

### Discrepancias con nuestros documentos

1. **Spec, línea 140: "la especificación de la señal [OTel Profiles] es estable desde 2025"**. Es falso: la spec está en "Status: Alpha" y el proto de profiles en "Development". Hay que corregirlo a "tanto la señal como el profiler están en Alpha".
2. **Spec, líneas 140 y 192: "Pyroscope 2.3.0"**. Lo que corrió fue el chart 2.2.1 (app 2.2.1). Además, `pyroscope-values.yaml:5-8`, `manifests/base/README.md:295` y `README.md:17` dicen "v2.3.0 no tiene chart aún". Hoy existe el chart 2.3.1 (app 2.3.1, 2026-09-08) y el parche 2.2.2 con CVEs.
3. **Spec, líneas 77 y 193, y `manifests/base/ebpf-profiler.yaml:18-21`: "0.147.0"**. La imagen es 0.160.0 (`:72`). Esto ya estaba en facts, pregunta abierta 8, y sigue sin corregir.
4. **Spec, líneas 58 y 190: "AWS provider ~> 6.53"**. Lo real es `~> 6.63`, con lock en 6.63.0 (`infra/versions.tf:34`).
5. **Spec, línea 196: THP en Bottlerocket vía `settings.boot.kernel-parameters` + VERIFY**. Queda resuelto: el setting es `settings.kernel.hugepages.transparent.enabled` (runtime, >= 1.64.0), que es lo que usa `infra/userdata/thp.toml`. Hay que actualizar el spec.
6. **Spec, línea 58: "misma AZ es requisito del Graviton perf runbook"**. El runbook recomienda un cluster placement group y acepta "at a minimum" la misma subnet. Es el mínimo, no un requisito.
7. **Spec §9, loader "nunca saturado"**. El runbook cuantifica: loader de 12xl o más, y "less than 50% of its time generating load" como objetivo. El guard del lab es 70% de CPU. Hay que presentarlo como umbral propio.
8. **Spec §9, llama.cpp.md**. El resumen "hilos explícitos (los defaults no son los mejores)" viene de la nota sobre python bindings ("use half of the vcpus"), no sobre `llama-server`. Además, la doc cambió el 2026-09-08 y ahora recomienda primero la imagen DLC de AWS para Graviton.
9. **Facts §7, PetClinic "(v4.0.2, Boot 4.1.1)"**. El commit pinneado está en master, 62 commits por delante del tag `v4.0.2` (que usa Boot 4.0.2). `apps/java/README.md` lo dice bien; la tabla de facts es ambigua.
10. **Facts, pregunta abierta 4 (hilos de llama.cpp en stock): queda respondida.** `common_cpu_get_num_math()` cuenta los núcleos físicos del host desde `/sys` e ignora el cpuset. El resultado es 8 en m8i y 16 en m8a/m9g sobre un cpuset de 15. Hay sobre-suscripción en m8a/m9g stock y media ocupación en m8i stock. Es comportamiento documentado en el código, no un bug del lab.
11. **Facts, pregunta abierta 6 (THP en stock): respondida por la doc.** El default de Bottlerocket es `madvise`. No hay medición en nodos stock.
12. **Comentario en `infra/userdata/thp.toml:9-10` ("MongoDB 8.0 production notes now recommend THP enabled")**. Es correcto, pero incompleto: MongoDB también pide `defrag=defer+madvise`, `max_ptes_none=0` y `overcommit_memory=1`, y el lab deja defrag en `madvise`.
13. **Spec, línea 70: loader `c7i.4xlarge`**. Ahora es `c8i.16xlarge` (`infra/nodegroups.tf:132`). Ya estaba en facts, pregunta abierta 8.

### Riesgos de versión (lo que puede salir en Q&A)

- **Nada de lo que usa el lab está EOL.** EKS 1.36 tiene standard support hasta 2027-08-02; PostgreSQL 18 hasta 2030-11-14; MongoDB 8.0 hasta 2029-10-31; JDK 25 es LTS; kernel 6.18 es longterm.
- **"¿Por qué no Kubernetes 1.37 / MongoDB 9.0 / JDK 27?"** Upstream ya sacó K8s 1.37 y Bottlerocket 1.66 trae variantes 1.37, pero EKS no la ofrece todavía. MongoDB 9.0 salió en septiembre de 2026, después del diseño; 8.0 es la versión del cambio de THP y la de CMP333. JDK 27 es feature release, no LTS.
- **Parches de seguridad disponibles y no aplicados:** Temurin 25.0.4.1 (TLS/HTTP), Pyroscope 2.2.2/2.3.1 (CVEs en grpc, x/crypto, etcd) e iperf3 3.22 (use-after-free remoto y heap overflow; salió hoy). El impacto real es bajo, porque el cluster es efímero y privado, pero si alguien pregunta, la respuesta es "pinneado a la fecha del lab, parches posteriores conocidos".
- **Reproducibilidad del módulo EKS:** `~> 21.25` sin lock resuelve hoy a 21.26.0. Quien clone el repo no obtiene el mismo módulo. Hay que fijar `21.25.0` antes de publicar.
- **APerf 1.3.0** amplía el PMU a "all EC2 instance types". Si los reportes 1.2.3 de m8a o m9g tienen huecos de PMU, alguien que conozca APerf lo va a notar.
- **El profiler en Alpha y la doc de Grafana con una imagen que no arranca en 6.18.** Se puede usar como material de slide ("la doc oficial te da un tag roto en kernels nuevos"), con `results/profiler-gate.md:31` como evidencia.
- **La imagen oficial de llama.cpp no trae KleidiAI y sí trae AMX en x86.** Un asistente de Arm o de Intel lo va a preguntar. El lab tiene la respuesta (`b10775-kleidiai`), pero en la slide la comparación "stock" tiene que decir que el stock de x86 ya incluye AMX y el de arm64 no incluye KleidiAI.
- **La guía de AWS para llama.cpp en Graviton ahora recomienda su propia imagen DLC** (`llama-cpp-arm64:server-cpu-v1`). No se midió. Es una pregunta probable del público de AWS.
- **PostgreSQL desaconseja THP explícitamente.** Si una celda tuned de Postgres usa THP de shmem, puede salir la pregunta "la doc de Postgres dice que no". Hay que tener la cita a mano.
- **Versiones de add-ons de EKS y de Bottlerocket por día de Task 7:** no quedaron registradas. No se puede afirmar qué versión corrió cada día después del 09-24.

---

### Slide 21b. ¿Y si corro en Fargate? (verificado 2026-09-30)

**F-01. "EKS en Fargate no corre Arm."** — https://docs.aws.amazon.com/eks/latest/userguide/fargate.html, tabla: "Can run workloads that require Arm processors | No"; también "Daemonsets aren't supported on Fargate." y "Amazon EKS doesn't support Fargate Spot." Roadmap abierto: https://github.com/aws/containers-roadmap/issues/1629 (2022-01-18, Proposed).
**F-02. "ECS en Fargate sí: cpuArchitecture ARM64."** — https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html: "The valid values are `X86_64` and `ARM64`."
**F-03. "Graviton en Fargate: 20 % menos por vCPU y GB; AWS dice hasta 40 % mejor precio-rendimiento."** — https://aws.amazon.com/fargate/faqs/: "delivers up to 40% improved price/performance at 20% lower cost over comparable Intel x86-based Fargate". Tarifas us-east-1 (ejemplos de https://aws.amazon.com/fargate/pricing/): x86 $0.000011244/vCPU-s, ARM $0.0000089944/vCPU-s. Caveat: el 40 % es cifra de AWS, no medida en el lab.
**F-04. "Fargate Spot con Graviton existe en ECS."** — https://aws.amazon.com/about-aws/whats-new/2024/09/amazon-ecs-graviton-based-spot-compute-fargate/ (2024-09-06).
**F-05. "No eliges el tipo de servidor."** — EKS doc: "You also don't need to choose server types".
**F-06. "La flota Arm de Fargate mezcla generaciones."** — https://github.com/aws/containers-roadmap/issues/2230: herrhound (AWS), 2024-09-09: "We added Graviton 3 to Fargate fleet across. Resolving issue." Vlaaaaaaad (usuario), 2024-12-03: "the ECS on Fargate fleet was using both Graviton2 and Graviton3 ... the split was `rand(30%, 100%)`". Caveat: la mezcla es medición de un usuario, "a handful of super-small tests"; AWS no publica la generación.
**F-07. "Ver en qué instancia caíste: /sys/class/dmi/id/product_name."** — mismo hilo, Vlaaaaaaad, 2025-02-01: "`/sys/class/dmi/id/product_name` seems to contain the underlying instance type used by Fargate". Caveat: observación de usuario, no documentado por AWS.
**F-08. "Para elegir instancia o fabricante: ECS Managed Instances."** — https://github.com/aws/containers-roadmap/issues/1030, AbhishekNautiyal (AWS), 2025-10-06: "This feature has been delivered with the Amazon ECS Managed Instances launch"; https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ManagedInstances.html: "you can specify desired instance attributes including instance types, CPU manufacturers, and accelerators."
**F-09. "Otros usuarios reportan variaciones de rendimiento en Fargate."** — https://github.com/aws/containers-roadmap/issues/2019 (abierto): "We have seen cases being 30% slower in some instances." Caveat: anécdota de usuario.
