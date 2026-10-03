"""Evidence-pack charts from analysis/data/cells.csv (talk-visuals theme, dataviz method).

Run: python3 slides/visuals/src/charts.py  -> slides/visuals/<nn>-<slug>.svg (then render.py --png-only).
Chip colors validated with dataviz validate_palette.js (light): violet / teal / blue, all checks pass;
tritan pair teal-blue is in the 6-8 floor band, so every bar carries a direct text label.
"""
import csv
import pathlib
import re
import statistics

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = pathlib.Path(__file__).resolve().parent.parent
VIOLET_G, TEAL_A, BLUE_I = "#6D4AE8", "#0e9f9a", "#1f6fe5"
CHIPS = [("arm", "Graviton5 (m9g)", "#6D4AE8"), ("amd", "EPYC (m8a)", "#0e9f9a"), ("x86", "Xeon 6 (m8i)", "#1f6fe5")]
TYPES = {"arm": "m9g.4xlarge", "amd": "m8a.4xlarge", "x86": "m8i.4xlarge"}
COST = (ROOT / "results/cost.md").read_text()
rate = lambda t: float(re.search(rf"\| {re.escape(t)} \| ([0-9.]+)", COST)[1])
T7 = "Fuente: lab propio, Task 7, 2 días × 3 runs; barra = media de los 2 días, línea = mín–máx entre días"

rows = list(csv.DictReader(open(ROOT / "analysis/data/cells.csv")))


def task7(workload, variant, field=None):
    """chip -> [value per day] for a Task 7 cell (set-aside dirs excluded)."""
    out = {}
    for r in rows:
        if r["day_class"].startswith("task7") and not r["set_aside"] and r["workload"] == workload \
                and r["variant"] == variant:
            f = field or ("knee_throughput" if workload in ("postgres", "mongo") else "headline_median")
            if r[f]:
                out.setdefault(r["chip"], []).append(float(r[f]))
    return out


def arc():
    out = {}
    for r in rows:
        if "task8" in r["results_dir"] and r["headline_median"]:
            out.setdefault(r["variant"], (r["instance_type"], []))[1].append(float(r["headline_median"]))
    return {f: (t, statistics.mean(v)) for f, (t, v) in out.items()}


def fmt(x, unit):
    if unit == "%":
        return "0 %" if round(x) == 0 else f"{x:+.0f} %"
    if unit in ("tok/s", "x", "núcleos/Gbps"):
        return f"{x:.3f}" if unit == "núcleos/Gbps" else (f"{x:.2f}x" if unit == "x" else f"{x:.1f}")
    if x >= 100000 or round(x / 1000, 1) % 1 == 0:
        return f"{x/1000:.0f}k"
    return f"{x/1000:.1f}k" if x >= 10000 else f"{x/1000:.1f}k"


HEAD = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080" width="1920" height="1080" font-family="'Inter', 'Helvetica Neue', Arial, sans-serif">
<title>{title}</title>
<defs>
<linearGradient id="tv-grad-h" gradientUnits="userSpaceOnUse" x1="96" y1="0" x2="1824" y2="0"><stop offset="0" stop-color="#4C2FC9"/><stop offset=".5" stop-color="#6D4AE8"/><stop offset="1" stop-color="#A78BFA"/></linearGradient>
<radialGradient id="tv-glow-a"><stop offset="0" stop-color="#A78BFA" stop-opacity=".16"/><stop offset=".45" stop-color="#6D4AE8" stop-opacity=".08"/><stop offset="1" stop-color="#6D4AE8" stop-opacity="0"/></radialGradient>
<radialGradient id="tv-glow-b"><stop offset="0" stop-color="#6D4AE8" stop-opacity=".10"/><stop offset="1" stop-color="#6D4AE8" stop-opacity="0"/></radialGradient>
</defs>
<style>@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&amp;family=Montserrat:wght@600;700&amp;family=JetBrains+Mono&amp;display=block');
.k{font:26px 'JetBrains Mono',Menlo,monospace;fill:#15123C}
.h{font-family:Montserrat,Inter,sans-serif;font-size:50px;font-weight:700;fill:#15123C}
.sub{font-size:26px;fill:#5E5A80}
.v{font-size:28px;font-weight:600;fill:#15123C}
.lab{font-size:28px;font-weight:600;fill:#15123C}
.c{font-size:24px;fill:#5E5A80}
.src{font-size:24px;fill:#5E5A80}
</style>
<rect width="1920" height="1080" fill="#ffffff"/>
<circle cx="1860" cy="40" r="820" fill="url(#tv-glow-a)"/><circle cx="60" cy="1060" r="760" fill="url(#tv-glow-b)"/>
"""


def frame(kicker, title, sub, body, source):
    k = f'<text x="96" y="74" class="k"><tspan fill="#6D4AE8">[</tspan>{kicker}<tspan fill="#6D4AE8">]</tspan></text>'
    subs = "".join(f'<text x="96" y="{192 + i*36}" class="sub">{t}</text>' for i, t in enumerate([sub] if isinstance(sub, str) else sub))
    return (HEAD.replace("{title}", title) + k
            + f'<text x="96" y="140" class="h">{title}</text>{subs}'
            + body + f'<text x="96" y="990" class="src">{source}</text></svg>\n')


def legend(items, y=250):
    out, x = [], 96
    for name, color in items:
        out.append(f'<rect x="{x}" y="{y-20}" width="24" height="24" rx="4" fill="{color}"/>'
                   f'<text x="{x+36}" y="{y}" class="c">{name}</text>')
        x += 36 + int(len(name) * 24 * 0.5) + 56
    return "".join(out)


def why_box(config, why, y):
    """Thin box under the legend: what was run (config) and the measured reason (por qué)."""
    return (f'<rect x="96" y="{y}" width="1728" height="92" rx="14" fill="#F6F4FE" stroke="#DCD6F7" stroke-width="1.5"/>'
            f'<text x="124" y="{y+37}" font-family="JetBrains Mono,Menlo,monospace" font-size="20" fill="#6D4AE8">CONFIG</text>'
            f'<text x="264" y="{y+37}" font-size="22" fill="#15123C">{config}</text>'
            f'<text x="124" y="{y+73}" font-family="JetBrains Mono,Menlo,monospace" font-size="20" fill="#6D4AE8">POR QUÉ</text>'
            f'<text x="264" y="{y+73}" font-size="22" fill="#15123C">{why}</text>')


def ref_key(x, text, y=250):
    return (f'<line x1="{x}" x2="{x+44}" y1="{y-8}" y2="{y-8}" stroke="#5E5A80" stroke-width="2" stroke-dasharray="8 8"/>'
            f'<text x="{x+58}" y="{y}" class="c">{text}</text>')


def bars(groups, unit, ymax, y0=900, top=300, ref=None, vs_x86=None, inside_below_ref=False):
    """groups: [(label, [(chip_key, [day values])])]. Grouped bars, mean + min-max whisker, direct labels.
    vs_x86: "up" (higher = better) or "down" (lower = better) prints each bar's multiple of the Xeon bar inside it."""
    h = y0 - top
    n = len(groups)
    gw = 1728 / n
    bw = min(150, (gw - 120) / max(len(it) for _, it in groups))
    out = [f'<line x1="96" x2="1824" y1="{y0}" y2="{y0}" stroke="#DCD6F7" stroke-width="2"/>']
    if ref is not None:
        ry = y0 - ref / ymax * h
        # label lives in the legend row (ref_key): a label on the line collides with the last group
        out.append(f'<line x1="96" x2="1824" y1="{ry:.1f}" y2="{ry:.1f}" stroke="#5E5A80" stroke-width="2" stroke-dasharray="8 8"/>')
    for gi, (label, items) in enumerate(groups):
        gx = 96 + gi * gw + (gw - bw * len(items) - 12 * (len(items) - 1)) / 2
        x86 = statistics.mean(dict(items)["x86"]) if vs_x86 and "x86" in dict(items) else None
        for bi, (chip, vals) in enumerate(items):
            color = dict((c, col) for c, _, col in CHIPS).get(chip, chip)
            m = statistics.mean(vals)
            x = gx + bi * (bw + 12)
            bh = m / ymax * h
            y = y0 - bh
            out.append(f'<path d="M{x:.1f},{y0} V{y+4:.1f} a4,4 0 0 1 4,-4 H{x+bw-4:.1f} a4,4 0 0 1 4,4 V{y0} Z" fill="{color}"/>')
            if x86 and chip != "x86":
                r = m / x86 if vs_x86 == "up" else x86 / m
                r1 = int(r * 10 + 0.5 + 1e-9) / 10   # half-up: 29/20 = 1.45 -> 1.5, not float-rounded 1.4
                txt = f"{r1:.1f}× Xeon 6" if vs_x86 == "up" else f"{(1 - m / x86) * 100:.0f} % menos"
                if r1 == 1.0:  # within ±5 %: say "tie", not a fake 1.0x win
                    txt = "≈ Xeon 6"
                out.append(f'<text x="{x+bw/2:.1f}" y="{y+40:.1f}" text-anchor="middle" font-size="22" font-weight="600" fill="#fff">{txt}</text>')
            if len(vals) > 1:
                lo, hi = y0 - min(vals) / ymax * h, y0 - max(vals) / ymax * h
                cx = x + bw / 2
                out.append(f'<path d="M{cx:.1f},{lo:.1f} V{hi:.1f} M{cx-14:.1f},{lo:.1f} H{cx+14:.1f} M{cx-14:.1f},{hi:.1f} H{cx+14:.1f}" stroke="#15123C" stroke-width="2.5" fill="none"/>')
                y = min(y, hi)
            if inside_below_ref and ref is not None and m < ref:   # label would sit on the dashed line: lift it above the line
                out.append(f'<text x="{x+bw/2:.1f}" y="{y0 - ref / ymax * h - 14:.1f}" text-anchor="middle" class="v">{fmt(m, unit)}</text>')
            else:
                out.append(f'<text x="{x+bw/2:.1f}" y="{y-14:.1f}" text-anchor="middle" class="v">{fmt(m, unit)}</text>')
        out.append(f'<text x="{96+gi*gw+gw/2:.1f}" y="{y0+48}" text-anchor="middle" class="lab">{label}</text>')
    return "".join(out)


def workload_chart(name, kicker, title, sub, workload, variants, unit, box, source=T7):
    groups = []
    for label, var in variants:
        d = task7(workload, var)
        groups.append((label, [(c, d[c]) for c, _, _ in CHIPS if c in d]))
    ymax = max(max(v) for _, it in groups for _, v in it) * 1.18
    ly = 250 + 36 * (len(sub) - 1 if isinstance(sub, list) else 0)
    body = legend([(n, c) for _, n, c in CHIPS], y=ly) + why_box(*box, ly + 28) + bars(groups, unit, ymax, top=ly + 160, vs_x86="up")
    (OUT / f"{name}.svg").write_text(frame(kicker, title, sub, body, source))


def per_dollar():
    # same variant for every chip (not "best per chip"); net = Gbps per $/h (instance cap, 1 day: O-40)
    sets = [("Go", "go", "stock"), ("Java", "java", "tuned"), ("Java + v. threads", "java", "tuned-vthreads"),
            ("Inferencia", "inference", "tuned"), ("PostgreSQL", "postgres", "tuned"), ("MongoDB", "mongo", "tuned"),
            ("Red (Gbps)", "net", "stock")]
    groups = []
    for label, w, v in sets:
        d = task7(w, v)
        base = statistics.mean(d["x86"]) / rate(TYPES["x86"])
        groups.append((label, [(c, [x / rate(TYPES[c]) / base for x in d[c]]) for c in ("arm", "amd")]))
    box = ("precio por hora, on-demand us-east-1: Graviton5 $0.78 · Xeon 6 $0.85 · EPYC $0.97 (mismo tamaño .4xlarge)",
           "Graviton5 cuesta 8 % menos que Xeon 6 y 20 % menos que EPYC, y en estas pruebas rinde igual o más; en PostgreSQL, EPYC compensa su precio")
    body = (legend([(n, c) for _, n, c in CHIPS[:2]], y=286) + ref_key(620, "1.00× = Xeon 6 (m8i)", y=286)
            + why_box(*box, 314) + bars(groups, "x", 2.6, top=446, ref=1.0, inside_below_ref=True))
    (OUT / "18-por-dolar.svg").write_text(frame(
        "PRECIO-RENDIMIENTO", "Por dólar, Graviton5 lidera en seis de siete escenarios",
        ["Cuánto trabajo da cada dólar por hora frente a Xeon 6 (1.00×, línea punteada); más alto = mejor",
         "Misma variante en los tres chips: con ajustes, salvo Go y red; red = Gbps por dólar, un solo día"], body,
        T7 + "; precios: AWS Pricing API"))


def tuning():
    sets = [("PostgreSQL", "postgres", "stock", "tuned"), ("Java", "java", "stock", "tuned"),
            ("Java + v. threads", "java", "tuned", "tuned-vthreads"), ("Inferencia", "inference", "stock", "tuned"),
            ("MongoDB", "mongo", "stock", "tuned")]
    groups = []
    for label, w, a, b in sets:
        da, db = task7(w, a), task7(w, b)
        groups.append((label, [(c, [(statistics.mean(db[c]) / statistics.mean(da[c]) - 1) * 100]) for c, _, _ in CHIPS]))
    # fuentes O-06, O-08, O-09, O-10, O-11, O-25; facts-setup §3.7 (what each ajuste is)
    box = ("PostgreSQL: 16 GB de buffers + páginas grandes · Java: páginas grandes + flags de JVM · inferencia: 15 hilos · MongoDB: páginas grandes",
           "ajustar rinde donde el default te deja lejos: sin -t, llama.cpp usa 8 hilos en Xeon (+29 %); MongoDB no estuvo limitada por CPU")
    body = legend([(n, c) for _, n, c in CHIPS], y=286) + why_box(*box, 314) + bars(groups, "%", 36, top=446)
    (OUT / "16-perillas.svg").write_text(frame(
        "AJUSTES", "Ajustar paga, pero no igual en cada chip",
        ["Ganancia frente a la versión sin ajustes; Java + virtual threads, frente a Java con ajustes; más alto = mejor",
         "En red (1 día), los ajustes de latencia costaron entre 20 % y 124 % más CPU por Gbps recibido"], body,
        "Fuente: lab propio, Task 7, media de 2 días; dentro del ruido: Java en EPYC, MongoDB en Graviton5 y EPYC; inferencia en Graviton5: leve (0–13 %)"))


def net():
    groups = []
    for label, var in (("Sin ajustes", "stock"), ("Con ajustes de latencia (IRQ fijas)", "tuned")):
        d = task7("net", var, "cpu_cores_per_gbps_fwd_median")
        groups.append((label, [(c, d[c]) for c, _, _ in CHIPS if c in d]))
    box = ("iperf3, 8 flujos TCP, 60 s por sentido, entre dos nodos del mismo tipo · los Gbps los limita la instancia",
           "Graviton5 y EPYC reciben tráfico a un costo parecido; Xeon paga 2–3×, probablemente porque sus 16 vCPU son 8 núcleos con SMT")
    body = legend([(n, c) for _, n, c in CHIPS], y=286) + why_box(*box, 314) + bars(groups, "núcleos/Gbps", 0.13, top=446, vs_x86="down")
    # fuentes O-40, O-41, O-11
    (OUT / "15b-red.svg").write_text(frame(
        "RED", "Red: Graviton5 gasta un tercio de la CPU de Xeon 6 por Gbps",
        ["Núcleos de CPU que gasta el nodo por cada Gbps recibido (iperf3, 8 flujos); más bajo = mejor; % frente a Xeon 6",
         "Los Gbps los pone la instancia, no el chip; los ajustes de latencia no sumaron Gbps y sí CPU"], body,
        "Fuente: lab propio, Task 7 día 2 (un solo día, 3 runs); throughput 16.9 Gbps m9g, 14.9 m8a y m8i"))


def hbars(rows, xmax, y0=300, row=62, gap=26, x0=440, x1=1400):
    """rows: [(family, chip, value, color, right_text, group)]; horizontal bars, vendor groups split by a gap."""
    out, y, prev = [], y0, None
    for fam, chip, v, color, txt, grp in rows:
        if prev is not None and grp != prev:
            y += gap
        prev = grp
        w = v / xmax * (x1 - x0)
        out.append(f'<text x="96" y="{y+30}" font-size="30" font-weight="700" fill="#15123C">{fam}</text>'
                   f'<text x="96" y="{y+54}" font-size="20" fill="#5E5A80">{chip}</text>'
                   f'<rect x="{x0}" y="{y+8}" width="{w:.1f}" height="42" rx="6" fill="{color}"/>'
                   f'<text x="{x0+w+18:.1f}" y="{y+38}" font-size="26" font-weight="600" fill="#15123C">{txt}</text>')
        y += row
    return "".join(out)


def arc_chart():
    # Task 8 arc: 1 fixed run per family (m8g: 2 nodes); fuentes O-44..O-47, headline.md
    a = arc()
    t5, v5 = a["m5"]
    fams = [("m5", "Intel Xeon", BLUE_I, "intel"), ("m6i", "Intel Xeon", BLUE_I, "intel"), ("m7i", "Intel Xeon", BLUE_I, "intel"),
            ("m8i", "Intel Xeon 6", BLUE_I, "intel"), ("m8a", "AMD EPYC 5.ª gen", TEAL_A, "amd"),
            ("m6g", "Graviton2", VIOLET_G, "arm"), ("m7g", "Graviton3", VIOLET_G, "arm"),
            ("m8g", "Graviton4", VIOLET_G, "arm"), ("m9g", "Graviton5", VIOLET_G, "arm")]
    prev_in = {"m6i": "m5", "m7i": "m6i", "m8i": "m7i", "m7g": "m6g", "m8g": "m7g", "m9g": "m8g"}
    raw, cost = [], []
    for f, chip, col, grp in fams:
        t, v = a[f]
        step = f" · +{int((v / a[prev_in[f]][1] - 1) * 100 + 0.5)} % vs {prev_in[f]}" if f in prev_in else ""
        raw.append((f, chip, v, col, f"{v/1000:.0f} mil rps · {v/v5:.2f}× m5{step}", grp))
        c = rate(t) / (v * 3600) * 1e9           # $ of node time per 1,000 M requests at the breaking point
        c5 = rate(t5) / (v5 * 3600) * 1e9
        cost.append((f, chip, c, col, f"${c:.2f}" + ("" if f == "m5" else f" · {c5/c:.1f}× más barato que m5"), grp))
    (OUT / "19a-arco.svg").write_text(frame(
        "ARCO GENERACIONAL", "De Graviton4 a Graviton5, la misma app hizo el doble",
        ["Java sin ajustes: peticiones por segundo en el punto de quiebre de cada familia .4xlarge; más largo = mejor",
         "Intel creció 2× en cuatro generaciones (m5 → m8i); Graviton, 2× en una sola (m8g → m9g)"],
        hbars(raw, 92000), "Fuente: lab propio, Task 8, 1 run por familia (m8g: 2 instancias, 40 mil rps cada una); orientativo"))
    (OUT / "19b-arco-por-dolar.svg").write_text(frame(
        "ARCO GENERACIONAL", "Con Java, cada petición en m9g cuesta un tercio que en m5",
        ["Costo del nodo por cada mil millones de peticiones, al punto de quiebre, on-demand us-east-1; más corto = mejor",
         "Si debes seguir en x86: m8a cuesta un tercio (2.96× por $); m8i, poco más de la mitad (1.81×)"],
        hbars(cost, 10.0), "Fuente: lab propio, Task 8, 1 run por familia; precios: AWS Pricing API; orientativo"))


if __name__ == "__main__":
    # titles and second lines: fuentes O-20, O-22, O-26 (Java), O-42 (Go), O-37/O-38 (PostgreSQL), O-27 (MongoDB), O-30..O-32 (inferencia)
    workload_chart("12-java", "JAVA", "Java: Graviton5 y EPYC atienden 1.7–2× lo que Xeon 6",
                   ["Spring REST: peticiones por segundo con el 99 % en menos de 10 ms; más alto = mejor",
                    "Sin ajustes, EPYC atiende 11 % más que Graviton5; con ajustes, empatan"],
                   "java", [("Sin ajustes", "stock"), ("Con ajustes (páginas grandes + JVM)", "tuned"),
                            ("Con ajustes + virtual threads", "tuned-vthreads")], "rps",
                   ("PetClinic REST, base H2 en memoria, heap de 24 GB · k6 sube de 10 mil en 10 mil hasta 120 mil peticiones/s",
                    "EPYC y Graviton5 hacen más trabajo por ciclo (IPC 1.35 y 1.25 contra 0.93) y tienen 16 núcleos reales; Xeon, 8 con SMT"))
    workload_chart("15-mongo", "MONGODB", "MongoDB: Graviton5 atiende 1.3× lo que EPYC y Xeon 6",
                   ["Operaciones por segundo con el 99 % de las lecturas en menos de 5 ms; más alto = mejor",
                    "EPYC y Xeon 6 empatan. En este punto, MongoDB no está limitado por la CPU"],
                   "mongo", [("Sin ajustes", "stock"), ("Con ajustes (páginas grandes)", "tuned")], "ops",
                   ("YCSB B: 20 M documentos (~20 GB) en caché, 95 % lecturas · de 16 a 512 hilos · quiebre en 128–256 hilos",
                    "Graviton5 hace más trabajo por ciclo (IPC 1.12 / 0.94 / 0.59), pero aquí la CPU no es el límite: por eso EPYC y Xeon empatan"))
    workload_chart("15a-inferencia", "INFERENCIA", "Llama 3.1 8B en CPU: Graviton5 genera ~2× los tokens de Xeon 6",
                   ["Tokens generados por segundo, sumados entre 4 usuarios a la vez (llama.cpp, Q4_0); más alto = mejor",
                    "Con ajustes, un millón de tokens cuesta $2.09 en Graviton5, $3.49 en EPYC y $4.09 en Xeon 6"],
                   "inference", [("Sin ajustes", "stock"), ("Con ajustes (15 hilos + páginas grandes)", "tuned")], "tok/s",
                   ("modelo de 4.7 GB · 4 usuarios a la vez, respuestas de 128 tokens, mismo prompt · runs de 6 minutos",
                    "sin ajustes, llama.cpp usa 8 hilos en Xeon y 16 en los otros; con 15 hilos, Graviton5 sigue arriba (IPC 1.01 / 0.82 / 0.62)"),
                   source="Fuente: lab propio, Task 7, 2 días × 3 runs de 6 min; barra = media de los 2 días, línea = mín–máx; $/M tokens: solo el nodo, on-demand")
    workload_chart("14-postgres", "POSTGRESQL", "PostgreSQL: aquí gana EPYC; Graviton5 empata con Xeon 6",
                   ["Transacciones por segundo (una lectura por índice cada una), con el 99 % en menos de 5 ms; más alto = mejor",
                    "Con ajustes y precios on-demand, por dólar EPYC rinde 1.52× el Xeon 6; Graviton5, 1.06×"],
                   "postgres", [("Sin ajustes", "stock"), ("Con ajustes (16 GB de buffers + páginas grandes)", "tuned")], "tps",
                   ("pgbench solo lectura, 100 M filas (~17 GB) en memoria · de 16 a 512 clientes · quiebre en 128–256 clientes, p99 ≈ 0.6 ms",
                    "EPYC y Graviton5 hacen el mismo trabajo por ciclo (IPC 1.00 y 1.04), pero EPYC va a 4.5 GHz contra 3.3: explica ~1.35× de 1.8×"))
    workload_chart("13-go", "GO", "Go: Graviton5 atiende 1.8× lo que Xeon 6",
                   ["Servicio HTTP: peticiones por segundo con el 99 % en menos de 20 ms; más alto = mejor",
                    "Go se midió solo sin ajustes"],
                   "go", [("Sin ajustes", "stock")], "rps",
                   ("servicio HTTP de la librería estándar, compilado genérico (sin flags por chip) · de 5 mil en 5 mil hasta 100 mil peticiones/s",
                    "Graviton5 hace más trabajo por ciclo (IPC 1.23 / 1.02 / 0.68) y falla menos al predecir saltos (1.1 / 2.4 / 3.2 por mil)"))
    per_dollar()
    tuning()
    net()
    arc_chart()
    print("\n".join(sorted(p.name for p in OUT.glob("*.svg"))))
