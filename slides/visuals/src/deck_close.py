"""Closing slides 17, 19-27 of ARMed and Dangerous (answers to the opening questions + close).

Run: python3 slides/visuals/src/deck_close.py  -> writes SVGs into slides/visuals/.
Every number below comes from slides/fuentes.md; the entry id (O-xx, 10.3, Parte 3 §n) is in a
comment next to it. Reuses HEAD / kicker / glyph_tile from gen.py so the look matches.
"""
import html
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from gen import HEAD, OUT, glyph_tile, kicker  # noqa: E402

VIOLET, TEAL, BLUE, AMBER = "#6D4AE8", "#0e9f9a", "#1f6fe5", "#d97706"   # Graviton / EPYC / Xeon / POR-CONFIRMAR

BASE_CSS = (
    ".hero{font-family:Montserrat,Inter,sans-serif;font-weight:700;fill:url(#tv-grad-h)}"
    ".cap{font-size:32px;fill:#15123C}"
    ".src{font-size:24px;fill:#5E5A80}"
    ".tag{font:24px 'JetBrains Mono',Menlo,monospace;fill:#6D4AE8}"
    ".tm{font:24px 'JetBrains Mono',Menlo,monospace;fill:#e6e9ef;white-space:pre;font-variant-ligatures:none}"
    ".pc{fill:none;stroke:#d97706;stroke-width:3;stroke-dasharray:12 8}"
    ".pct{font:600 24px 'JetBrains Mono',Menlo,monospace;fill:#d97706}"
    # play-once reveal; outside the media query everything is visible (= poster)
    "@media (prefers-reduced-motion: no-preference){"
    ".a{animation:in .7s cubic-bezier(.2,.7,.2,1) both}"
    ".ty{animation:ty .01s linear both}"
    "@keyframes in{from{opacity:0;transform:translateY(24px)}}"
    "@keyframes ty{from{opacity:0}}}"
)


def page(name, title, body, css=""):
    svg = (HEAD.replace("{title}", title).replace("{css}", BASE_CSS + css) + body + "\n</svg>\n")
    (OUT / f"{name}.svg").write_text(svg)


def header(k, h, sub):
    return (kicker(k) + f'<text x="96" y="140" class="h">{h}</text>\n'
            + f'<text x="96" y="192" class="sub">{sub}</text>\n')


def src(text, y=1000):
    return f'<text x="96" y="{y}" class="src">{text}</text>\n'


def a(delay, inner, cls="a"):
    """Group revealed at `delay` seconds (play-once)."""
    return f'<g class="{cls}" style="animation-delay:{delay:.2f}s">{inner}</g>\n'


def por_confirmar(x, y, w, h, label):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" class="pc"/>'
            f'<text x="{x + w / 2}" y="{y + h / 2 - 6}" text-anchor="middle" class="pct">POR-CONFIRMAR</text>'
            f'<text x="{x + w / 2}" y="{y + h / 2 + 30}" text-anchor="middle" class="c">{label}</text>')


def card(x, y, w, h, extra=""):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="20" class="card"{extra}/>'


# ---------------------------------------------------------------- terminal frame (type 18)
TC = {"p": "#a78bfa", "t": "#e6e9ef", "d": "#8b95a7", "err": "#f87171", "ok": "#34d399", "hi": "#fbbf24"}


def terminal(x, y, w, lines, t0=0.4, step=0.32, lh=38):
    """lines: list of [(text, color-key), ...]; each line appears in turn (typing feel)."""
    h = 64 + lh * len(lines) + 24
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="18" fill="#15123C" filter="url(#sh)"/>',
           f'<rect x="{x}" y="{y}" width="{w}" height="48" rx="18" fill="#232b36"/><rect x="{x}" y="{y + 30}" width="{w}" height="18" fill="#232b36"/>']
    out += [f'<circle cx="{x + 30 + i * 26}" cy="{y + 24}" r="8" fill="{c}"/>' for i, c in enumerate(("#f87171", "#fbbf24", "#34d399"))]
    for i, segs in enumerate(lines):
        spans = "".join(f'<tspan fill="{TC[k]}">{html.escape(s)}</tspan>' for s, k in segs)
        out.append(a(t0 + i * step, f'<text x="{x + 32}" y="{y + 64 + 26 + i * lh}" class="tm">{spans}</text>', "ty"))
    return "\n".join(out) + "\n", h, t0 + len(lines) * step


# ---------------------------------------------------------------- 17 ¿Precio?
def precio():
    b = header("¿PRECIO?", "¿Precio? Más trabajo por cada dólar",
               "Graviton5 (m9g) frente a Xeon 6 (m8i), mismo tamaño .4xlarge, on-demand us-east-1")
    # headline.md per $ arm/x86: go 1.97, java tuned-vthreads 2.11 (O-26), java tuned 1.80, inference tuned 1.96 / stock 2.36,
    # mongo tuned 1.36, postgres tuned 1.06 (amd 1.52, O-38); net: Gbps/$ derived from O-40 + cost.md prices
    b += a(.2, '<text x="84" y="520" font-size="250" class="hero">~2×</text>')
    b += a(.6, '<text x="96" y="600" class="cap">por dólar en Go, Java e inferencia:</text>'
               '<text x="96" y="642" class="cap">cerca de la mitad del costo por unidad de trabajo</text>'
               '<text x="96" y="700" class="c">m9g cuesta 7.6 % menos por hora que m8i y además rinde más</text>')
    rows = [("1.97×", VIOLET, "Go", "sin ajustes"),
            ("2.11×", VIOLET, "Java", "con ajustes + virtual threads (1.80× sin ellos)"),
            ("1.96×", VIOLET, "Inferencia", "con ajustes; 2.36× sin ajustes"),
            ("1.36×", VIOLET, "MongoDB", "con ajustes"),
            ("1.06×", "#5E5A80", "PostgreSQL", "aquí gana EPYC: 1.52× por dólar"),
            ("1.23×", VIOLET, "Red", "Gbps por dólar; tope de la instancia, 1 día")]
    for i, (v, col, t, c) in enumerate(rows):
        y = 226 + i * 96
        b += a(1.0 + i * .18, card(1000, y, 824, 84)
               + f'<text x="1030" y="{y + 60}" font-size="46" font-weight="700" fill="{col}">{v}</text>'
               + f'<text x="1220" y="{y + 38}" font-size="28" font-weight="600" fill="#15123C">{t}</text>'
               + f'<text x="1220" y="{y + 68}" class="c">{c}</text>')
    # headline.md "Per $ at Spot" (weekly median us-east-1, 2026-09-22..30)
    b += a(2.3, card(96, 840, 1728, 104)
           + f'<rect x="96" y="840" width="10" height="104" rx="5" fill="{TEAL}"/>'
           + '<text x="136" y="882" font-size="28" font-weight="600" fill="#15123C">En Spot, EPYC supera a Graviton5 en Java sin ajustes</text>'
           + '<text x="136" y="920" class="c">Mediana semanal us-east-1: Java sin ajustes, EPYC 1.99× contra Graviton5 1.86×; Go, inferencia y MongoDB siguen con Graviton5</text>')
    b += src("Fuente: medido en el lab, Task 7, 2 días × 3 runs (red: 1 día); precios on-demand y Spot: AWS Pricing API y EC2 API, us-east-1")
    page("17-precio", "¿Precio? Más trabajo por cada dólar", b)


# ---------------------------------------------------------------- 19 ¿Rendimiento?
def rendimiento():
    b = header("¿RENDIMIENTO?", "¿Rendimiento? La misma app, desde un m5",
               "Si hoy corres Java en un m5: cuánto ganas al moverte (Java sin ajustes, 1 run por familia: orientativo)")
    # O-44 (headline.md:36): m9g 3.33x m5 raw; O-45 per $ 3.27x
    b += a(.2, '<text x="96" y="318" font-size="44" fill="#5E5A80">m5 → m9g</text>'
               '<text x="84" y="540" font-size="250" class="hero">3.3×</text>')
    b += a(.6, '<text x="96" y="610" class="cap">Graviton5, la misma app sin tocar:</text>'
               '<text x="96" y="652" class="cap">24 mil → 80 mil rps; 3.27× por dólar</text>')
    # O-44 x86 path: m8a 3.75x (90k), m8i 2.0x (48k); O-45 per $ 2.96x / 1.81x
    # O-44 / O-45: m8a 3.75x (2.96x per $), m8i 2.0x (1.81x), m8g 1.67x (1.78x)
    rows = [("3.75×", TEAL, "m5 → m8a (EPYC)", "el salto más grande en crudo; 2.96× por $"),
            ("2.0×", BLUE, "m5 → m8i (Xeon 6)", "el salto en Xeon, sigue en x86; 1.81× por $"),
            ("1.67×", VIOLET, "m5 → m8g (Graviton4)", "la generación anterior de Graviton; 1.78× por $")]
    for i, (v, col, t, c) in enumerate(rows):
        y = 226 + i * 160
        b += a(1.0 + i * .3, card(1120, y, 704, 140)
               + f'<rect x="1120" y="{y}" width="10" height="140" rx="5" fill="{col}"/>'
               + f'<text x="1156" y="{y + 94}" font-size="80" class="hero">{v}</text>'
               + f'<text x="1420" y="{y + 58}" class="t">{t}</text><text x="1420" y="{y + 94}" class="c">{c.split("; ")[0]}</text>'
               + f'<text x="1420" y="{y + 124}" class="c">{c.split("; ")[1]}</text>')
    # O-01 + Parte 3 §2 (Phoronix +30% geomean) + §4 (Honeycomb 11-26% less CPU); "no decir" #10 / Parte 3 #1
    b += a(1.9, card(96, 760, 1728, 176)
           + '<rect x="96" y="760" width="10" height="176" rx="5" fill="#6D4AE8"/>'
           + '<text x="136" y="822" font-size="34" font-weight="600" fill="#15123C">Graviton5 frente a Graviton4 (m8g): 2× en nuestra carga, ~30 % en suites amplias</text>'
           + '<text x="136" y="870" class="c">Medido: 80 mil contra 40 mil rps, repetido en 2 nodos m8g. Terceros: Phoronix +30 % de media geométrica (140+ pruebas);</text>'
           + '<text x="136" y="904" class="c">Honeycomb, 11–26 % menos CPU en producción. Decide tu carga.</text>')
    b += src("Fuente: medido en el lab, Task 8 (arco, 2026-09-28, 1 run por familia); terceros: Phoronix 2026-07-09, Honeycomb 2026-06-10")
    page("19-rendimiento", "¿Rendimiento? La misma app, desde un m5", b)


# ---------------------------------------------------------------- 20 ¿Compatibilidad?
def side_cards(x, y0, w, items, t0):
    """Right-column cards: (label, title, lines). Returns svg."""
    out, y = "", y0
    for i, (lbl, t, lines) in enumerate(items):
        h = 110 + 32 * len(lines)
        out += a(t0 + i * .3, card(x, y, w, h)
                 + f'<text x="{x + 28}" y="{y + 40}" class="tag" style="font-size:20px">{lbl}</text>'
                 + f'<text x="{x + 28}" y="{y + 78}" font-size="27" font-weight="600" fill="#15123C">{t}</text>'
                 + "".join(f'<text x="{x + 28}" y="{y + 112 + j * 32}" class="c">{ln}</text>' for j, ln in enumerate(lines)))
        y += h + 20
    return out


def compatibilidad():
    b = header("¿COMPATIBILIDAD?", "¿Compatibilidad? Lo que se rompe está fuera de tu app",
               "Un DaemonSet con imagen solo amd64, en un clúster con nodos x86 y Graviton")
    # O-51 / O-52: daemonset-blocker.txt:26-42 (NODE ip column dropped; node arch/type from :1-5)
    L = [
        [("$ ", "p"), ("kubectl apply -f legacy-agent-daemonset.yaml", "t")],
        [("$ ", "p"), ("kubectl get pods -l app=legacy-agent", "t")],
        [("NAME                READY  STATUS   RESTARTS", "d")],
        [("legacy-agent-6xcqj  0/1    ", "t"), ("Error  ", "err"), ("  3   ", "t"), ("# arm64 · m6g", "d")],
        [("legacy-agent-8tglw  1/1    ", "t"), ("Running", "ok"), ("  0   ", "t"), ("# amd64 · m6i", "d")],
        [("legacy-agent-d62ht  0/1    ", "t"), ("Error  ", "err"), ("  3   ", "t"), ("# arm64 · m7g", "d")],
        [("$ ", "p"), ("kubectl logs legacy-agent-6xcqj", "t")],
        [("exec /bin/sh: exec format error", "err")],
    ]
    t, h, end = terminal(96, 230, 1040, L)
    b += t
    y = 230 + h
    b += a(end + .2, f'<text x="96" y="{y + 56}" font-size="30" fill="#15123C">La imagen se descargó sin error;</text>'
                     f'<text x="96" y="{y + 96}" font-size="30" fill="#15123C">el fallo apareció al arrancar el contenedor.</text>')
    # facts-setup §3.4 + apps/build-multiarch.sh:108 (go-ycsb amd64 only); §3.3 + O-35 (KleidiAI own build, no gain)
    b += side_cards(1176, 230, 648, [
        ("[EN ESTA ESCENA]", "Agentes y DaemonSets", ["monitoreo, seguridad, logs: si uno", "es solo amd64, falla en cada nodo arm"]),
        ("[EN EL LAB]", "El generador de carga", ["construimos go-ycsb solo para amd64:", "el loader se quedó en x86"]),
        ("[OPCIONAL]", "Optimizaciones por chip", ["para activar KleidiAI compilamos otra", "imagen; en calibración, sin ganancia"]),
    ], end + .4)
    # Parte 4 B.8 (Docker Docs: buildx --platform; imagetools inspect lists one entry per platform)
    b += a(end + 1.4, f'<rect x="96" y="868" width="1728" height="72" rx="36" fill="url(#tv-grad-h)"/>'
                      f'<text x="132" y="914" font-size="26" font-weight="600" fill="#fff">Antes de migrar</text>'
                      f'<text x="360" y="914" class="tm" style="fill:#fff">docker buildx imagetools inspect &lt;imagen&gt;</text>'
                      f'<text x="1060" y="914" font-size="24" fill="#fff">lista las plataformas de cada imagen</text>')
    b += src("Fuente: escena medida en el lab, Task 9, 2026-09-28 (salida real de kubectl, columnas acortadas); buildx: Docker Docs")
    page("20-compatibilidad", "¿Compatibilidad? Lo que se rompe está fuera de tu app", b)
    return end + 1.8


# ---------------------------------------------------------------- 21 ¿Esfuerzo? (x86 -> arm)
def esfuerzo():
    b = header("¿ESFUERZO?", "¿Esfuerzo? De x86 a ARM, una línea por manifiesto",
               "Con imágenes multi-arch listas, solo cambió el nodeSelector en Java, Go, PostgreSQL y MongoDB")
    # manifests/workloads/{java,go,postgres,mongo}/overlays/{x86,arm}-stock/kustomization.yaml: only aad/cell differs
    L = [
        [("$ ", "p"), ("diff overlays/x86-stock/ overlays/arm-stock/", "t")],
        [("  spec:", "d")],
        [("    nodeSelector:", "d")],
        [("-     aad/cell: x86-stock", "err")],
        [("+     aad/cell: arm-stock", "ok")],
        [("# misma etiqueta de imagen, mismos recursos", "d")],
    ]
    t, h, end = terminal(96, 230, 1040, L)
    b += t
    # apps/build-multiarch.sh:108-109 (buildx linux/amd64,linux/arm64); facts-setup §3.1-3.5 (official multi-arch images)
    b += side_cards(1176, 230, 648, [
        ("[LO QUE HICIMOS]", "Una imagen para los dos", ["buildx --platform linux/amd64,linux/arm64;", "Postgres, Mongo y llama.cpp ya vienen así"]),
        ("[LO QUE NO TOCAMOS]", "El código de las apps", ["Java: mismo JAR.", "Go: un binario por arquitectura, mismo código"]),
        ("[LO QUE SÍ CAMBIA]", "Los ajustes finos", ["los flags de JVM se eligen por chip;", "sin ajustes, solo cambia el nodeSelector"]),
    ], end + .3)
    # O-48 / O-49 / O-44 / O-47: Karpenter chose m6g (cheapest); m6g 0.92x m5 vs m9g 3.33x (arc, 1 run per family)
    y = 230 + h + 40
    b += a(end + 1.3, card(96, y, 1040, 190)
           + f'<rect x="96" y="{y}" width="10" height="190" rx="5" fill="{VIOLET}"/>'
           + f'<text x="132" y="{y + 50}" class="tag" style="font-size:20px">[DÓNDE ESTÁ EL TRABAJO]</text>'
           + f'<text x="132" y="{y + 92}" font-size="27" font-weight="600" fill="#15123C">Antes: imágenes multi-arch y dependencias revisadas</text>'
           + f'<text x="132" y="{y + 128}" class="c">Después: mover un servicio, medir su punto de quiebre</text>'
           + f'<text x="132" y="{y + 162}" class="c">y seguir con el siguiente.</text>')
    b += a(end + 1.7, f'<rect x="96" y="868" width="1728" height="72" rx="36" fill="url(#tv-grad-h)"/>'
                      f'<text x="132" y="914" font-size="26" font-weight="600" fill="#fff">Node groups x86 y arm en el mismo clúster: migras servicio por servicio, sin big-bang</text>')
    b += src("Fuente: manifiestos del lab (overlays x86-stock y arm-stock); apps/build-multiarch.sh (buildx linux/amd64,linux/arm64)")
    page("21-esfuerzo", "¿Esfuerzo? De x86 a ARM, una línea por manifiesto", b)
    return end + 2.1


# ---------------------------------------------------------------- 21b ¿Y si corro en Fargate?
def fargate():
    b = header("¿Y FARGATE?", "¿Y si corro en Fargate? No eliges la generación",
               "Lo medido aquí es EC2. En ECS Fargate eliges x86 o Arm, pero AWS elige la generación")
    # fuentes F-01..F-09 (docs EKS/ECS Fargate, FAQ, pricing, containers-roadmap #2230, #1030, #2019)
    cols = [(96, "EKS + FARGATE", "#d97706", "Sin Arm", ["La tabla de EKS dice: «Arm processors: No».",
             "Tampoco DaemonSets ni Fargate Spot.", "Para Graviton en EKS: nodos EC2,", "como en este lab."]),
            (996, "ECS + FARGATE", VIOLET, "Arm sí: cpuArchitecture ARM64", ["20 % menos por vCPU y GB que x86;",
             "AWS dice «hasta 40 %» mejor precio-", "rendimiento (cifra de AWS, no medida aquí).", "Spot con Graviton: sí."])]
    for i, (x, k, col, t, lines) in enumerate(cols):
        b += a(.3 + i * .35, card(x, 230, 828, 330)
               + f'<rect x="{x}" y="230" width="828" height="10" rx="5" fill="{col}"/>'
               + f'<text x="{x + 36}" y="292" class="k" style="fill:{col}">[{k}]</text>'
               + f'<text x="{x + 36}" y="346" font-size="36" font-weight="700" fill="#15123C">{t}</text>'
               + "".join(f'<text x="{x + 36}" y="{400 + j * 38}" class="c" style="font-size:26px">{ln}</text>' for j, ln in enumerate(lines)))
    # the dynamic fleet: #2230 (AWS comment + user measurement), #2019 (user report)
    b += a(1.1, card(96, 590, 1728, 230)
           + f'<rect x="96" y="590" width="10" height="230" rx="5" fill="{VIOLET}"/>'
           + '<text x="136" y="640" class="tag" style="font-size:20px">[EL HARDWARE ES DINÁMICO · GITHUB aws/containers-roadmap #2230]</text>'
           + '<text x="136" y="690" font-size="28" font-weight="600" fill="#15123C">AWS anunció la incorporación de Graviton3 a Fargate en 2024: «We added Graviton 3 to Fargate fleet»</text>'
           + '<text x="136" y="734" class="c" style="font-size:26px">En pruebas pequeñas de octubre de 2024, un usuario observó Graviton2 y Graviton3 en ECS Fargate</text>'
           + '<text x="136" y="774" class="c" style="font-size:26px">Un usuario identificó la instancia con:</text>'
           + '<text x="590" y="774" class="m" style="fill:#6D4AE8">cat /sys/class/dmi/id/product_name</text>'
           + '<text x="1100" y="774" class="c" style="font-size:26px">(sin garantía de AWS)</text>')
    b += a(1.5, '<rect x="96" y="850" width="1728" height="72" rx="36" fill="url(#tv-grad-h)"/>'
                '<text x="132" y="896" font-size="26" font-weight="600" fill="#fff">¿Necesitas elegir generación? EKS con nodos EC2 o ECS Managed Instances (tipo y fabricante)</text>')
    b += src("Fuente: docs de EKS y ECS sobre Fargate, FAQ y precios de Fargate (30-09-2026); GitHub aws/containers-roadmap #2230, #1030, #2019", y=990)
    page("21b-fargate", "¿Y si corro en Fargate? No eliges la generación", b)


# ---------------------------------------------------------------- 22 conclusiones (stat row)
def conclusiones():
    b = header("CONCLUSIONES", "Lo que medimos en los tres chips",
               "Mismo tamaño .4xlarge, 16 vCPU, siete workloads; precios on-demand us-east-1")
    # Graviton5: O-55 per $ vs Xeon (Go 1.97, Java 1.80/2.11, inference 1.96, Mongo 1.36) + O-41 net CPU/Gbps 1/3; O-53 geomean 1.59x
    # EPYC: O-20 Java stock 89k vs 80k; O-37/O-38 PG 1.75x raw, 1.52x per $; O-53 raw arm/amd 1.04x
    # Xeon 6: O-03 8 cores + SMT; last or tied in every workload (headline.md)
    cards = [("GRAVITON5", VIOLET, "~2×", "por dólar frente a Xeon 6",
              ["en Go, Java e inferencia; lidera", "por dólar en 6 de 7 escenarios", "(media geom., 5 clases: 1.59×)"]),
             ("EPYC", TEAL, "1.75×", "Xeon 6 en PostgreSQL con ajustes",
              ["el más rápido en PostgreSQL y", "en Java sin ajustes; en promedio,", "similar a Graviton5"]),
             ("XEON 6", BLUE, "8 + SMT", "contra 16 núcleos físicos",
              ["mismas 16 vCPU, la mitad de", "núcleos: último o empatado", "en los siete workloads"])]
    for i, (k, col, v, cap, lines) in enumerate(cards):
        x = 96 + i * 588
        body = (card(x, 250, 552, 560)
                + f'<rect x="{x}" y="250" width="552" height="10" rx="5" fill="{col}"/>'
                + f'<text x="{x + 36}" y="320" class="k" fill="{col}" style="fill:{col}">[{k}]</text>'
                + f'<text x="{x + 30}" y="470" font-size="100" class="hero">{v}</text>'
                + f'<text x="{x + 36}" y="530" class="t">{cap}</text>'
                + "".join(f'<text x="{x + 36}" y="{640 + j * 40}" class="cap" style="font-size:28px">{ln}</text>' for j, ln in enumerate(lines)))
        b += a(.3 + i * .45, body)
    b += a(1.8, '<text x="96" y="880" font-size="30" font-weight="600" fill="#15123C">El chip conveniente depende de tu carga: mide tu punto de quiebre.</text>')
    b += src("Fuente: medido en el lab, Task 7, 2 días × 3 runs (red: 1 día); precios on-demand us-east-1 (AWS Pricing API)")
    page("22-conclusiones", "Lo que medimos en los tres chips", b)


# ---------------------------------------------------------------- 23 recomendaciones (numbered outcomes)
def recomendaciones():
    b = header("RECOMENDACIONES", "Qué haría según tu punto de partida",
               "Rutas de la guía de decisión; las cifras del arco son Java sin ajustes frente a m5.4xlarge, mismo JDK")
    # decision-guide.md routes; O-56 (m8a 3.75x from m5), O-44/O-45 (m9g 3.33x), O-37 + O-09 (PG), O-32 ($/M tokens), O-51
    rows = [("Tienes que seguir en x86 (por el proveedor o la licencia)", "m8a; y si puedes, JDK 17+ antes de moverte", "3.75× m5", "[Java · arco]"),
            ("Java o Go con imágenes multi-arch", "m9g, con la familia fijada en Karpenter (si no, eligió m6g)", "3.3× m5", "[Java · arco]"),
            ("PostgreSQL", "m8a + shared_buffers de 16 GB y páginas grandes (+19 %)", "1.75× Xeon 6", "[ambos con ajustes]"),
            ("Generación de tokens en CPU", "m9g, y fija los hilos (-t) al tamaño del pod", "$2.09 / M tokens", "[Llama 3.1 8B · con ajustes]"),
            ("Antes de migrar", "imágenes multi-arch, DaemonSets y agentes incluidos", "exec format error", "[escena]")]
    for i, (t, c, m, tag) in enumerate(rows):
        y = 226 + i * 140
        mfs = 50 if len(m) < 10 else 36
        body = (card(96, y, 1728, 124)
                + f'<rect x="124" y="{y + 22}" width="80" height="80" rx="14" fill="url(#tv-grad)"/>'
                + f'<text x="164" y="{y + 76}" text-anchor="middle" font-size="34" font-weight="700" fill="#fff">0{i + 1}</text>'
                + f'<text x="236" y="{y + 54}" class="t">{t}</text><text x="236" y="{y + 94}" class="c">{c}</text>'
                + f'<text x="1792" y="{y + 64}" text-anchor="end" font-size="{mfs}" class="hero">{m}</text>'
                + f'<text x="1792" y="{y + 102}" text-anchor="end" class="tag" style="font-size:20px">{tag}</text>')
        b += a(.3 + i * .35, body)
    b += src("Fuente: guía de decisión del lab; Task 7 (2 días × 3 runs) y Task 8 (arco, 1 run por familia: orientativo); $/M tokens: solo el nodo, on-demand")
    page("23-recomendaciones", "Qué haría según tu punto de partida", b)


# ---------------------------------------------------------------- 24 aprendizajes (takeaways)
G_LOADER = '<path d="M16 30 H58 M48 20 L58 30 L48 40 M64 52 H22 M32 42 L22 52 L32 62"/>'
G_SLIDERS = '<path d="M18 24 H62 M18 40 H62 M18 56 H62"/><circle cx="30" cy="24" r="6"/><circle cx="50" cy="40" r="6"/><circle cx="36" cy="56" r="6"/>'
G_DIAL = '<circle cx="40" cy="42" r="20"/><path d="M40 42 L52 28 M40 14 V18 M18 26 L21 29 M62 26 L59 29"/>'
G_KNEE = '<path d="M16 16 V62 H66"/><path d="M20 58 C38 56 48 48 54 34 L60 18"/><path d="M44 18 V62" stroke-dasharray="4 5"/>'
G_DISK = '<ellipse cx="40" cy="22" rx="22" ry="8"/><path d="M18 22 V58 A22 8 0 0 0 62 58 V22 M18 40 A22 8 0 0 0 62 40"/>'
G_TERM = '<rect x="12" y="16" width="56" height="48" rx="4"/><path d="M22 32 L32 40 L22 48 M38 50 H56"/>'
G_DAYS = '<rect x="12" y="22" width="26" height="36" rx="3"/><rect x="42" y="22" width="26" height="36" rx="3"/><path d="M18 32 H32 M48 32 H62"/>'


def aprendizajes():
    b = header("APRENDIZAJES", "Lo que aprendimos midiendo CPUs en Kubernetes",
               "Sirve para cualquier benchmark que hagas en tu clúster")
    # facts-history.md §5; evidence: fuentes O-12 + facts-setup §4.4 (2 YCSB clients: 191.1k vs 242.2k), O-33, O-29, O-11,
    # Phoronix "Linux 7.0 Shows Significant PostgreSQL Performance Gains On AMD EPYC" + facts-setup kernel 6.18, O-18, O-15/O-22
    rows = [(G_LOADER, "El loader es el primer sospechoso",
             "si pasa del 70 % de CPU, el run no cuenta; un cliente YCSB topaba en 191 mil ops/s, dos llegaron a 242 mil"),
            (G_SLIDERS, "«Sin ajustes» no es neutral: los defaults ya eligen por ti",
             "llama.cpp sin -t usó 8 hilos en el Xeon y 16 en Graviton5 y EPYC"),
            (G_DISK, "Revisa el disco antes de culpar al chip",
             "MongoDB en gp3 de 125 MiB/s dio 134 mil de 194 mil ops/s; con 1000 MiB/s, los runs se sostuvieron"),
            (G_DIAL, "Mide la perilla en tu carga",
             "la de red de un runbook de latencia costó 2.2× CPU por Gbps en Graviton5 (1 día)"),
            (G_TERM, "El kernel también es parte del benchmark",
             "Phoronix: Linux 7.0 mejoró PostgreSQL (lectura/escritura) en otro EPYC frente a 6.19; aquí: 6.18, solo lecturas"),
            (G_KNEE, "Define el punto de quiebre antes de mirar los datos",
             "el mayor rendimiento que cumple el SLO de p99: 10 ms Java, 20 ms Go, 5 ms las bases"),
            (G_DAYS, "Dos instancias en días distintos deciden los empates",
             "de un día a otro, 0–8 %; Java con ajustes m9g contra m8a: 0.98×, dentro del ruido")]
    for i, (g, t, e) in enumerate(rows):
        y = 226 + i * 104
        b += a(.3 + i * .3, glyph_tile(96, y + 6, g, 64)
               + f'<text x="190" y="{y + 34}" font-size="30" font-weight="600" fill="#15123C">{t}</text>'
               + f'<text x="190" y="{y + 70}" class="tag" style="fill:#5E5A80;font-size:21px">{e}</text>')
    b += src("Fuente: medido en el lab (Task 7 y calibración; guardas del runner); kernel: Phoronix, «Linux 7.0 … PostgreSQL … AMD EPYC»")
    page("24-aprendizajes", "Lo que aprendimos midiendo CPUs en Kubernetes", b)


# ---------------------------------------------------------------- 25 casos futuros (question cards, static)
def casos_futuros():
    b = header("LO QUE SIGUE", "Python y MySQL: pendientes de medir",
               "Lo que queremos averiguar y lo que ya sabemos")
    # MySQL: O-37/O-38 (PostgreSQL: AMD wins); Python: Parte 3 §2 (PyPerformance, Phoronix, third party)
    cols = [("Python", "¿Qué chip rinde mejor con Python?",
             ["¿Todas tus dependencias nativas tienen", "paquetes compilados para arm64?"],
             ["Phoronix: m9g superó a m8g", "en PyPerformance (terceros)"]),
            ("MySQL", "¿EPYC también lidera en MySQL?",
             ["¿O su ventaja era de PostgreSQL", "y no de las bases relacionales?"],
             ["PostgreSQL con ajustes: EPYC 1.75×", "Xeon 6; Graviton5 y Xeon 6 empataron"])]
    for i, (name, q, q2, know) in enumerate(cols):
        x = 96 + i * 882
        body = (card(x, 240, 846, 560)
                + f'<path d="M{x} 336 V260 a20 20 0 0 1 20 -20 H{x + 826} a20 20 0 0 1 20 20 V336 Z" fill="url(#tv-grad)"/>'
                + f'<text x="{x + 36}" y="304" font-size="40" font-weight="700" fill="#fff">{name}</text>'
                + f'<rect x="{x + 560}" y="266" width="252" height="44" rx="22" fill="#fff" fill-opacity=".92"/><text x="{x + 686}" y="296" text-anchor="middle" font-size="24" font-weight="600" fill="#6D4AE8">no medido todavía</text>'
                + f'<text x="{x + 36}" y="410" font-size="34" font-weight="700" fill="#15123C">{q}</text>'
                + "".join(f'<text x="{x + 36}" y="{464 + j * 40}" class="cap" style="font-size:28px;fill:#5E5A80">{ln}</text>' for j, ln in enumerate(q2))
                + f'<rect x="{x + 36}" y="560" width="774" height="196" rx="16" fill="#F6F4FE" stroke="#DCD6F7" stroke-width="1.5"/>'
                + f'<text x="{x + 64}" y="610" class="k" style="fill:#6D4AE8;font-size:22px">LO QUE YA SABEMOS</text>'
                + "".join(f'<text x="{x + 64}" y="{662 + j * 40}" class="cap" style="font-size:28px">{ln}</text>' for j, ln in enumerate(know)))
        b += a(.3 + i * .4, body)
    b += src("Fuente: PostgreSQL medido en el lab (Task 7); PyPerformance: Phoronix, 2026-07-09 (terceros)")
    page("25-casos-futuros", "Python y MySQL: pendientes de medir", b)


# ---------------------------------------------------------------- 26 siguientes pasos (resources + first steps)
def siguientes():
    b = header("PARA LLEVAR", "Repite el lab en tu carga",
               "Todo está en el repo: código, datos crudos, análisis y fuentes")
    n, path = (OUT / "assets/repo-qr.path").read_text().split("\n", 1)
    k = 380 / int(n)   # 41 modules incl. 4-module quiet zone -> 380 px
    b += (card(96, 240, 460, 460) + f'<g transform="translate(136 256) scale({k:.4f})"><path d="{path}" fill="#15123C"/></g>'
          + '<text x="326" y="672" text-anchor="middle" class="m" style="font-size:16px;fill:#6D4AE8">github.com/andrezc98/armed-and-dangerous</text>')
    items = [("El repo del lab", "Código, manifiestos y datos de cada run", "github.com/andrezc98/armed-and-dangerous"),
             ("La guía de decisión", "Rutas y mediciones por stack: «corro X hoy, ¿qué gano?»", "analysis/decision-guide.md"),
             ("Las fuentes verificadas", "Fuentes y alcance de cada cifra de esta charla", "slides/fuentes.md")]
    for i, (t, c, pth) in enumerate(items):
        y = 240 + i * 160
        b += a(.3 + i * .25, card(600, y, 1224, 140) + glyph_tile(630, y + 32, '<path d="M24 20 H46 L58 32 V62 H24 Z M46 20 V32 H58"/>', 76)
               + f'<text x="736" y="{y + 50}" class="t">{t}</text><text x="736" y="{y + 88}" class="c">{c}</text>'
               + f'<text x="736" y="{y + 122}" class="m" style="fill:#6D4AE8">{pth}</text>')
    # first steps: build-multiarch.sh (imagetools inspect), O-51 (mixed node groups), O-18 (breaking point)
    steps = [("1", "Revisa tus imágenes", "amd64 y arm64 en cada una"),
             ("2", "Agrega un node group arm64", "m9g junto al grupo x86"),
             ("3", "Mide tu punto de quiebre", "tu SLO en ambas instancias")]
    b += a(1.2, '<text x="96" y="772" class="k" style="fill:#6D4AE8">[EL LUNES]</text>')
    for i, (n, t, c) in enumerate(steps):
        x = 96 + i * 588
        b += a(1.4 + i * .25, card(x, 796, 552, 130)
               + f'<circle cx="{x + 56}" cy="861" r="30" fill="url(#tv-grad)"/><text x="{x + 56}" y="872" text-anchor="middle" font-size="30" font-weight="700" fill="#fff">{n}</text>'
               + f'<text x="{x + 110}" y="850" font-size="27" font-weight="600" fill="#15123C">{t}</text>'
               + f'<text x="{x + 110}" y="890" class="c">{c}</text>')
    page("26-siguientes-pasos", "Repite el lab en tu carga", b)


# ---------------------------------------------------------------- 28 feedback (static)
def feedback():
    b = header("TU OPINIÓN", "¿Qué te pareció la charla?",
               "Escanea el código y déjanos tu feedback: nos ayuda a mejorar la próxima")
    # QR provided by the event (Sessionize feedback code), embedded as-is
    b += card(660, 240, 600, 660)
    b += '<image href="assets/feedback-qr.png" x="690" y="262" width="540" height="560" preserveAspectRatio="xMidYMid meet"/>'
    b += '<text x="960" y="870" text-anchor="middle" class="m" style="font-size:22px;fill:#6D4AE8">escanea para calificar esta sesión</text>'
    b += ('<text x="96" y="1000" class="src">Andrés Zeballos · in/andreszc · github.com/andrezc98</text>'
          '<text x="1824" y="1000" text-anchor="end" class="src">Victor Herrera · in/victor-herreraa · github.com/VotircH</text>')
    page("28-feedback", "¿Qué te pareció la charla?", b)


# ---------------------------------------------------------------- 27 gracias (thank you, loop)
def gracias():
    sweep = ('<linearGradient id="sw" gradientUnits="userSpaceOnUse" x1="1150" y1="0" x2="1920" y2="1080"><stop offset="0" stop-color="#4C2FC9"/><stop offset=".5" stop-color="#6D4AE8"/><stop offset="1" stop-color="#A78BFA"/></linearGradient>'
             '<g class="sweep">'
             '<circle cx="2350" cy="540" r="1150" fill="none" stroke="url(#sw)" stroke-width="10" opacity=".35"/>'
             '<circle cx="2350" cy="540" r="1030" fill="none" stroke="url(#sw)" stroke-width="140" opacity=".9"/>'
             '<circle cx="2350" cy="540" r="880" fill="none" stroke="url(#sw)" stroke-width="60" opacity=".55"/>'
             '<circle cx="2350" cy="540" r="790" fill="none" stroke="url(#sw)" stroke-width="18" opacity=".3"/></g>\n')
    css = ("@media (prefers-reduced-motion: no-preference){.sweep{animation:drift 12s ease-in-out infinite;transform-origin:2350px 540px}"
           "@keyframes drift{0%,100%{transform:rotate(0) translateX(0)}50%{transform:rotate(-7deg) translateX(-30px)}}}")
    b = sweep + kicker("ARMED AND DANGEROUS", y=300)
    b += '<text x="96" y="430" font-size="120" font-weight="700" fill="#15123C">Gracias</text>\n'
    b += '<text x="96" y="500" class="sub" style="font-size:32px">Tres chips, siete workloads, un mismo clúster EKS</text>\n'
    b += '<text x="96" y="640" font-size="44" font-weight="600" fill="#15123C">Andrés Zeballos</text>'
    b += '<text x="96" y="744" class="m" style="fill:#6D4AE8">in/andreszc</text><text x="96" y="782" class="m" style="fill:#6D4AE8">github.com/andrezc98</text>'
    b += '<text x="96" y="688" font-size="28" fill="#5E5A80">Solutions Architect · phData</text>'
    b += '<text x="640" y="640" font-size="44" font-weight="600" fill="#15123C">Victor Herrera</text>'
    b += '<text x="640" y="688" font-size="28" fill="#5E5A80">Cloud Specialist · Caleidos</text>'
    b += '<text x="640" y="744" class="m" style="fill:#6D4AE8">in/victor-herreraa</text><text x="640" y="782" class="m" style="fill:#6D4AE8">github.com/VotircH</text>'
    b += '<text x="96" y="930" class="m" fill="#5E5A80" style="fill:#5E5A80">ACD Perú · 3 de octubre de 2026 · Colaboratorio</text>\n'
    svg = (HEAD.replace("{title}", "Gracias").replace("{css}", BASE_CSS + css)
           .replace('<circle cx="1860" cy="40" r="820" fill="url(#tv-glow-a)"/>', "")  # theme: no glow-a on sweep slides
           + b + "\n</svg>\n")
    (OUT / "27-gracias.svg").write_text(svg)


if __name__ == "__main__":
    precio()
    rendimiento()
    t20 = compatibilidad()
    t21 = esfuerzo()
    fargate()
    conclusiones()
    recomendaciones()
    aprendizajes()
    casos_futuros()
    siguientes()
    gracias()
    feedback()
    print(f"ok (20 ends {t20:.1f}s, 21 ends {t21:.1f}s)")
