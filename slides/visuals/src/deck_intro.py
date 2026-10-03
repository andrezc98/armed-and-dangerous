"""Intro slides 01-11 for ARMed and Dangerous (talk-visuals skill). Run: python3 slides/visuals/src/deck_intro.py

Every figure carries the slides/fuentes.md entry it comes from in a comment next to it.
Reuses HEAD/kicker from gen.py so the whole deck shares tokens.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from gen import HEAD, OUT, kicker  # noqa: E402

ROOT = OUT.parents[1]
GLOW_A = '<circle cx="1860" cy="40" r="820" fill="url(#tv-glow-a)"/>'
CHIP = {"x86": "#1f6fe5", "amd": "#0e9f9a", "arm": "#6D4AE8"}  # same as charts.py CHIPS
# stagger-in: poster (no motion) = final state
IN = "@keyframes in{from{opacity:0;transform:translateY(24px)}to{opacity:1;transform:none}}.in{animation:in .7s cubic-bezier(.2,.7,.2,1) both}"
FADE = "@keyframes fd{from{opacity:0}to{opacity:1}}.fd{animation:fd .5s ease-out both}"
EXTRA = (".big{font-size:30px;font-weight:600;fill:#15123C}.lbl{font:24px 'JetBrains Mono',Menlo,monospace;fill:#6D4AE8}"
         ".pc{fill:#fff4e5;stroke:#d97706;stroke-width:2;stroke-dasharray:8 6}"
         ".pct{font:24px 'JetBrains Mono',Menlo,monospace;fill:#b45309}")


def page(name, title, body, anim="", glow=True):
    css = EXTRA + (f"@media (prefers-reduced-motion: no-preference){{{anim}}}" if anim else "")
    head = HEAD.replace("{title}", title).replace("{css}", css)
    if not glow:
        head = head.replace(GLOW_A, "")
    (OUT / f"{name}.svg").write_text(head + body + "\n</svg>\n")


def top(k, h, sub=""):
    out = kicker(k) + f'<text x="96" y="140" class="h">{h}</text>\n'
    return out + (f'<text x="96" y="192" class="sub">{sub}</text>\n' if sub else "")


def src(text):
    return f'<text x="96" y="990" class="c">{text}</text>\n'


def porc(x, y, w, h, text="POR-CONFIRMAR", cls="pct"):
    # ponytail: placeholder on purpose (skill rule), replace before the talk
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" class="pc"/>'
            f'<text x="{x+18}" y="{y+h/2+8}" class="{cls}">{text}</text>\n')


def card(x, y, w, h):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="20" class="card"/>'


def g_in(i, inner, d0=0.3, step=0.45):
    return f'<g class="in" style="animation-delay:{d0 + i*step:.2f}s">{inner}</g>\n'


def lines(x, y, rows, cls="c", dy=34):
    return "".join(f'<text x="{x}" y="{y + i*dy}" class="{cls}">{r}</text>' for i, r in enumerate(rows))


# ---------------------------------------------------------------- 01 title (loop 12 s)
def titulo():
    sweep = """<linearGradient id="sw" gradientUnits="userSpaceOnUse" x1="1150" y1="0" x2="1920" y2="1080"><stop offset="0" stop-color="#4C2FC9"/><stop offset=".5" stop-color="#6D4AE8"/><stop offset="1" stop-color="#A78BFA"/></linearGradient>
<g class="sweep">
  <circle cx="2350" cy="540" r="1150" fill="none" stroke="url(#sw)" stroke-width="10" opacity=".35"/>
  <circle cx="2350" cy="540" r="1030" fill="none" stroke="url(#sw)" stroke-width="140" opacity=".9"/>
  <circle cx="2350" cy="540" r="880" fill="none" stroke="url(#sw)" stroke-width="60" opacity=".55"/>
  <circle cx="2350" cy="540" r="790" fill="none" stroke="url(#sw)" stroke-width="18" opacity=".3"/>
</g>
"""
    body = (sweep
            # title: facts-talk-scope.md §1 (submitted abstract, immutable)
            + '<text x="96" y="400" font-size="92" font-weight="700" fill="#15123C"><tspan fill="url(#tv-grad-h)">ARM</tspan>ed and Dangerous</text>\n'
            + '<text x="96" y="486" font-size="44" fill="#5E5A80">lo que Graviton5 hace con tus workloads,</text>\n'
            + '<text x="96" y="544" font-size="44" fill="#5E5A80">medido en EKS</text>\n'
            + '<path d="M96 600 H336" stroke="url(#tv-grad-h)" stroke-width="8" stroke-linecap="round"/>\n'
            + '<text x="96" y="716" font-size="36" font-weight="600" fill="#15123C">Andrés Zeballos</text>\n'
            + '<text x="96" y="764" font-size="28" fill="#5E5A80">Solutions Architect · phData</text>\n'
            + '<text x="600" y="716" font-size="36" font-weight="600" fill="#15123C">Victor Herrera</text>\n'
            + '<text x="600" y="764" font-size="28" fill="#5E5A80">Cloud Specialist · Caleidos</text>\n'
            # event: ../kcd/kcd-argentina-2026-brainstorm-recap.md §11 (Sessionize, verified 2026-08-12)
            + '<text x="96" y="900" class="m" font-size="26" fill="#5E5A80">AWS Community Day Perú 2026 · 3 de octubre · Lima</text>\n')
    anim = (".sweep{animation:drift 12s ease-in-out infinite;transform-origin:2350px 540px}"
            "@keyframes drift{0%,100%{transform:rotate(0) translateX(0)}50%{transform:rotate(-7deg) translateX(-30px)}}")
    page("01-titulo", "ARMed and Dangerous", body, anim, glow=False)


# ---------------------------------------------------------------- 02 question (static)
def pregunta():
    body = (kicker("ANTES DE EMPEZAR")
            + '<text x="96" y="560" font-size="120" font-weight="700" fill="#15123C">¿Saben qué es <tspan fill="url(#tv-grad-h)">Graviton</tspan>?</text>\n'
            + '<text x="96" y="650" font-size="36" fill="#5E5A80">Levanten la mano. Y ahora: ¿quién ya lo tiene en producción?</text>\n')
    page("02-pregunta", "¿Saben qué es Graviton?", body)


# ---------------------------------------------------------------- 03 Graviton5 stat row (play-once)
def graviton5():
    W, G, Y, H = 414, 24, 290, 480
    stats = [  # (kicker, prefix, stat, caption lines, fuentes entry)
        ("CÓMPUTO", "hasta ", "25 %", ["más rendimiento de cómputo", "que Graviton4 (M8g)"]),          # Parte 2 §1.2
        ("NÚCLEOS", "", "192", ["núcleos en un solo chip"]),                                           # Parte 2 §1.6
        ("MEMORIA", "DDR5", "8800", ["“la memoria más rápida de", "cualquier instancia en la", "nube”, según AWS"]),  # Parte 2 §1.4
        ("CACHÉ L3", "", "5×", ["más L3 que Graviton4 por", "chip; por núcleo, 2.6×"]),               # Parte 2 §1.5 (5x per chip, 2.6x per core)
    ]
    body = [top("GRAVITON5", "Lo que promete Graviton5", "Cifras de AWS al lanzar M9g; las nuestras vienen después.")]
    for i, (k, pre, st, cap) in enumerate(stats):
        x = 96 + i * (W + G)
        pre_t = f'<text x="{x+32}" y="{Y+142}" font-size="40" font-weight="700" fill="url(#tv-grad-h)">{pre.strip()}</text>' if pre else ""
        inner = (card(x, Y, W, H)
                 + f'<text x="{x+32}" y="{Y+64}" class="lbl">[{k}]</text>'
                 + pre_t + f'<text x="{x+32}" y="{Y+240}" font-size="100" font-weight="700" fill="url(#tv-grad-h)">{st}</text>'
                 + lines(x + 32, Y + 316, cap, "sub", 38))
        body.append(g_in(i, inner))
    body.append(src("Fuente: AWS News Blog, “Now available: Amazon EC2 M9g and M9gd instances…”, 10-06-2026; About Amazon (2.6× por núcleo)"))
    page("03-graviton5", "Lo que promete Graviton5", "".join(body), IN)


# ---------------------------------------------------------------- 04 joke placeholder (static)
def chiste():
    """Speakers' joke (2026-09-29): every Graviton launch gets cheers, then everyone goes back to
    m5 and t2. Art generated by Codex image generation from our brief (original drawing; the
    "Ah, ya / ¿en qué estábamos?" meme was only a structure reference): art/chiste-graviton.png,
    1672x941 with transparency. Two beats: left panel, then the punchline panel."""
    w, h = 1480, round(1480 * 941 / 1672)
    x, y = (1920 - w) // 2, 212
    half = round(w * 835 / 1672)  # the panel gutter sits at x≈835 of 1672 in the art
    # chiste-graviton-alpha.png = the art with near-white keyed to transparent (Codex returned RGB)
    img = f'href="art/chiste-graviton-alpha.png" x="{x}" y="{y}" width="{w}" height="{h}"'
    body = (top("EL CHISTE", "Cada año, un Graviton nuevo")
            + f'<clipPath id="cl"><rect x="{x}" y="{y}" width="{half}" height="{h}"/></clipPath>'
            + f'<clipPath id="cr"><rect x="{x + half}" y="{y}" width="{w - half}" height="{h}"/></clipPath>'
            + f'<g class="p1"><image {img} clip-path="url(#cl)"/></g>'
            + f'<g class="p2"><image {img} clip-path="url(#cr)"/></g>')
    anim = (".p1{animation:pin .6s ease-out both}.p2{animation:pin .6s ease-out 1.8s both}"
            "@keyframes pin{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:none}}")
    page("04-chiste", "Cada año, un Graviton nuevo", body, anim)


# ---------------------------------------------------------------- 05 instance naming (static)
def nombre():
    # docs.aws.amazon.com/ec2/latest/instancetypes/instance-type-names.html, fetched 2026-09-29
    # fuentes.md Parte 2 §12.1. Play-once slot machine: m8i -> m8a -> m9g, poster = m9g + the three.
    T, L = 12.0, 300                           # seconds, reel line height (neighbors stay outside the window)
    fs, cw, x0, base = 220, 132, 234, 470      # mono: char width 0.6 × font size
    amd = CHIP["amd"]
    mono = "font-family=\"'JetBrains Mono',Menlo,monospace\""

    def p(t):
        return f"{100 * t / T:.2f}%"
    body = [top("NOMBRES", "¿Qué significa el nombre de un tipo de instancia EC2?")]
    # fixed glyphs: m and .4xlarge
    body.append(f'<g class="in" style="animation-delay:.2s"><text x="{x0}" y="{base}" {mono} font-size="{fs}" fill="#15123C">m</text>'
                f'<text x="{x0 + 3*cw}" y="{base}" {mono} font-size="{fs}" fill="#15123C"><tspan fill="#8C86B6">.</tspan>4xlarge</text>')
    # reels: generation digit (col 1) and option letter (col 2), clipped to one line
    reels = [("rd", 1, [("8", "#15123C"), ("3", "#8C86B6"), ("9", CHIP["arm"])]),
             ("rl", 2, [("i", CHIP["x86"]), ("c", "#8C86B6"), ("a", amd), ("x", "#8C86B6"), ("g", CHIP["arm"])])]
    body.append(f'<defs><linearGradient id="fadeV" gradientUnits="userSpaceOnUse" x1="0" y1="{base-270}" x2="0" y2="{base+90}">'
                '<stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".22" stop-color="#fff"/><stop offset=".85" stop-color="#fff"/>'
                '<stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
                f'<mask id="win" maskUnits="userSpaceOnUse" x="0" y="{base-270}" width="1920" height="360"><rect x="0" y="{base-270}" width="1920" height="360" fill="url(#fadeV)"/></mask></defs>')  # soft reel edges
    for rid, col, glyphs in reels:
        cx = x0 + col * cw + cw / 2
        texts = "".join(f'<text x="{cx}" y="{base + i*L}" text-anchor="middle" {mono} font-size="{fs}" fill="{c}">{g}</text>' for i, (g, c) in enumerate(glyphs))
        body.append(f'<g mask="url(#win)"><g id="{rid}">{texts}</g></g>')
    body.append("</g>\n")
    # brackets from each part to its label column (neutral, they never change)
    parts = [(0, 1, 240, 590), (1, 2, 500, 582), (2, 3, 960, 600), (4, 11, 1520, 590)]   # (from, to, label x, elbow y)
    for a, b, cx, ey in parts:
        xa, xb = x0 + a * cw + 8, x0 + b * cw - 8
        mid = (xa + xb) / 2
        body.append(f'<path class="in" style="animation-delay:.6s" d="M{xa} 548 V562 H{xb} V548 M{mid} 562 V{ey} H{cx} V614" fill="none" stroke="#A78BFA" stroke-width="3"/>')
    # labels: one group per state, in that state's color; crossfade when the reel lands
    states = [("st0", CHIP["x86"], "8", "i", "procesador Intel"),
              ("st1", amd, "8", "a", "procesador AMD"),
              ("st2", CHIP["arm"], "9", "g", "procesador AWS Graviton")]
    for sid, c, gen, opt, what in states:
        lab = [("m", "serie: uso general"), (gen, "generación"), (opt, what), ("4xlarge", "tamaño (aquí: 16 vCPU · 64 GiB)")]
        g = "".join(f'<text x="{cx}" y="664" text-anchor="middle" {mono} font-size="40" font-weight="700" fill="{c}">{k}</text>'
                    f'<text x="{cx}" y="708" text-anchor="middle" class="c">{d}</text>' for (_, _, cx, _), (k, d) in zip(parts, lab))
        body.append(f'<g id="{sid}">{g}</g>\n')
    # recap: the three of the lab (final frame carries all three for the PDF)
    pills = [("m8i.4xlarge", 2, CHIP["x86"], "Intel Xeon 6"), ("m8a.4xlarge", 2, amd, "AMD EPYC"), ("m9g.4xlarge", 2, CHIP["arm"], "Graviton5")]
    rec = ['<text x="200" y="808" class="lbl">[LAS TRES DEL LAB]</text>']
    for i, (name, k, c, chip) in enumerate(pills):
        x = 200 + i * 520
        nm = f'{name[:k]}<tspan fill="{c}" font-weight="700">{name[k]}</tspan>{name[k+1:]}'
        if name.startswith("m9g"):
            nm = f'm<tspan fill="{c}" font-weight="700">9g</tspan>{name[3:]}'
        rec.append(f'<rect x="{x}" y="830" width="480" height="96" rx="48" fill="#fff" stroke="{c}" stroke-width="2.5" filter="url(#sh)"/>'
                   f'<text x="{x+40}" y="890" {mono} font-size="32" fill="#15123C">{nm}</text>'
                   f'<text x="{x+300}" y="889" class="c" fill="#15123C">{chip}</text>')
    body.append(f'<g id="rc">{"".join(rec)}</g>\n')
    body.append(src("Fuente: EC2 “Instance type naming conventions” y “General purpose specifications”, docs.aws.amazon.com/ec2/latest/instancetypes (29-09-2026)"))
    # timeline: Intel holds, spin 1 lands on a, spin 2 lands on 9g, then the recap
    s1, e1, s2, e2, rc = 2.6, 4.9, 6.6, 8.9, 9.5   # 2.3 s spins; the digit reel stops 0.35 s before the letter
    bounce = "animation-timing-function:cubic-bezier(.45,.05,.2,1)"   # soft start, long reel-like deceleration
    anim = (IN
            + f"@keyframes rl{{0%,{p(s1)}{{transform:translateY(0);{bounce}}}{p(e1)},{p(s2)}{{transform:translateY(-{2*L}px);{bounce}}}{p(e2)},100%{{transform:translateY(-{4*L}px)}}}}"
            + f"@keyframes rd{{0%,{p(s2)}{{transform:translateY(0);{bounce}}}{p(e2-.35)},100%{{transform:translateY(-{2*L}px)}}}}"
            + f"@keyframes st0{{0%,{p(.6)}{{opacity:0}}{p(1.2)},{p(e1-.9)}{{opacity:1}}{p(e1-.5)},100%{{opacity:0}}}}"
            + f"@keyframes st1{{0%,{p(e1-.3)}{{opacity:0}}{p(e1+.3)},{p(e2-.9)}{{opacity:1}}{p(e2-.5)},100%{{opacity:0}}}}"
            + f"@keyframes st2{{0%,{p(e2-.3)}{{opacity:0}}{p(e2+.3)},100%{{opacity:1}}}}"
            + f"@keyframes rc{{0%,{p(rc)}{{opacity:0;transform:translateY(24px)}}{p(rc+.8)},100%{{opacity:1;transform:none}}}}"
            + f"#rl{{animation:rl {T}s linear both}}#rd{{animation:rd {T}s linear both}}"
            + "".join(f"#{s}{{animation:{s} {T}s linear both}}" for s in ("st0", "st1", "st2", "rc")))
    # static (reduced motion / poster) = final state: 9g landed, Graviton labels, recap shown
    still = f"#rl{{transform:translateY(-{4*L}px)}}#rd{{transform:translateY(-{2*L}px)}}#st0,#st1{{opacity:0}}"
    page("05-nombre-instancia", "Qué significa el nombre de una instancia EC2", f"<style>{still}</style>" + "".join(body), anim)


# ---------------------------------------------------------------- 06 why not (play-once)
def por_que_no():
    # Adoption: fuentes.md Parte 3 §8.1 (Cast AI 2026, their customers, Q2 2024 -> Q4 2025) and
    # §8.3 (Datadog State of Containers and Serverless 2025). No lab numbers here: the four cards
    # only say WHAT we tested; the answers come later in the talk (slides 17, 20, 21, 19).
    left = ('<text x="96" y="286" class="lbl">[ADOPCIÓN HOY]</text>'
            '<text x="90" y="470" font-size="210" font-weight="700" fill="url(#tv-grad-h)">9 %</text>'
            '<text x="96" y="532" font-size="32" font-weight="600" fill="#15123C">de las CPU en clústeres</text>'
            '<text x="96" y="572" font-size="32" font-weight="600" fill="#15123C">Kubernetes ya son Arm</text>'
            '<text x="96" y="622" class="c">y crecen 3.5× más rápido que x86</text>'
            '<path d="M96 668 H560" stroke="#DCD6F7" stroke-width="2"/>'
            '<text x="96" y="716" class="c">Instancias cloud en Arm:</text>'
            '<text x="96" y="764" font-size="40" font-weight="700" fill="#15123C">9 % → 15 %</text>'
            '<text x="96" y="802" class="c">en dos años</text>'
            '<rect x="96" y="846" width="496" height="90" rx="18" fill="#F6F4FE" stroke="#DCD6F7" stroke-width="1.5"/>'
            '<text x="124" y="882" class="c">detrás de las cuatro dudas:</text>'
            '<text x="124" y="920" font-size="30" font-weight="600" fill="#15123C">desconocimiento · temor</text>')
    cards = [("PRECIO", ["¿De verdad sale más barato?"], "“El ahorro es de marketing”",
              ["Rendimiento por dólar en 6 cargas,", "con precios on-demand y Spot"]),
             ("COMPATIBILIDAD", ["¿Mis imágenes y DaemonSets", "corren en ARM?"], "“Algo se va a romper”",
              ["Un DaemonSet solo amd64 en un", "clúster con nodos x86 y Graviton"]),
             ("ESFUERZO", ["¿Cuánto trabajo me cuesta", "migrar?"], "“Es un proyecto de meses”",
              ["Node groups mixtos y Karpenter", "en el mismo clúster"]),
             ("RENDIMIENTO", ["¿Y si mi app rinde menos", "en ARM?"], "“ARM es para cargas chicas”",
              ["La misma app de m5 a m9g, y 7 cargas", "en Graviton5, EPYC y Xeon 6"])]
    W, H, G, X0, Y0 = 570, 358, 24, 660, 220
    body = [top("LA PREGUNTA", "¿Por qué no lo usan?", "Cuatro dudas que escuchamos cada vez que alguien propone migrar"),
            g_in(0, left)]
    for i, (k, q, heard, measured) in enumerate(cards):
        x, y = X0 + (i % 2) * (W + G), Y0 + (i // 2) * (H + G)
        inner = (card(x, y, W, H) + f'<text x="{x+32}" y="{y+52}" class="lbl">[{k}]</text>'
                 + lines(x + 32, y + 100, q, "big", 38)
                 + f'<text x="{x+32}" y="{y+190}" font-size="24" font-style="italic" fill="#5E5A80">se escucha: {heard}</text>'
                 + f'<text x="{x+32}" y="{y+236}" class="lbl" style="fill:#0e9f9a">LO QUE PROBAMOS</text>'
                 + lines(x + 32, y + 276, measured, "c", 34))
        body.append(g_in(i + 1, inner))
    body.append(src("Fuente: Cast AI, 2026 State of Kubernetes Optimization Report (sus clientes); "
                    "Datadog, State of Containers and Serverless 2025"))
    page("06-por-que-no", "¿Por qué no lo usan?", "".join(body), IN)


# ---------------------------------------------------------------- 07 workloads (play-once)
def workloads():
    G, Y, H = 20, 250, 640
    W = (1728 - 4 * G) / 5
    # sources: facts-setup.md §3.1-3.5 (what it is), spec §4 table (what it stresses), fuentes O-18 (SLOs)
    cards = [
        ("Java + vthreads", ["Spring REST (PetClinic)", "en JDK 25, con ajustes", "y virtual threads"],
         ["muchas peticiones", "simultáneas: uso de", "CPU y coordinación", "entre hilos"], ["peticiones por segundo", "con el 99 % en &lt; 10 ms"]),
        ("Java tuned", ["Spring REST en JDK 25,", "con THP y flags de JVM", "elegidas por chip"],
         ["mucho código:", "qué tan rápido el", "núcleo lee y decodifica", "sus instrucciones"], ["peticiones por segundo", "con el 99 % en &lt; 10 ms"]),
        ("Go", ["servicio HTTP de la", "librería estándar"],  # sort-10000 not claimed: facts-setup open question 3
         ["cálculo por petición,", "sin leer datos", "del disco"], ["peticiones por segundo", "con el 99 % en &lt; 20 ms"]),        # facts-setup §3.2 (ECHO_N 10000)
        ("PostgreSQL", ["pgbench select-only,", "escala 1000 (~17 GB)"],                    # facts-setup §3.5; fuentes O-37
         ["consultas cortas por", "índice, con los datos", "precargados en", "memoria"], ["consultas por segundo", "con el 99 % en &lt; 5 ms"]),
        ("MongoDB", ["YCSB workload B", "(95 % lecturas),", "20 M registros"],               # fuentes O-27; facts-setup §3.4
         ["lecturas en memoria:", "qué tan rápido llegan", "los datos al chip", "(en caché a propósito)"], ["operaciones por", "segundo; 99 % de las", "lecturas en &lt; 5 ms"]),
    ]
    body = [top("WORKLOADS", "Siete workloads, cada uno exige algo distinto", "Los mismos siete en Intel, AMD y Graviton5; primero, los cinco con SLO de latencia")]
    for i, (t, que, exige, metric) in enumerate(cards):
        x = 96 + i * (W + G)
        inner = (card(x, Y, W, H) + f'<text x="{x+24}" y="{Y+62}" class="t">{t}</text>'
                 + f'<text x="{x+24}" y="{Y+124}" class="lbl">QUÉ ES</text>' + lines(x + 24, Y + 164, que)
                 + f'<text x="{x+24}" y="{Y+290}" class="lbl">QUÉ EXIGE</text>' + lines(x + 24, Y + 330, exige)
                 + f'<path d="M{x+24} {Y+460} H{x+W-24}" stroke="#DCD6F7" stroke-width="1.5"/>'
                 + f'<text x="{x+24}" y="{Y+505}" class="lbl">CÓMO SE MIDE</text>' + lines(x + 24, Y + 545, metric))
        body.append(g_in(i, inner, step=0.35))
    body.append(src("Fuente: lab propio; versiones, datasets y SLO en analysis/facts-setup.md §3–§4"))
    page("07-workloads", "Siete workloads", "".join(body), IN)


# ---------------------------------------------------------------- 07b inference + network (play-once)
def workloads_extra():
    G, Y, H = 20, 250, 640
    W = (1728 - G) / 2
    # sources: facts-setup §3.3 + §4.3 (inference), §3.6 + §4.6 (net); spec §4 table (what each stresses); fuentes O-40
    cards = [
        ("Inferencia en CPU", ["llama.cpp con Llama 3.1 8B (Q4_0),", "4 usuarios generando texto a la vez"],
         ["ancho de banda de memoria y cálculo", "vectorial para generar cada token"],
         ["tokens por segundo entre los 4 usuarios;", "no hay SLO de latencia, runs de 6 minutos"]),
        ("Red", ["iperf3 con 8 flujos TCP entre dos", "nodos del mismo tipo"],
         ["la pila de red del kernel: cuánta CPU", "gasta el nodo en recibir tráfico"],
         ["núcleos de CPU por Gbps recibido;", "los Gbps los limita la instancia, no el chip"]),
    ]
    body = [top("WORKLOADS", "Y dos más: inferencia y red", "Mismos tres chips y mismo clúster; aquí no hay SLO de p99")]
    for i, (t, que, exige, metric) in enumerate(cards):
        x = 96 + i * (W + G)
        inner = (card(x, Y, W, H) + f'<text x="{x+32}" y="{Y+62}" class="t">{t}</text>'
                 + f'<text x="{x+32}" y="{Y+124}" class="lbl">QUÉ ES</text>' + lines(x + 32, Y + 164, que)
                 + f'<text x="{x+32}" y="{Y+290}" class="lbl">QUÉ EXIGE</text>' + lines(x + 32, Y + 330, exige)
                 + f'<path d="M{x+32} {Y+460} H{x+W-32}" stroke="#DCD6F7" stroke-width="1.5"/>'
                 + f'<text x="{x+32}" y="{Y+505}" class="lbl">CÓMO SE MIDE</text>' + lines(x + 32, Y + 545, metric))
        body.append(g_in(i, inner, step=0.35))
    body.append(src("Fuente: lab propio; setup en analysis/facts-setup.md §3.3, §3.6, §4.3 y §4.6"))
    page("07b-workloads-extra", "Y dos más: inferencia y red", "".join(body), IN)


# ---------------------------------------------------------------- 09 method (play-once)
def como_medimos():
    rows = [  # (stat, title, caption) — fuentes Parte 1
        ("2 × 3", "3 runs de 8 minutos por día, durante 2 días", "instancias distintas cada día · inferencia: runs de 6 min · red: un día, 60 s por sentido"),   # O-14
        ("15 vCPU", "asignadas en exclusiva al pod de la app", "el runner verifica las 15 vCPU antes de medir; si faltan, aborta la prueba"),      # O-05
        ("≤ 70 %", "el loader corre en su propia instancia (c8i.16xlarge)", "si pasa del 70 % de CPU, el run se descarta; en red, el tráfico sale de otro nodo igual"),  # O-12
        ("punto de quiebre", "la mayor carga medida que cumple el SLO de p99", "10 ms Java · 20 ms Go · 5 ms PostgreSQL y MongoDB; inferencia y red no tienen SLO"),        # O-18
        ("30 / 30", "pruebas válidas el día 3", "prueba = un workload en un chip con una configuración; ningún run inválido"),  # O-17
    ]
    body = [top("MÉTODO", "Cómo medimos para comparar los tres", "Las reglas para comparar los siete workloads")]
    for i, (st, t, c) in enumerate(rows):
        y = 240 + i * 130
        inner = (card(96, y, 1728, 110)
                 + f'<text x="136" y="{y+76 if len(st) < 10 else y+70}" font-size="{60 if len(st) < 10 else 40}" font-weight="700" fill="url(#tv-grad-h)">{st}</text>'
                 + f'<text x="560" y="{y+48}" class="t">{t}</text><text x="560" y="{y+86}" class="c">{c}</text>')
        body.append(g_in(i, inner, step=0.35))
    body.append(src("Fuente: lab propio, Task 7 (25 al 28-09-2026); analysis/facts-setup.md §1.4 y §4"))
    page("09-como-medimos", "Cómo medimos para comparar los tres", "".join(body), IN)


# ---------------------------------------------------------------- 10 vCPU (play-once)
def vcpu():
    rows = [  # (chip key, name, type, clock as AWS words it, summary)
        ("x86", "Intel Xeon 6", "m8i.4xlarge", "3.9 GHz de turbo sostenido en todos los núcleos",   # Parte 2 §2.1
         "8 núcleos × 2 hilos (SMT)"),                                                            # Parte 2 §2.5; O-03
        ("amd", "AMD EPYC 9R45", "m8a.4xlarge", "hasta 4.5 GHz",                                  # Parte 2 §3.2 (MATIZ: "hasta")
         "16 núcleos, 1 hilo cada uno"),                                                          # Parte 2 §3.3, §3.7
        ("arm", "AWS Graviton5", "m9g.4xlarge", "3.3 GHz",                                        # Parte 2 §1.8 (MATIZ: Getting Started + API)
         "16 núcleos, 1 hilo cada uno"),                                                          # Parte 2 §1.11
    ]
    body = [top("VCPU ≠ VCPU", "Mismo tamaño, 16 vCPU, distinto procesador", "Qué hay detrás de cada vCPU en una 4xlarge")]
    css, n = [IN, "@keyframes sq{from{opacity:0;transform:scale(.4)}to{opacity:1;transform:none}}"
              ".sq{transform-box:fill-box;transform-origin:center;animation:sq .35s ease-out both}"], 0
    X0 = 780
    for r, (k, name, typ, clock, summ) in enumerate(rows):
        y = 240 + r * 224
        col = CHIP[k]
        body.append(g_in(r, card(96, y, 1728, 200)
                         + f'<text x="136" y="{y+62}" class="t">{name}</text>'
                         + f'<text x="136" y="{y+102}" class="m">{typ}</text>'
                         + f'<text x="136" y="{y+160}" class="c">{clock}</text>', step=0.25))
        sq = []
        for i in range(16):
            if k == "x86":
                p, s = divmod(i, 2)
                sx = X0 + p * 128 + s * 56
                if s == 0:
                    sq.append(f'<rect x="{sx-8}" y="{y+32}" width="120" height="64" rx="10" fill="none" stroke="{col}" stroke-width="2"/>')
                op = 1 if s == 0 else .45
            else:
                sx, op = X0 + i * 64, 1
            d = 1.0 + r * 0.5 + i * 0.05
            sq.append(f'<rect class="sq" style="animation-delay:{d:.2f}s" x="{sx}" y="{y+40}" width="48" height="48" rx="6" fill="{col}" fill-opacity="{op}"/>')
        body.append("".join(sq))
        body.append(f'<text x="{X0}" y="{y+150}" class="big" style="fill:{col}">{summ}</text>'
                    + ('<text x="1200" y="' + str(y + 150) + '" class="c">cada par comparte un núcleo físico</text>' if k == "x86" else "") + "\n")
    body.append(src("Fuente: EC2 gp.html y describe-instance-types (29-09-2026); páginas de producto M8i y M8a; aws-graviton-getting-started (3.3 GHz)"))
    page("10-vcpu", "Mismo tamaño, 16 vCPU, distinto procesador", "".join(body), "".join(css))


# ---------------------------------------------------------------- 11 knee (play-once)
def knee():
    d = json.loads((ROOT / "results/2026-09-27-task7-d3/java/arm-stock/knee.json").read_text())
    series, kx, slo = d["series"], d["knee"], d["slo_ms"]   # knee 70000 (coarse), slo 10 ms
    L, R, T, B = 230, 1760, 290, 820
    XMAX, YMAX = 125000, 25
    px = lambda r: L + r / XMAX * (R - L)
    py = lambda ms: B - min(ms, YMAX) / YMAX * (B - T)
    body = [top("PUNTO DE QUIEBRE", "Qué es el punto de quiebre",
                "Graviton5 (m9g), Java sin ajustes, día 3: el p99 al subir la carga de 10 mil en 10 mil rps")]
    ax = [f'<line x1="{L}" x2="{R}" y1="{B}" y2="{B}" stroke="#DCD6F7" stroke-width="2"/>']
    for v in range(0, 26, 5):
        ax.append(f'<line x1="{L}" x2="{R}" y1="{py(v)}" y2="{py(v)}" stroke="#EEEBFB" stroke-width="1.5"/>' if v else "")
        ax.append(f'<text x="{L-18}" y="{py(v)+8}" text-anchor="end" class="c">{v}</text>')
    for v in range(0, 125000, 20000):
        ax.append(f'<text x="{px(v)}" y="{B+40}" text-anchor="middle" class="c">{f"{v//1000}k" if v else 0}</text>')
    ax.append(f'<text x="{R}" y="{B+84}" text-anchor="end" class="c">carga enviada (rps)</text>')
    ax.append(f'<text x="{L-18}" y="{T-30}" text-anchor="end" class="c">p99 (ms)</text>')
    ys = py(slo)
    ax.append(f'<line x1="{L}" x2="{R}" y1="{ys}" y2="{ys}" stroke="#5E5A80" stroke-width="2" stroke-dasharray="8 8"/>'
              f'<text x="{L+16}" y="{ys-14}" class="c">SLO: p99 &lt; {slo} ms</text>')
    body.append("".join(ax) + "\n")
    pts = " ".join(f"{px(r):.1f},{py(ms):.1f}" for r, ms in series)
    body.append(f'<defs><clipPath id="plot"><rect x="{L}" y="{T-8}" width="{R-L+10}" height="{B-T+10}"/></clipPath></defs>'
                f'<polyline id="ln" points="{pts}" pathLength="1" fill="none" stroke="#6D4AE8" stroke-width="4" '
                f'stroke-linejoin="round" stroke-dasharray="1" stroke-dashoffset="0" clip-path="url(#plot)"/>\n')
    for i, (r, ms) in enumerate(series):
        dl = 0.3 + i / (len(series) - 1) * 2.4
        if ms > YMAX:   # off-scale steps: marker at the top edge + value
            mk = (f'<path d="M{px(r)-12} {T+4} L{px(r)} {T-16} L{px(r)+12} {T+4} Z" fill="#6D4AE8"/>'
                  f'<text x="{px(r)}" y="{T-28}" text-anchor="middle" class="c">{ms:.0f} ms</text>')
        else:
            mk = f'<circle cx="{px(r)}" cy="{py(ms)}" r="7" fill="#6D4AE8" stroke="#fff" stroke-width="2"/>'
        body.append(f'<g class="fd" style="animation-delay:{dl:.2f}s">{mk}</g>')
    body.append(f'<text x="{px(110000)}" y="{T+44}" text-anchor="middle" class="c">fuera de escala</text>')
    kms = dict(series)[kx]
    cx, cy = px(kx), py(kms)
    ann = (f'<circle cx="{cx}" cy="{cy}" r="18" fill="none" stroke="url(#tv-grad)" stroke-width="4"/>'
           f'<path d="M{cx} {cy+20} V{B}" stroke="#6D4AE8" stroke-width="2" stroke-dasharray="4 6"/>'
           f'<path d="M{cx-30} {cy-100} L{cx-14} {cy-16}" stroke="#6D4AE8" stroke-width="2"/>'
           f'<text x="{cx-40}" y="{cy-190}" text-anchor="end" class="t">punto de quiebre en esta medición:</text>'
           f'<text x="{cx-40}" y="{cy-152}" text-anchor="end" class="t">{kx//1000} mil rps, la mayor carga dentro del SLO</text>'
           # fuentes O-20: fine-ladder knee for m9g Java stock = 80.0k
           f'<text x="{cx-40}" y="{cy-114}" text-anchor="end" class="c">otra medición, subiendo de 2 mil en 2 mil, lo ubicó en 80 mil rps</text>')
    body.append(f'<g class="fd" style="animation-delay:3.0s">{ann}</g>\n')
    body.append('<text x="96" y="935" class="sub">rps / tps / ops/s = peticiones / transacciones / operaciones por segundo</text>\n')
    body.append(src("Fuente: lab propio, Task 7 día 3, Java sin ajustes en Graviton5 (results/2026-09-27-task7-d3)"))
    anim = (FADE + "@keyframes ln{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}"
            "#ln{animation:ln 2.8s linear .2s both}")
    page("11-knee", "Qué es el punto de quiebre", "".join(body), anim)


if __name__ == "__main__":
    for f in (titulo, pregunta, graviton5, chiste, nombre, por_que_no, workloads, workloads_extra, como_medimos, vcpu, knee):
        f()
    print("ok")
