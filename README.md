# ARMed and Dangerous: lo que Graviton5 hace con tus workloads, medido en EKS

Demo repo de la charla (AWS Community Day Argentina 2026, waitlist → ACD Perú
2026 → AWS Women Colombia 2026): tres clases de workload — Java de alta
concurrencia, MongoDB y inferencia LLM en CPU — medidas en el mismo clúster
EKS con nodos x86 (`m8i`) y Graviton5 (`m9g`), explicadas con flame graphs de
eBPF (señal de Profiles de OpenTelemetry) y un harness open source completo.

> Slides: `slides/contenido.md` · fuentes y caveats de cada número:
> `slides/fuentes.md` · spec y plan: `docs/superpowers/`

## Versiones probadas
(se llena con cada corrida; verificar contra docs del día antes de confiar)

- Terraform >= 1.15 + `terraform-aws-modules/eks/aws` 21.25.0, provider aws ~> 6.63, provider helm ~> 3.3, EKS 1.36 con Bottlerocket >= 1.64.0 (ver `infra/README.md`)
- Imágenes propias en ECR privado de la cuenta sandbox: root `infra/ecr` (repos `IMMUTABLE`, scan on push, últimas 5 versiones; ver `infra/ecr/README.md`)
- Karpenter v1.14.1 (chart OCI oficial) · Pyroscope chart 2.2.1 (appVersion 2.2.1; v2.3.0 no tiene chart aún) · k6 v2.2.0
- OTel eBPF profiler `otel/opentelemetry-collector-ebpf-profiler` (tag del día) · APerf (`kubectl-aperf`) · metrics-server (addon EKS)
- Apps (verificado y probado en local 2026-09-03, ver `apps/*/Dockerfile`): `spring-petclinic-rest` master@`4cd8e1b0` (v4.0.2, Boot 4.1.1) sobre `eclipse-temurin:25.0.4_7-jre-noble`, build `maven:3.9.16-eclipse-temurin-25-noble` · Go `golang:1.27.1` + `gcr.io/distroless/static-debian13:nonroot` · `alpine:3.24.1` + iperf3 3.20-r0 · go-ycsb v1.0.3 · k6 `grafana/k6:2.2.0` (imagen oficial, amd64+arm64)
- Pendientes de Task 5: MongoDB 8.0 y llama.cpp `ghcr.io/ggml-org/llama.cpp:server-b10775` (imágenes oficiales; modelo `unsloth/Llama-3.1-8B-Instruct-GGUF` Q4_0, ver spec §9)
- EKS con Bottlerocket: `m8i.4xlarge` (x86, Xeon 6) vs `m9g.4xlarge` (Graviton5), un node group por celda stock/tuned

## El lab en una línea

```
 runner (Mac, sin terraform) ── escala MNG de la celda 0→1 ── aplica overlay (nodeSelector aad/cell)
        │
        ▼
 loader c7i.4xlarge ─ k6 / go-ycsb / iperf3 -c ─▶ SUT de la celda (1 pod, taint aad/sut)
                                                   x86-stock | x86-tuned | x86-smtoff  (m8i.4xlarge)
                                                   arm-stock | arm-tuned               (m9g.4xlarge)
                                                      │            │
                                   kubectl aperf ─────┘            └── DaemonSet profiler eBPF
                                   (PMU: IPC, stalls, TLB)              ─▶ Pyroscope (tools m7g.large)
        │                                                                     ─▶ flame graphs
        └── knee (ramping) → fija 80% ×n → JSON + tarball APerf + PNG ─▶ results/ ─▶ charts ─▶ slides
```

Una celda = un silicio en una configuración (stock / tuned / SMT off). Cada
workload corre en todas sus celdas; el clúster queda abajo entre días de lab.

## Reproducir
(completar en el Task 12 con el orden real de corrida y el costo medido)

### Orden

Una sola vez, para toda la gira de charlas:

```bash
# 1. Los cuatro repositorios ECR privados de la cuenta sandbox. Root de
#    Terraform aparte, con estado propio, y NO se destruye entre días de lab.
cd infra/ecr && terraform init && terraform apply     # GATED

# 2. Build multi-arch y push de las cuatro imágenes propias (GATED). Mergea en
#    results/images.json un tag y un digest POR IMAGEN: ese archivo SÍ se
#    commitea (no lleva datos de cuenta).
cd ../../apps && AWS_PROFILE=sura-sandbox AWS_REGION=us-east-1 PUSH=1 ./build-multiarch.sh
git add ../results/images.json && git commit -m "build: push <fecha>"
```

Por cada día de lab:

```bash
# Primera línea del día, siempre: el perfil sandbox tiene us-west-2 por default y
# el lab vive en us-east-1. Sin AWS_REGION, `aws` apunta a la región equivocada y
# los chequeos de fuga del cierre devuelven vacío por el motivo equivocado.
export AWS_PROFILE=sura-sandbox AWS_REGION=us-east-1

cd infra && terraform apply                            # GATED
mkdir -p ../results/$(date +%F)
terraform output -json             > ../results/$(date +%F)/cluster.json
terraform -chdir=ecr output -json  > ../results/$(date +%F)/ecr.json
# Los dos archivos están git-ignored: llevan el id de cuenta.

aws eks update-kubeconfig --region us-east-1 --name aws-aad-eks-lab
kubectl apply -k manifests/base                        # ver manifests/base/README.md
cd ../runner && uv run cell --workload java --cell arm-tuned --runs 3
# ...el resto de las celdas del día, y al terminar el cierre de abajo.
```

### Cierre del día de lab (orden canónico)

Este es el único lugar donde vive el orden: `infra/README.md`,
`manifests/base/README.md` y `runner/README.md` apuntan aquí en vez de repetirlo.
Cada paso existe porque el siguiente no lo cubre — `terraform destroy` no ve los
nodos de Karpenter ni el volumen EBS del driver CSI, porque ninguno de los dos
está en el estado de Terraform.

```bash
# 1. NodePools de Karpenter (existen solo en los días de arco / clip). Sus nodos
#    no están en el estado de Terraform.
kubectl delete nodepool --all --ignore-not-found
kubectl get nodes -l aad/role=arc            # tiene que quedar vacío

# 2. Todo lo que el runner dejó vivo en el clúster: StatefulSet de Mongo, PVCs,
#    Jobs de k6/YCSB/iperf3 y la perilla de red. Repite el paso 1 por las dudas
#    e imprime este checklist al terminar.
cd runner && uv run cell --teardown-day

# 3. Esperar a que los volúmenes desaparezcan de verdad. Las DOS listas tienen
#    que devolver [] ANTES del destroy (--teardown-day ya las corre una vez;
#    repetirlas hasta que estén vacías):
aws ec2 describe-volumes --region us-east-1 \
  --filters Name=tag:Project,Values=armed-and-dangerous \
  --query 'Volumes[].VolumeId'
aws ec2 describe-volumes --region us-east-1 \
  --filters Name=tag:kubernetes.io/created-for/pvc/namespace,Values=aad \
  --query 'Volumes[].VolumeId'

# 4. Recién ahora el destroy (GATED, lo corre una persona). Es el de `infra/` y
#    solamente el de `infra/`: NO destruir `infra/ecr`, ahí viven las imágenes.
cd infra && terraform destroy

# 5. Verificación final: cero instancias.
aws ec2 describe-instances --region us-east-1 \
  --filters Name=tag:Project,Values=armed-and-dangerous \
  Name=instance-state-name,Values=running \
  --query 'Reservations[].Instances[].InstanceId'
```

Por qué dos filtros de volúmenes: `default_tags` del provider no llega a un
volumen creado por el driver CSI (lo crea su propio `CreateVolume`, no
Terraform). El `Project` aparece porque el add-on va configurado con
`controller.extraVolumeTags` (`infra/main.tf`); el segundo filtro usa la etiqueta
que el driver escribe por su cuenta
(`kubernetes.io/created-for/pvc/namespace`, `pkg/driver/constants.go` de
`kubernetes-sigs/aws-ebs-csi-driver`), así que el chequeo sigue en pie aunque esa
configuración se pierda.

### Imágenes multi-arch
`apps/build-multiarch.sh` construye con `docker buildx` las cuatro imágenes
(`aad-java`, `aad-go`, `aad-iperf3` en `linux/amd64,linux/arm64`; `aad-ycsb`
solo en `linux/amd64`, porque el loader es x86). Prueba local sin tocar
ningún registro (exporta un tarball OCI por imagen bajo `apps/build-out/` y
valida que cada tarball tenga las plataformas esperadas):

```
PUSH=0 apps/build-multiarch.sh
```

Push a los repositorios **ECR privados** de la cuenta sandbox (`infra/ecr`),
con `docker buildx imagetools inspect` al final de cada imagen para confirmar
ambos manifests: **queda gated** hasta que el speaker lo autorice
explícitamente. El script deriva el registro en el momento
(`aws sts get-caller-identity` + `aws ecr get-login-password`) y exige un
`AWS_PROFILE` cuyo nombre contenga `sandbox`, igual que el runner. El push se
realiza sin attestations de provenance ni SBOM (el script pasa
`--provenance=false --sbom=false`); quitar las dos flags si se requieren
attestations.

```
AWS_PROFILE=sura-sandbox AWS_REGION=us-east-1 PUSH=1 apps/build-multiarch.sh
```

El script mergea el resultado (un tag y un digest **por imagen**) en
`results/images.json` en vez de sobreescribirlo: una corrida parcial (un solo
positional arg) no toca el tag de las otras tres. Si el mismo día hace falta
reconstruir una imagen que ya se subió, `IMMUTABLE` devuelve
`ImageTagAlreadyExistsException`; la recuperación es `TAG=<fecha>-r2 PUSH=1
apps/build-multiarch.sh <imagen>` (el merge conserva el resto) y el runner
sigue tomando el tag de cada imagen de `results/images.json` solo — no hace
falta tocar nada más. `--image-tag <tag>` es solo para pisar puntualmente una
celda con otro tag que ya esté en ECR (`infra/ecr/README.md`).

Los manifiestos no llevan el registro: nombran las imágenes por nombre pelado y
tag centinela (`aad-java:UNSET`) para que el id de cuenta no entre a git, y el
runner les pone registro y tag al renderizar. El detalle está en
`manifests/base/README.md` y en `runner/README.md`. El espejo en ECR Public para
que la audiencia pueda hacer `docker pull` es opcional (plan Task 12).

## Estructura
```
apps/        java/ (spring-petclinic-rest sobre JDK 25), go/ (baseline stdlib),
             iperf3/, ycsb/ (go-ycsb, amd64 para loader), build-multiarch.sh (buildx → ECR)
infra/       Terraform: EKS 21.25.0, 7 MNG (5 SUT por celda + loader + tools), Karpenter, metrics-server
infra/ecr/   Terraform aparte (estado propio, se aplica una vez): los 4 repos ECR privados
manifests/   base/ (Pyroscope, profiler eBPF, DaemonSets de perillas: C-states y red, StorageClass)
             workloads/<java|mongo|inference|net|go>/ (kustomize base + overlays por celda)
runner/      Python 3.13 + uv: cell.py (orquestador), knee.py, capture.py, cost.py, analysis/, k6/*.js, tests/
results/     JSONs crudos (n≥3 por celda), tarballs/HTML APerf, flame graphs PNG, cost.md, profiler-gate.md
slides/      contenido.md + fuentes.md + assets/ (entregable para la plantilla oficial)
demo/        record.md (plan B grabado) + sanitize-check.sh
docs/        superpowers/{specs,plans}/ (spec y plan v2)
```

## Reglas del repo
Ver `CLAUDE.md`: verify-don't-guess, sandbox gate (perfil cliente prohibido),
presupuesto $200 (estimado v2 $40-70), clúster abajo entre días de lab, el runner
nunca ejecuta terraform, español neutro para la audiencia.