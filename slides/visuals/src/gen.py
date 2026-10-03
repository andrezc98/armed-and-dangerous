"""Generate the ARMed and Dangerous slide SVGs (talk-visuals skill). Run: python3 slides/visuals/src/gen.py"""
import pathlib
import re
import sys

SKILL = pathlib.Path.home() / "Documents/personal/charlas/.claude/skills/talk-visuals"
sys.path.insert(0, str(SKILL / "scripts"))
from icon import snippet  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent.parent

HEAD = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080" width="1920" height="1080" font-family="'Inter', 'Helvetica Neue', Arial, sans-serif">
<title>{title}</title>
<defs>
<linearGradient id="tv-grad" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#4C2FC9"/><stop offset=".5" stop-color="#6D4AE8"/><stop offset="1" stop-color="#A78BFA"/></linearGradient>
<linearGradient id="tv-grad-h" gradientUnits="userSpaceOnUse" x1="96" y1="0" x2="1824" y2="0"><stop offset="0" stop-color="#4C2FC9"/><stop offset=".5" stop-color="#6D4AE8"/><stop offset="1" stop-color="#A78BFA"/></linearGradient>
<radialGradient id="tv-glow-a"><stop offset="0" stop-color="#A78BFA" stop-opacity=".16"/><stop offset=".45" stop-color="#6D4AE8" stop-opacity=".08"/><stop offset="1" stop-color="#6D4AE8" stop-opacity="0"/></radialGradient>
<radialGradient id="tv-glow-b"><stop offset="0" stop-color="#6D4AE8" stop-opacity=".10"/><stop offset="1" stop-color="#6D4AE8" stop-opacity="0"/></radialGradient>
<filter id="sh" x="-10%" y="-10%" width="120%" height="130%"><feDropShadow dx="0" dy="6" stdDeviation="10" flood-color="#15123C" flood-opacity=".07"/></filter>
</defs>
<style>@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&amp;family=Montserrat:wght@600;700&amp;family=JetBrains+Mono&amp;display=block');
.k{font:26px 'JetBrains Mono',Menlo,monospace;fill:#15123C}
.h{font-family:Montserrat,Inter,sans-serif;font-size:52px;font-weight:700;fill:#15123C}
.sub{font-size:26px;fill:#5E5A80}
.t{font-size:30px;font-weight:600;fill:#15123C}
.c{font-size:24px;fill:#5E5A80}
.m{font:24px 'JetBrains Mono',Menlo,monospace;fill:#15123C}
.card{fill:#fff;stroke:#DCD6F7;stroke-width:1.5;filter:url(#sh)}
.act{fill:none;stroke:url(#tv-grad);stroke-width:3;filter:drop-shadow(0 0 18px rgb(109 74 232 / .35))}
.idle{fill:none;stroke:#DCD6F7;stroke-width:3;stroke-dasharray:6 6}
.on{fill:none;stroke:#6D4AE8;stroke-width:3}
.dot{fill:#6D4AE8;stroke:#fff;stroke-width:3;filter:drop-shadow(0 0 8px rgb(109 74 232 / .6))}
.gl{fill:none;stroke:#fff;stroke-width:3;stroke-linecap:round;stroke-linejoin:round}
{css}
</style>
<rect width="1920" height="1080" fill="#fff"/><circle cx="1860" cy="40" r="820" fill="url(#tv-glow-a)"/><circle cx="60" cy="1060" r="760" fill="url(#tv-glow-b)"/>
"""


def kicker(text, y=74):
    return f'<text x="96" y="{y}" class="k"><tspan fill="#6D4AE8">[</tspan>{text}<tspan fill="#6D4AE8">]</tspan></text>\n'


def glyph_tile(x, y, body, size=72):
    """Self-drawn glyph for non-AWS things (laptop, flame), same tile as the recolored icons."""
    s = size / 80
    return (f'<g transform="translate({x} {y}) scale({s})"><rect width="80" height="80" fill="url(#tv-grad)"/>'
            f'<g class="gl">{body}</g></g>')


LAPTOP = '<rect x="20" y="22" width="40" height="28" rx="3"/><path d="M14 58 H66 L60 50 H20 Z"/>'
FLAME = '<path d="M40 16 C48 28 58 34 56 48 C55 58 48 64 40 64 C32 64 25 58 24 48 C23 40 30 34 32 26 C36 32 38 34 40 36 C42 30 42 24 40 16 Z"/><path d="M40 64 C35 64 33 58 36 52 C38 49 40 47 40 44 C43 48 46 52 45 57 C44 61 42 64 40 64 Z"/>'


# ---------------------------------------------------------------- 08 architecture (facts-setup §2, fuentes O-12)
PKG = SKILL / "assets/aws-icons/pkg"
LOOP = 9.0
SUTS = [  # (chip, instance, chip color from the deck palette, y)
    ("Intel Xeon 6", "m8i.4xlarge", "#1f6fe5", 412),
    ("AMD EPYC", "m8a.4xlarge", "#0e9f9a", 604),
    ("Graviton5", "m9g.4xlarge", "#6D4AE8", 796),
]
LX, LY, LW, LH = 726, 572, 330, 230          # loader card
SX, SW, SH = 1110, 380, 170                  # SUT cards
PX, PY, PW, PH = 1540, 557, 216, 260         # Pyroscope card


def pkg_icon(rel, x, y, size, tile=None, line="#fff"):
    """Official group/resource icon from the AWS package. Group icons: background -> gradient.
    Resource icons (single-color line art): drawn in `line` on a `tile` square (gradient by default)."""
    svg = (PKG / rel).read_text()
    vb = re.search(r'viewBox="([^"]+)"', svg).group(1)
    body = svg[svg.index(">", svg.index("<svg")) + 1: svg.rindex("</svg>")]
    body = re.sub(r"<title>.*?</title>", "", body, flags=re.S)
    body = re.sub(r'\s+id="[^"]*"', "", body)
    if rel.startswith("Architecture-Group"):
        body = re.sub(r'fill="#(?!FFFFFF)[0-9A-Fa-f]{6}"', 'fill="url(#tv-grad)"', body, count=1)
        return f'<svg x="{x}" y="{y}" width="{size}" height="{size}" viewBox="{vb}">{body.strip()}</svg>'
    body = re.sub(r'fill="#[0-9A-Fa-f]{6}"', f'fill="{line}"', body)
    pad = size * 0.14
    return (f'<rect x="{x}" y="{y}" width="{size}" height="{size}" fill="{tile or "url(#tv-grad)"}"/>'
            f'<svg x="{x+pad}" y="{y+pad}" width="{size-2*pad}" height="{size-2*pad}" viewBox="{vb}">{body.strip()}</svg>')


CLIENT = "Resource-Icons_07312026/Res_General-Icons/Res_48_Light/Res_Client_48_Light.svg"
INSTANCE = "Resource-Icons_07312026/Res_Compute/Res_Amazon-EC2_Instance_48.svg"
REGION = "Architecture-Group-Icons_07312026/Region_32.svg"
VPC = "Architecture-Group-Icons_07312026/Virtual-private-cloud-VPC_32.svg"


def pct(t):
    return f"{100 * t / LOOP:.2f}%"


def arch():
    css, body = [], []
    # AWS group frames: Region > VPC > AZ (official group icons, theme colors)
    body.append('<rect x="376" y="236" width="1448" height="800" rx="6" fill="none" stroke="#A78BFA" stroke-width="2" stroke-dasharray="10 7"/>')
    body.append(pkg_icon(REGION, 376, 236, 44) + '<text x="434" y="268" class="c" fill="#15123C">Región us-east-1</text>')
    body.append('<rect x="676" y="296" width="1124" height="716" rx="6" fill="none" stroke="#6D4AE8" stroke-width="2"/>')
    body.append(pkg_icon(VPC, 676, 296, 44) + '<text x="734" y="328" class="c" fill="#15123C">VPC · Amazon EKS 1.36 · managed node groups · Bottlerocket</text>')
    body.append('<rect x="700" y="358" width="1076" height="630" rx="10" fill="#F6F4FE" stroke="#DCD6F7" stroke-width="1.5" stroke-dasharray="8 6"/>')
    body.append('<text x="724" y="394" class="c" fill="#6D4AE8">us-east-1a · loader y nodo medido en la misma zona</text>')
    # runner: laptop, outside AWS
    body.append('<rect x="96" y="300" width="240" height="210" rx="20" class="card"/>' + pkg_icon(CLIENT, 120, 324, 64))
    body.append('<text x="120" y="430" class="t">Runner</text><text x="120" y="466" class="c">kubectl · AWS CLI</text>')
    # EKS control plane + ECR (regional, outside the VPC)
    body.append('<rect x="406" y="300" width="240" height="210" rx="20" class="card"/>' + snippet("Elastic-Kubernetes-Service", 430, 324, 64))
    body.append('<text x="430" y="430" class="t">Amazon EKS</text><text x="430" y="466" class="c">plano de control</text>')
    body.append('<path d="M336 405 H406" class="idle"/>')
    body.append('<rect x="406" y="780" width="240" height="210" rx="20" class="card"/>' + snippet("Elastic-Container-Registry", 430, 804, 64))
    body.append('<text x="430" y="910" class="t">Amazon ECR</text><text x="430" y="946" class="m">amd64 + arm64</text>')
    body.append('<path d="M646 405 H700" class="idle"/>')
    body.append('<path d="M646 885 H700" class="idle"/>')
    # loader
    body.append(f'<rect x="{LX}" y="{LY}" width="{LW}" height="{LH}" rx="20" class="card"/>' + pkg_icon(INSTANCE, LX + 24, LY + 24, 64))
    body.append(f'<text x="{LX+104}" y="{LY+56}" class="t">Loader</text><text x="{LX+104}" y="{LY+88}" class="m">c8i.16xlarge</text>')
    body.append(f'<text x="{LX+24}" y="{LY+144}" class="c" fill="#15123C">k6, go-ycsb, pgbench</text>')
    body.append(f'<text x="{LX+24}" y="{LY+184}" class="c">64 vCPU · pico ≤ 70 %</text>')
    # Pyroscope on the tools node (open source, no official icon: self-drawn flame)
    body.append(f'<rect x="{PX}" y="{PY}" width="{PW}" height="{PH}" rx="20" class="card"/>' + glyph_tile(PX + 24, PY + 24, FLAME, 64))
    body.append(f'<text x="{PX+24}" y="{PY+138}" class="t">Pyroscope</text><text x="{PX+24}" y="{PY+174}" class="m">m7g.large</text>'
                f'<text x="{PX+24}" y="{PY+216}" class="c">guarda perfiles</text>')
    body.append(f'<rect x="{PX}" y="{PY}" width="{PW}" height="{PH}" rx="20" class="act" id="py"/>')
    for i, (title, inst, color, y) in enumerate(SUTS):
        t0 = i * LOOP / 3
        a, b, c, d = t0 + 0.2, t0 + 1.2, t0 + 1.4, t0 + 2.8
        load = f"M{LX+LW} {LY+LH/2} C{LX+LW+40} {LY+LH/2} {SX-40} {y+SH/2} {SX} {y+SH/2}"
        prof = f"M{SX+SW} {y+SH/2} C{SX+SW+30} {y+SH/2} {PX-30} {PY+PH/2} {PX} {PY+PH/2}"
        body.append(f'<path d="{load}" class="idle"/><path d="{prof}" class="idle"/>')
        body.append(f'<path d="{load}" class="on" id="on{i}"/><path d="{prof}" class="on" id="op{i}"/>')
        body.append(f'<rect x="{SX}" y="{y}" width="{SW}" height="{SH}" rx="20" class="card"/>' + pkg_icon(INSTANCE, SX + 24, y + 24, 64, tile=color))
        body.append(f'<text x="{SX+108}" y="{y+56}" class="t">{title}</text><text x="{SX+108}" y="{y+90}" class="m">{inst}</text>')
        body.append(f'<text x="{SX+24}" y="{y+140}" class="c">app: 15 vCPU exclusivas</text>')
        body.append(f'<rect x="{SX}" y="{y}" width="{SW}" height="{SH}" rx="20" class="act" id="s{i}"/>')
        body.append(f'<circle r="11" class="dot" id="d{i}" style="offset-path:path(\'{load}\')"/>')
        body.append(f'<circle r="11" class="dot" id="p{i}" style="offset-path:path(\'{prof}\')"/>')
        css.append(
            f"@keyframes on{i}{{0%,{pct(a)}{{opacity:0}}{pct(a+.1)},{pct(d)}{{opacity:1}}{pct(d+.2)},100%{{opacity:0}}}}"
            f"@keyframes d{i}{{0%,{pct(a)}{{offset-distance:0%;opacity:0}}{pct(a+.1)}{{opacity:1}}{pct(b)}{{offset-distance:100%;opacity:1}}{pct(b+.1)},100%{{offset-distance:100%;opacity:0}}}}"
            f"@keyframes s{i}{{0%,{pct(b-.1)}{{opacity:0}}{pct(b+.2)},{pct(d)}{{opacity:1}}{pct(d+.2)},100%{{opacity:0}}}}"
            f"@keyframes p{i}{{0%,{pct(c)}{{offset-distance:0%;opacity:0}}{pct(c+.1)}{{opacity:1}}{pct(c+1)}{{offset-distance:100%;opacity:1}}{pct(c+1.1)},100%{{offset-distance:100%;opacity:0}}}}"
            f"#on{i},#op{i}{{animation:on{i} {LOOP}s linear infinite both}}#d{i}{{animation:d{i} {LOOP}s linear infinite both}}"
            f"#s{i}{{animation:s{i} {LOOP}s linear infinite both}}#p{i}{{animation:p{i} {LOOP}s linear infinite both}}"
        )
    pulses = "".join(f"{pct(i*3+2.3)}{{opacity:0}}{pct(i*3+2.5)}{{opacity:1}}{pct(i*3+2.95)}{{opacity:0}}" for i in range(3))
    css.append(f"@keyframes py{{0%{{opacity:0}}{pulses}100%{{opacity:0}}}}#py{{animation:py {LOOP}s linear infinite both}}")
    # un-animated (reduced motion) state = poster: Graviton lit, everything else idle
    static = "#on0,#op0,#on1,#op1,#s0,#s1,#py,.dot{opacity:0}"
    svg = (HEAD.replace("{title}", "El lab: mismo clúster, mismo loader, tres procesadores")
           .replace("{css}", static + "@media (prefers-reduced-motion: no-preference){" + "".join(css) + "}")
           + kicker("EL LAB")
           + '<text x="96" y="140" class="h">Mismo clúster, mismo loader, tres procesadores</text>\n'
           + '<text x="96" y="192" class="sub">Una celda a la vez: un nodo medido (dos en red) y perfiles de CPU por eBPF, sin instrumentar la app.</text>\n'
           + "\n".join(body) + "\n</svg>\n")
    (OUT / "08-arquitectura.svg").write_text(svg)


# ---------------------------------------------------------------- 01 promise (text)
def promesa():
    # verbatim from the abstract submitted to ACD Argentina / Perú (kcd recap §11b)
    css = ("#w{fill:#15123C}"
           "@media (prefers-reduced-motion: no-preference){"
           "#w{animation:w 5s ease-out both}@keyframes w{0%,30%{fill:#15123C}60%,100%{fill:#6D4AE8}}"
           "#u{animation:u 5s ease-out both}@keyframes u{0%,45%{stroke-dashoffset:300}75%,100%{stroke-dashoffset:0}}"
           "#lead{animation:f 5s ease-out both}@keyframes f{0%{opacity:0}15%,100%{opacity:1}}}"
           "#w{fill:#6D4AE8}")
    svg = (HEAD.replace("{title}", "La promesa").replace("{css}", css)
           + kicker("LA PROMESA", y=300)
           + '<text id="lead" x="96" y="380" font-size="40" fill="#5E5A80">Todos escuchamos la promesa: Graviton ofrece mejor precio-rendimiento.</text>\n'
           + '<text x="96" y="520" font-size="84" font-weight="700" fill="#15123C">Lo que casi nadie hace es</text>\n'
           + '<text x="96" y="630" font-size="84" font-weight="700" fill="#15123C"><tspan id="w">medir</tspan> qué significa todo eso</text>\n'
           + '<text x="96" y="740" font-size="84" font-weight="700" fill="#15123C">para su propio workload.</text>\n'
           + '<path id="u" d="M96 655 H336" stroke="url(#tv-grad-h)" stroke-width="8" stroke-linecap="round" stroke-dasharray="300" stroke-dashoffset="0"/>\n'
           + '<text x="96" y="900" class="m" fill="#5E5A80">ARMed and Dangerous · tres workloads, tres silicios, un mismo clúster</text>\n'
           + "</svg>\n")
    (OUT / "01-promesa.svg").write_text(svg)


if __name__ == "__main__":
    arch()
    promesa()
    print("ok")
