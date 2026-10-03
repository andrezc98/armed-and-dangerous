# ARMed and Dangerous: lo que Graviton5 hace con tus workloads, medido en EKS

Demo repo de la charla (AWS Community Day Argentina 2026, waitlist → ACD Perú
2026 → AWS Women Colombia 2026): tres clases de workload — Java de alta
concurrencia, bases de datos (MongoDB y PostgreSQL) e inferencia LLM en CPU — medidas en el mismo clúster
EKS con nodos x86 (`m8i` Intel y `m8a` AMD) y Graviton5 (`m9g`), explicadas con flame graphs de
eBPF (señal de Profiles de OpenTelemetry) y un harness open source completo.

> Slides: `slides/contenido.md` · fuentes y caveats de cada número:
> `slides/fuentes.md` · spec y plan: `docs/superpowers/`

## Versiones probadas
(se llena con cada corrida; verificar contra docs del día antes de confiar)

- Terraform >= 1.15 + `terraform-aws-modules/eks/aws` 21.25.0, provider aws ~> 6.63, EKS 1.36 con Bottlerocket >= 1.64.0 (ver `infra/README.md`)
- Imágenes propias en ECR privado de la cuenta sandbox: root `infra/ecr` (repos `IMMUTABLE`, scan on push, últimas 5 versiones; ver `infra/ecr/README.md`)
- Karpenter v1.14.1 (chart OCI oficial) · Pyroscope chart 2.2.1 (appVersion 2.2.1; v2.3.0 no tiene chart aún) · k6 v2.2.0
- OTel eBPF profiler `otel/opentelemetry-collector-ebpf-profiler` (tag del día) · APerf (`kubectl-aperf`) · metrics-server (addon EKS)
- Apps (verificado y probado en local 2026-09-03, ver `apps/*/Dockerfile`): `spring-petclinic-rest` master@`4cd8e1b0` (v4.0.2, Boot 4.1.1) sobre `eclipse-temurin:25.0.4_7-jre-noble`, build `maven:3.9.16-eclipse-temurin-25-noble` · Go `golang:1.27.1` + `gcr.io/distroless/static-debian13:nonroot` · `alpine:3.24.1` + iperf3 3.20-r0 · go-ycsb v1.0.3 · k6 `grafana/k6:2.2.0` (imagen oficial, amd64+arm64)
- PostgreSQL `postgres:18.6` (imagen oficial, amd64+arm64, verificada 2026-09-25) con pgbench select-only desde el loader: `manifests/workloads/postgres/README.md`
- Pendientes de Task 5: MongoDB 8.0 y llama.cpp `ghcr.io/ggml-org/llama.cpp:server-b10775` (imágenes oficiales; modelo `unsloth/Llama-3.1-8B-Instruct-GGUF` Q4_0, ver spec §9)
- EKS con Bottlerocket: `m8i.4xlarge` (x86, Xeon 6), `m8a.4xlarge` (x86, AMD EPYC 9R45, 16 núcleos sin SMT; columna agregada el 2026-09-25) y `m9g.4xlarge` (Graviton5), un node group por celda stock/tuned

## El lab en una línea

```
 runner (Mac, sin terraform) ── escala MNG de la celda 0→1 ── aplica overlay (nodeSelector aad/cell)
        │
        ▼
 loader c8i.16xlarge ─ k6 / go-ycsb / pgbench / iperf3 -c ─▶ SUT de la celda (1 pod, taint aad/sut)
                                                             x86-stock | x86-tuned | x86-smtoff  (m8i.4xlarge)
                                                             amd-stock | amd-tuned               (m8a.4xlarge)
                                                             arm-stock | arm-tuned               (m9g.4xlarge)
                                                                │            │
                                   kubectl aperf ───────────────┘            └── DaemonSet profiler eBPF
                                   (PMU: IPC, stalls, TLB)                        ─▶ Pyroscope (tools m7g.large)
        │                                                                               ─▶ flame graphs
        └── knee (ramping) → fija 80% ×n → JSON + tarball APerf + PNG ─▶ results/ ─▶ charts ─▶ slides
```

Una celda = un silicio en una configuración (stock / tuned / SMT off). Cada
workload corre en todas sus celdas; el clúster queda abajo entre días de lab.

## Reproducir
(completar en el Task 12 con el orden real de corrida y el costo medido)

El camino principal es CI. Los `apply` y los `destroy` los dispara una persona
desde GitHub Actions (`.github/workflows/infra.yml`), que asume un rol por OIDC
—no hay ninguna credencial de AWS guardada en el repositorio— y guarda el estado
en un bucket S3. Lo único que se aplica a mano, una sola vez y desde la laptop,
es `infra/bootstrap/`: el bucket, el proveedor OIDC y ese rol. El camino local
con la CLI sigue documentado más abajo como fallback y no cambió.

Lo GATED no cambió de dueño: disparar un workflow de `apply` o de `destroy` es
exactamente igual de gated que correr `terraform apply` en la laptop.

### Una sola vez, para toda la gira de charlas

```bash
# 1. Bootstrap: bucket de estado + proveedor OIDC + rol aws-aad-gha. Local, a
#    mano, GATED. El detalle completo (incluido el formato del claim `sub`, que
#    hay que confirmar antes del apply) está en infra/bootstrap/README.md.
export AWS_PROFILE=<perfil-sandbox> AWS_REGION=us-east-1
cd infra/bootstrap && cp example.tfvars terraform.tfvars && $EDITOR terraform.tfvars
terraform init && terraform apply                      # GATED

# 2. Las cinco variables del repositorio (variables, no secrets: ver por qué en
#    infra/bootstrap/README.md). Ninguna se commitea.
gh variable set AWS_ROLE_ARN        --body "$(terraform output -raw gha_role_arn)"
gh variable set TF_STATE_BUCKET     --body "$(terraform output -raw state_bucket)"
gh variable set SANDBOX_ACCOUNT_ID  --body "<los 12 dígitos de la cuenta sandbox>"
gh variable set ADMIN_CIDRS         --body "[\"$(curl -s https://checkip.amazonaws.com)/32\"]"
# CLUSTER_ADMIN_ARNS: bajo IAM Identity Center, get-caller-identity devuelve un
# ARN de rol asumido (assumed-role/<rol>/<sesión>), que la validation de
# Terraform rechaza y que tampoco sirve como principal de un access entry. Se
# resuelve al ARN del rol (conserva el path /aws-reserved/sso.amazonaws.com/):
ROLE=$(aws sts get-caller-identity --query Arn --output text | \
  sed -E 's#^arn:aws:sts::([0-9]+):assumed-role/([^/]+)/.*#\2#')
ROLE_ARN=$(aws iam get-role --role-name "$ROLE" --query Role.Arn --output text)
gh variable set CLUSTER_ADMIN_ARNS  --body "[\"$ROLE_ARN\"]"

# 3. Los cuatro repositorios ECR privados. Root de Terraform aparte, con estado
#    propio, y NO se destruye entre días de lab.
cd ../.. && gh workflow run infra.yml -f root=ecr -f action=apply   # GATED

# 4. Build multi-arch y push de las cuatro imágenes propias (GATED). El workflow
#    commitea results/images.json solo, con un tag y un digest POR IMAGEN.
gh workflow run images.yml                             # GATED
gh run watch && git pull
```

Si sale mal y hay que repetir el push de una sola imagen el mismo día,
`IMMUTABLE` devuelve `ImageTagAlreadyExistsException` y esa recuperación se hace
por el camino local (más abajo, "Imágenes multi-arch"): el workflow no lleva
inputs de tag ni de subconjunto a propósito.

### Por cada día de lab

```bash
# El /32 de salida de la laptop cambia; es lo único que se re-setea cada día.
gh variable set ADMIN_CIDRS --body "[\"$(curl -s https://checkip.amazonaws.com)/32\"]"

gh workflow run infra.yml -f root=lab -f action=apply   # GATED
gh run watch

# Los outputs los sigue necesitando la laptop, y los dos archivos están
# git-ignored porque llevan el id de cuenta. Con el estado en S3, el init local
# necesita el nombre del bucket (backend.hcl, git-ignored; ver
# infra/backend.hcl.example).
export AWS_PROFILE=<perfil-sandbox> AWS_REGION=us-east-1
mkdir -p results/$(date +%F)
terraform -chdir=infra     init -backend-config=backend.hcl
terraform -chdir=infra     output -json > results/$(date +%F)/cluster.json
terraform -chdir=infra/ecr init -backend-config=backend.hcl
terraform -chdir=infra/ecr output -json > results/$(date +%F)/ecr.json

aws eks update-kubeconfig --region us-east-1 --name aws-aad-eks-lab
kubectl apply -k manifests/base                        # ver manifests/base/README.md
cd runner && uv run cell --workload java --cell arm-tuned --runs 3
# ...el resto de las celdas del día, y al terminar el cierre de abajo.
```

Con el `apply` en CI, el creador del clúster es el rol de CI y no la laptop: sin
`CLUSTER_ADMIN_ARNS` puesta, el primer `kubectl` responde `error: You must be
logged in to the server (Unauthorized)`. Es el punto que más fácil se pasa por
alto al mudar el apply a CI.

### Cierre del día de lab (orden canónico)

Este es el único lugar donde vive el orden: `infra/README.md`,
`manifests/base/README.md` y `runner/README.md` apuntan aquí en vez de repetirlo.
Cada paso existe porque el siguiente no lo cubre — `terraform destroy` no ve los
nodos de Karpenter ni el volumen EBS del driver CSI, porque ninguno de los dos
está en el estado de Terraform, y el workflow no tiene `kubectl`.

```bash
# 1. Chart y NodePools de Karpenter (existen solo en los días de arco / clip).
#    El chart se instaló a mano desde la laptop (manifests/base/README.md) y
#    ni él ni sus nodos están en el estado de Terraform.
helm uninstall karpenter -n kube-system --ignore-not-found
kubectl delete nodepool --all --ignore-not-found
kubectl get nodes -l aad/role=arc            # tiene que quedar vacío

# 2. Todo lo que el runner dejó vivo en el clúster: StatefulSets de Mongo y PostgreSQL, el
#    chart de Pyroscope (antes de su PVC; se reinstala el día siguiente), PVCs,
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

# 4. Recién ahora el destroy (GATED). Es el del root `lab` y solamente ese: NO
#    destruir `ecr`, ahí viven las imágenes. El workflow vuelve a correr los dos
#    describe-volumes del paso 3 y se niega a destruir si queda algo.
gh workflow run infra.yml -f root=lab -f action=destroy
gh run watch

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

### El camino local con la CLI (fallback)

Sigue funcionando entero y es el que se usa si GitHub está caído, si hay que
depurar un plan con las manos, o para la recuperación de un push del mismo día.
Lo único que cambió es que el estado ya no es local: cada root necesita su
`backend.hcl` (copiado de `backend.hcl.example`, git-ignored) en el `init`.

```bash
export AWS_PROFILE=<perfil-sandbox> AWS_REGION=us-east-1

cd infra
cp example.tfvars terraform.tfvars   # git-ignored; admin_cidrs y sandbox_account_id reales
cp backend.hcl.example backend.hcl   # git-ignored; bucket = <state_bucket del bootstrap>
terraform init -backend-config=backend.hcl
terraform apply                      # GATED
```

Con el `apply` local, el creador del clúster vuelve a ser la laptop y
`cluster_admin_principal_arns` puede quedar vacío. El detalle de cada root está
en `infra/README.md` y en `infra/ecr/README.md`; la migración del estado local al
bucket, en `infra/bootstrap/README.md`.

### Imágenes multi-arch
`apps/build-multiarch.sh` construye con `docker buildx` las cuatro imágenes
(`aad-java`, `aad-go`, `aad-iperf3` en `linux/amd64,linux/arm64`; `aad-ycsb`
solo en `linux/amd64`, porque el loader es x86). Prueba local sin tocar
ningún registro (exporta un tarball OCI por imagen bajo `apps/build-out/` y
valida que cada tarball tenga las plataformas esperadas):

```
PUSH=0 apps/build-multiarch.sh
```

El camino normal del push es `gh workflow run images.yml` (arriba). Lo que sigue
es el mismo push desde la laptop, que es el fallback y la única forma de
recuperar un re-push del mismo día.

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
AWS_PROFILE=<perfil-sandbox> AWS_REGION=us-east-1 PUSH=1 apps/build-multiarch.sh
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
.github/     workflows/: infra.yml (plan/apply/destroy de los dos roots por OIDC) e images.yml (build multi-arch + push a ECR)
infra/       Terraform: EKS 21.25.0, 7 MNG (5 SUT por celda + loader + tools), Karpenter, metrics-server
infra/ecr/   Terraform aparte (estado propio, se aplica una vez): los 4 repos ECR privados
infra/bootstrap/ Terraform aparte, a mano y una sola vez: bucket de estado, proveedor OIDC de GitHub, rol aws-aad-gha
manifests/   base/ (Pyroscope, profiler eBPF, DaemonSets de perillas: C-states y red, StorageClass)
             workloads/<java|mongo|postgres|inference|net|go>/ (kustomize base + overlays por celda)
runner/      Python 3.13 + uv: cell.py (orquestador), knee.py, capture.py, cost.py, analysis/, k6/*.js, tests/
results/     JSONs crudos (n≥3 por celda), tarballs/HTML APerf, flame graphs PNG, cost.md, profiler-gate.md
             (los tarballs APerf, ~1.4 GB, están en el release `aperf-raw-2026-09`:
              https://github.com/andrezc98/armed-and-dangerous/releases/tag/aperf-raw-2026-09;
              `tar -xf aperf-raw-2026-09.tar` desde la raíz del repo los deja en su lugar)
slides/      contenido.md + fuentes.md + assets/ (entregable para la plantilla oficial)
demo/        record.md (plan B grabado) + sanitize-check.sh
docs/        superpowers/{specs,plans}/ (spec y plan v2)
```

## Reglas del repo
Ver `CLAUDE.md`: verify-don't-guess, sandbox gate (perfil cliente prohibido),
presupuesto $200 (estimado v2 $40-70), clúster abajo entre días de lab, el runner
nunca ejecuta terraform, español neutro para la audiencia.