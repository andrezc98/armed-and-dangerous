# infra — el clúster EKS del lab

Un clúster EKS con nueve managed node groups: siete celdas de medición (un
silicio en una configuración), un `loader` y un `tools`. Las celdas viven en
`min_size = 0`; el runner las sube a 1 (o a 2 en la celda de red) mientras dura
la corrida y las devuelve a 0. Terraform no se ejecuta nunca desde el runner.

> El `apply` y el `destroy` los hace una persona, con el perfil sandbox, y
> solamente cuando el speaker lo autoriza. Escalar una celda de 0 a 1 está
> igual de gated que un `apply`.

Los repositorios ECR de las imágenes propias **no** están acá: viven en
`infra/ecr/`, que es un root de Terraform con estado propio, se aplica una sola
vez y **no se destruye entre días de lab**. El `terraform destroy` del cierre es
el de este directorio y solamente el de este directorio.

## Versiones fijadas (verificadas el 2026-09-04)

| Qué | Valor | Fuente |
|---|---|---|
| Terraform | `>= 1.15` (local 1.15.2; el módulo pide `>= 1.5.7`) | https://raw.githubusercontent.com/terraform-aws-modules/terraform-aws-eks/v21.25.0/versions.tf |
| Provider `hashicorp/aws` | `~> 6.63` (6.63.0, 2026-09-03) | el mismo `versions.tf` exige `>= 6.59` |
| `terraform-aws-modules/eks/aws` | `~> 21.25` (21.25.0, 2026-08-14) | https://github.com/terraform-aws-modules/terraform-aws-eks/releases |
| `terraform-aws-modules/vpc/aws` | `~> 6.7` (6.7.2, 2026-08-28; resuelve a 6.7.2) | https://api.github.com/repos/terraform-aws-modules/terraform-aws-vpc/releases/latest y https://raw.githubusercontent.com/terraform-aws-modules/terraform-aws-vpc/v6.7.2/variables.tf (pide `aws >= 6.28`, que el pin `~> 6.63` cumple) |
| `kubernetes_version` | `1.36` (EKS 2026-06-02, soporte estándar hasta 2027-08-02) | https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions.html |
| Karpenter (chart OCI) | `1.14.1` (2026-08-21) | `helm show chart oci://public.ecr.aws/karpenter/karpenter --version 1.14.1` |
| Bottlerocket | variante `aws-k8s-1.36`, mínimo **1.64.0** para THP | https://bottlerocket.dev/en/os/1.64.x/api/settings/kernel/ |
| `ami_type` | `BOTTLEROCKET_x86_64` / `BOTTLEROCKET_ARM_64` | https://docs.aws.amazon.com/eks/latest/APIReference/API_Nodegroup.html |
| Add-ons | `coredns`, `kube-proxy`, `vpc-cni`, `eks-pod-identity-agent`, `aws-ebs-csi-driver`, `metrics-server` | https://docs.aws.amazon.com/eks/latest/userguide/workloads-add-ons-available-eks.html y https://docs.aws.amazon.com/eks/latest/userguide/community-addons.html |
| `configuration_values` del add-on EBS CSI | `controller.extraVolumeTags` | values del chart (`charts/aws-ebs-csi-driver/values.yaml`, `kubernetes-sigs/aws-ebs-csi-driver`); el add-on los toma tal cual vía `--configuration-values` (https://docs.aws.amazon.com/eks/latest/userguide/updating-an-add-on.html) |
| Backend | S3 con `use_lockfile` (bloqueo nativo, Terraform >= 1.10) | https://developer.hashicorp.com/terraform/language/backend/s3 — `use_lockfile`: "Whether to use a lockfile for locking the state file. Defaults to `false`"; en la misma página "DynamoDB-based locking is deprecated and will be removed in a future minor version" |
| Esperar a Karpenter antes de las CRD | `kubectl -n kube-system rollout status deploy/karpenter --timeout=5m` | https://kubernetes.io/docs/reference/kubectl/generated/kubectl_rollout/kubectl_rollout_status/ — "By default 'rollout status' will watch the status of the latest rollout until it's done"; `--timeout` es "The length of time to wait before ending watch, zero means never" |

Las tres CRD de Karpenter (`infra/karpenter/`) usan `karpenter.sh/v1` y
`karpenter.k8s.aws/v1`: son las únicas versiones que sirve el chart 1.14.1
(`crds/karpenter.sh_nodepools.yaml`, `crds/karpenter.k8s.aws_ec2nodeclasses.yaml`).

## Las nueve node groups

| Node group | Instancia | AMI | min/max/desired | Etiqueta | Distintivo |
|---|---|---|---|---|---|
| `aws-aad-mng-x86-stock` | `m8i.4xlarge` | x86_64 | 0/2/0 | `aad/cell=x86-stock` | Bottlerocket tal cual (+ `base.toml`) |
| `aws-aad-mng-x86-tuned` | `m8i.4xlarge` | x86_64 | 0/2/0 | `aad/cell=x86-tuned` | `base.toml` + THP `always` |
| `aws-aad-mng-x86-smtoff` | `m8i.4xlarge` | x86_64 | 0/1/0 | `aad/cell=x86-smtoff` | `base.toml` + THP `always` + `cpu_options` 8 núcleos, 1 hilo |
| `aws-aad-mng-amd-stock` | `m8a.4xlarge` | x86_64 | 0/2/0 | `aad/cell=amd-stock` | Bottlerocket tal cual (+ `base.toml`) |
| `aws-aad-mng-amd-tuned` | `m8a.4xlarge` | x86_64 | 0/2/0 | `aad/cell=amd-tuned` | `base.toml` + THP `always` |
| `aws-aad-mng-arm-stock` | `m9g.4xlarge` | ARM_64 | 0/2/0 | `aad/cell=arm-stock` | Bottlerocket tal cual (+ `base.toml`) |
| `aws-aad-mng-arm-tuned` | `m9g.4xlarge` | ARM_64 | 0/2/0 | `aad/cell=arm-tuned` | `base.toml` + THP `always` |
| `aws-aad-mng-loader` | `c8i.16xlarge` | x86_64 | 1/1/1 | `aad/role=loader` | k6, go-ycsb, cliente llama |
| `aws-aad-mng-tools` | `m7g.large` | ARM_64 | 1/1/1 | `aad/role=tools` | Pyroscope y el controlador de Karpenter |

Las siete celdas llevan el taint `aad/sut=true:NO_SCHEDULE`. En la API de EKS el
efecto se escribe en mayúsculas y con guion bajo (`NO_SCHEDULE`); dentro de un
NodePool de Karpenter, en cambio, se escribe `NoSchedule`.

`max_size = 2` en las seis celdas de red, no 1: la celda de iperf3 necesita un
segundo nodo del mismo tipo para el cliente (spec sección 4), y la spec sección 3
dice `max=1`. Se resolvió a favor de la sección 4 porque `max_size` no cuesta
nada mientras `desired_size` siga en 0 y el runner es quien lo mueve.
`x86-smtoff` no corre la celda de red y se queda en 1.

La columna AMD (`amd-stock`, `amd-tuned`) entró el 2026-09-25 por decisión del
speaker: `m8a.4xlarge` es AMD EPYC 9R45 (Turin), 16 vCPU = 16 núcleos físicos
(`DefaultThreadsPerCore` 1, sin SMT), 4,5 GHz sostenidos, 64 GiB, a
$0.97376/h on-demand en us-east-1 (EC2 `describe-instance-types` y
`pricing get-products`, 2026-09-24). Responde la objeción "el Intel tiene 8
núcleos con SMT; la comparación justa es contra 16 núcleos x86 reales". No hay celda AMD sin SMT
porque no hay SMT que apagar.

## Reproducir

El camino principal es CI: `gh workflow run infra.yml -f root=lab -f action=apply`,
que asume el rol `aws-aad-gha` por OIDC y toma los valores no sensibles de
`ci.tfvars` y el resto de variables del repositorio. El orden completo del día
está en el README raíz. Lo que sigue es el camino local, que sigue siendo válido
y es el fallback.

El estado ya no es local: vive en el bucket S3 que crea `infra/bootstrap/`. Lo
único que no está commiteado del backend es el nombre del bucket, así que el
`init` necesita `-backend-config`.

```bash
# Primera línea del día de lab, siempre. El perfil sandbox tiene us-west-2 por
# default y el lab vive en us-east-1: sin AWS_REGION, cada comando de la CLI
# apunta a la región equivocada.
export AWS_PROFILE=<perfil-sandbox> AWS_REGION=us-east-1

cd infra
cp example.tfvars terraform.tfvars   # terraform.tfvars está git-ignored
$EDITOR terraform.tfvars             # admin_cidrs y sandbox_account_id reales;
                                     # los CIDRs y las AZs ya vienen por default
# admin_cidrs es la lista que puede llegar al endpoint público de la API. En el
# lab es el /32 de salida de la laptop y nada más:
#   curl -s https://checkip.amazonaws.com

cp backend.hcl.example backend.hcl   # backend.hcl está git-ignored
$EDITOR backend.hcl                  # bucket = <terraform -chdir=bootstrap output -raw state_bucket>

terraform init -backend-config=backend.hcl
terraform apply                      # GATED: solo con autorización explícita
# Si el plan corta con "These credentials belong to an account other than the
# sandbox_account_id", el perfil exportado no es el del sandbox. Se revisa con
# `aws sts get-caller-identity`; no se toca el gate.

# El runner nunca ejecuta terraform. Los nombres del clúster y de las node
# groups se los deja escritos una persona, una vez por día de lab, en el
# directorio del día; sin ese archivo el runner se niega a arrancar. El registro
# de las imágenes propias sale del otro root, el mismo día y de la misma forma
# (infra/ecr/README.md). Los dos archivos están git-ignored: llevan el id de
# cuenta.
mkdir -p ../results/$(date +%F)
terraform output -json            > ../results/$(date +%F)/cluster.json
terraform -chdir=ecr output -json > ../results/$(date +%F)/ecr.json

aws eks update-kubeconfig --region us-east-1 --name aws-aad-eks-lab
```

El chart de Karpenter **no** lo instala este `apply`: se instala a mano desde
la laptop, solo el día del arco o del clip (plan Tasks 8 y 9), con el comando y
los values de `manifests/base/README.md`. Este módulo de Terraform deja listo
todo lo que ese chart necesita (rol IAM, rol de nodo, pod identity association,
access entry); recién después de instalarlo con Helm existen las CRD, y recién
entonces se aplican con kubectl la NodePool y las dos EC2NodeClass de
`infra/karpenter/` — hay que esperar el rollout del Deployment o el kubectl
falla con "no matches for kind NodePool":

```bash
kubectl -n kube-system rollout status deploy/karpenter --timeout=5m
kubectl apply -f karpenter/   # desde infra/; equivale a infra/karpenter/ desde la raíz
```

Un día de lab normal no necesita nada de esto: el benchmark corre sobre las
managed node groups y el runner es quien las escala.

Al final del día de lab, el orden canónico está en el README raíz, sección
"Reproducir" → "Cierre del día de lab". En una línea: `helm uninstall karpenter`
(si se instaló) → NodePools → `uv run cell --teardown-day` → esperar a que los
dos `describe-volumes` devuelvan `[]` → `terraform destroy` (GATED) →
`describe-instances` vacío. Ni el chart de Karpenter, ni sus nodos, ni el
volumen EBS del driver CSI están en el estado de Terraform, y por eso van antes
del destroy y no dentro de él.

## Decisiones que conviene conocer

**El pull desde ECR ya está permitido; no se agrega ninguna política.** El rol
IAM de los nodos lo arma el módulo y ya trae adjunta la política de pull.
Verificado en el código del módulo 21.25.0 que está bajado en
`.terraform/modules/` (2026-09-04):

- managed node groups → `modules/eks-managed-node-group/main.tf`,
  `aws_iam_role_policy_attachment.this` adjunta `AmazonEKSWorkerNodePolicy` y
  **`AmazonEC2ContainerRegistryReadOnly`**;
- nodos de Karpenter → `modules/karpenter/main.tf`,
  `aws_iam_role_policy_attachment.node` adjunta `AmazonEKSWorkerNodePolicy` y
  **`AmazonEC2ContainerRegistryPullOnly`**.

`AmazonEC2ContainerRegistryPullOnly` permite `ecr:GetAuthorizationToken`,
`ecr:BatchGetImage`, `ecr:GetDownloadUrlForLayer` y `ecr:BatchImportUpstreamImage`
sobre `"Resource": "*"`
(https://docs.aws.amazon.com/aws-managed-policy/latest/reference/AmazonEC2ContainerRegistryPullOnly.html);
`AmazonEC2ContainerRegistryReadOnly` es un superconjunto
(https://docs.aws.amazon.com/aws-managed-policy/latest/reference/AmazonEC2ContainerRegistryReadOnly.html).
Alcanza para bajar las cuatro imágenes de `infra/ecr` sin política de repositorio
y sin ningún secreto de registro en el clúster.

**La VPC la crea Terraform, y una sola AZ mide.** El lab arma su propia red con
el módulo oficial `terraform-aws-modules/vpc/aws` (`module "vpc"` en `main.tf`):
una VPC `var.vpc_cidr` (default `10.42.0.0/16`) con dos subnets públicas y nada
más. La primera, `var.nodes_subnet_cidr` en `var.availability_zone`, es donde
viven las nueve node groups y los nodos de Karpenter: loader y SUT siempre en la
misma AZ (requisito del runbook de performance de Graviton). EKS exige "at least
two subnets that are in different Availability Zones" para el control plane, así
que la segunda, `var.control_plane_subnet_cidr` en otra AZ, se pasa únicamente en
`control_plane_subnet_ids` y nunca en `subnet_ids`: ningún nodo puede caer ahí.

Ya no hay VPC preexistente ni `var.vpc_id`: el `destroy` del cierre se lleva
también la red, y no queda nada que pueda chocar con la de otra persona. El
módulo crea por su cuenta el internet gateway, la route table pública, su ruta
por default y las asociaciones (`create_igw` es "Controls if an Internet Gateway
is created for public subnets and the related routes that connect them" y viene
en `true`). **Sin NAT gateway**: `enable_nat_gateway = false` y
`single_nat_gateway = false`, que además son los defaults del módulo; los nodos
salen por IP pública (`map_public_ip_on_launch = true`, "Specify true to indicate
that instances launched into the subnet should be assigned a public IP address.
Default is `false`"). Un NAT gateway es lo más caro que este lab podría dejar
prendido sin estar midiendo nada. Citas de
https://raw.githubusercontent.com/terraform-aws-modules/terraform-aws-vpc/v6.7.2/variables.tf
(leído 2026-09-04).

La etiqueta de descubrimiento de Karpenter va en **una** subnet, no en las dos:
`public_subnet_tags_per_az` es "Additional tags for the public subnets where the
primary key is the AZ" (mismo `variables.tf`) y el módulo hace
`lookup(var.public_subnet_tags_per_az, element(var.azs, count.index), {})` sobre
los tags de cada subnet (`main.tf` del módulo en v6.7.2, recurso
`aws_subnet.public`). Con `public_subnet_tags` a secas quedarían etiquetadas las
dos y Karpenter podría poner un nodo en la del control plane.

**CPU exclusiva es un control, no una perilla.** `infra/userdata/base.toml` va en
las **siete** celdas SUT, stock incluidas, y pone el CPU manager del kubelet en
`static`. Sin eso `requests = limits` solo compra QoS Guaranteed: el kubelet
aplica el límite con una cuota CFS y los hilos del pod siguen paseando por los 16
vCPU junto a los DaemonSets y las IRQ. La regla es explícita: "Only containers
that are both part of a Guaranteed pod and have integer CPU requests are assigned
exclusive CPUs" y "The kubelet requires a CPU reservation greater than zero be
made using either `--kube-reserved` and/or `--system-reserved` or
`--reserved-cpus` when the static policy is enabled"
(https://kubernetes.io/docs/tasks/administer-cluster/cpu-management-policies/,
leído 2026-09-04). Los nombres de los ajustes son
`settings.kubernetes.cpu-manager-policy` ("If you want to allow pods with certain
resource characteristics to be granted increased CPU affinity and exclusivity on
the node, you can set this setting to `static`") y
`settings.kubernetes.kube-reserved` ("Resources reserved for node components. The
following keys are valid: `cpu`: in millicores from the total number of vCPUs
available on the instance"), los dos de
https://bottlerocket.dev/en/os/1.64.x/api/settings/kubernetes/ (leído
2026-09-04). Es user data de primer arranque, así que no aplica el "You should
reboot if you change this setting after startup" de esa misma página.

El valor reservado es `cpu = "250m"`, no `1000m`, y la diferencia son dos capas
distintas de contabilidad:

- **cpuset**: el kubelet redondea la reserva hacia arriba ("Take the ceiling of
  the reservation, since fractional CPUs cannot be exclusively allocated",
  `pkg/kubelet/cm/cpumanager/cpu_manager.go`, kubernetes release-1.36), así que
  cualquier valor en (0, 1000m] aparta exactamente **un** vCPU como pool
  compartido: cpu0 se queda con los DaemonSets y cpu1-15 quedan asignables en
  exclusiva.
- **scheduler**: `Allocatable = Capacity - kube-reserved`. Con `1000m` el nodo
  publicaría 15000m, el pod SUT pide 15000m él solo, y kube-proxy + aws-node +
  ebs-csi-node + el profiler (unos 450m juntos) no entrarían nunca: el pod
  medido quedaría Pending para siempre. Con `250m` el nodo publica 15750m y
  entra todo. Misma cuenta en `x86-smtoff`: 8000m − 250m = 7750m contra un pod
  de 7000m.

`cpu-manager-policy-options` queda sin fijar a propósito: `full-pcpus-only`
rechazaría un pedido de 15 vCPU (15 no es un número entero de pares SMT) y el pod
SUT es 15 de 16 por diseño. Y en x86 con SMT el vCPU reservado comparte core
físico con uno de los 15 hilos del pod; es inherente a medir 15 de 16 y va dicho
en el slide, no escondido.

**THP sin reboot.** `infra/userdata/thp.toml` es el user data de las tres celdas
tuned, concatenado con `base.toml` (las dos declaran tablas TOML distintas, así
que la suma sigue siendo un documento válido). Con `ami_type = BOTTLEROCKET_*` y sin AMI propia, `bootstrap_extra_args`
es el user data completo (TOML crudo con sus propios encabezados `[settings.*]`)
y EKS lo mergea sobre el suyo. `settings.kernel.hugepages.transparent.enabled`
existe desde Bottlerocket 1.64.0 ("Add support for static and transparent
hugepages", notas de la release v1.64.0) y se aplica en caliente. Si la AMI
publicada fuese anterior, `terraform_data.bottlerocket_supports_thp` corta el
plan con el mensaje que dice qué hacer: dentro de `thp.toml` está comentada la
ruta alternativa por `settings.boot.kernel-parameters`, que sí cuesta un reboot
extra en el primer arranque del nodo.

Se fija una sola perilla, `enabled = "always"`. `defrag` queda en el default del
sistema operativo tanto en stock como en tuned: "When unset, the defrag policy
is derived from `hugepages.transparent.enabled` (`always` and `madvise` map to
`madvise`, `never` maps to `never`)"
(https://bottlerocket.dev/en/os/1.64.x/api/settings/kernel/). Es además la única
perilla que puede fijar la ruta alternativa por línea de comandos del kernel,
así que las dos rutas producen la misma máquina.

**La AMI que arranca es la AMI que revisa el gate.** Las siete node groups fijan
`ami_release_version` desde el mismo parámetro SSM
`/aws/service/bottlerocket/aws-k8s-1.36/<arch>/latest/image_version` que lee
`terraform_data.bottlerocket_supports_thp`. Para una managed node group
Bottlerocket, el `releaseVersion` que espera EKS es exactamente ese string
(`1.64.0-<hash>`): el módulo mapea cada `ami_type` `BOTTLEROCKET_*` a ese
parámetro —
`BOTTLEROCKET_x86_64 = "/aws/service/bottlerocket/aws-k8s-${local.ssm_kubernetes_version}/x86_64/latest/image_version"`
— y pasa su valor tal cual —
`release_version = var.ami_id != "" ? null : var.use_latest_ami_release_version ? local.latest_ami_release_version : var.ami_release_version`
(https://raw.githubusercontent.com/terraform-aws-modules/terraform-aws-eks/v21.25.0/modules/eks-managed-node-group/main.tf,
líneas 415-416, 437 y 480). La documentación de AWS no publica el formato del
`releaseVersion` de Bottlerocket; la cita es del módulo. Como
`use_latest_ami_release_version` viene en `true` por default y gana sobre
`ami_release_version`, se apaga explícitamente en `nodegroups.tf`.

**SMT off es solo x86.** EC2 pide las dos opciones de CPU juntas, por eso
`core_count = 8` (el default de `m8i.4xlarge`, 8 núcleos por 2 hilos) además de
`threads_per_core = 1`. En Graviton no existe la perilla: "You can't modify the
number of threads per core for ... instances based on the AWS Graviton
processor" (https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instance-optimize-cpu.html).
Esa asimetría es material de slide, no una omisión.

**El endpoint público solo para la laptop del speaker.** El módulo trae
`endpoint_public_access_cidrs` en `["0.0.0.0/0"]` por default ("List of CIDR
blocks which can access the Amazon EKS public API server endpoint",
`variables.tf` de v21.25.0). Aquí se pasa `var.admin_cidrs`, sin default, para
que el `apply` falle si nadie decidió quién entra.

**La AZ se verifica antes de crear nada.**
`terraform_data.instance_types_offered_in_az` corta el plan si la AZ elegida no
ofrece las cinco instancias del lab (`m8i.4xlarge`, `m8a.4xlarge`, `m9g.4xlarge`,
`c8i.16xlarge`, `m7g.large`), en vez de descubrirlo cuando el `loader` no
arranca. Ofrecer no es tener: el gate prueba que la AZ vende el tipo, no que
haya stock. La capacidad se confirma el día del gate, en el apply mismo, y el
plan B de la spec es mover todas las node groups de AZ antes que cambiar de
talla.

**`cluster_name` está clavado.** El valor de `karpenter.sh/discovery` está
escrito literalmente en las dos `EC2NodeClass`, así que `var.cluster_name` lleva
un `validation` que solo acepta `aws-aad-eks-lab` y cuyo mensaje nombra los dos
archivos. Renderizar los YAML con `templatefile` sería más maquinaria de la que
el lab necesita.

**EBS CSI con Pod Identity, y sus etiquetas.** Sin el driver ningún PVC liga y el
StatefulSet de MongoDB queda en Pending (fue el golpe del clúster de kcd). El rol
`aws-aad-ebs-csi` confía en `pods.eks.amazonaws.com` y lleva
`arn:aws:iam::aws:policy/AmazonEBSCSIDriverPolicyV2` (tipo "AWS managed
policy", versión v1, creada el 2026-04-16, sin el tramo `service-role/`:
https://docs.aws.amazon.com/aws-managed-policy/latest/reference/AmazonEBSCSIDriverPolicyV2.html),
que alcanza porque cada acción de escritura ya está acotada a recursos que el
propio driver etiqueta (`ebs.csi.aws.com/cluster`, `CSIVolumeName`,
`kubernetes.io/created-for/pvc/name`), es decir a todo lo que provisiona
dinámicamente.

El add-on además va con `configuration_values`:

```hcl
configuration_values = jsonencode({ controller = { extraVolumeTags = local.tags } })
```

`default_tags` del provider **no** llega a esos volúmenes: los crea el
`CreateVolume` del driver, no Terraform. Sin esa configuración el chequeo de fuga
del final del día (`describe-volumes --filters Name=tag:Project,...`) devolvía
`[]` con un gp3 de 200Gi todavía facturando. El esquema de configuración del
add-on son los values del chart, donde la clave es `controller.extraVolumeTags`
("Extra volume tags to attach to each dynamically provisioned volume",
`charts/aws-ebs-csi-driver/values.yaml` de `kubernetes-sigs/aws-ebs-csi-driver`,
leído 2026-09-04). En ese mismo archivo `controller.extraCreateMetadata` viene en
`true`, que es lo que hace que el volumen lleve también
`kubernetes.io/created-for/pvc/namespace` — el segundo filtro del chequeo, que no
depende de esta configuración
(`PVCNamespaceTag`, `pkg/driver/constants.go` del mismo repo).

**Quién es admin del clúster depende de quién hizo el `apply`.**
`enable_cluster_creator_admin_permissions = true` le da el access entry de admin
a la identidad que corrió el `apply`, y a nadie más. Con el `apply` en CI eso es
el rol `aws-aad-gha`, no la laptop, y el primer `kubectl` del día responde
`error: You must be logged in to the server (Unauthorized)`. Para eso está
`var.cluster_admin_principal_arns` (lista vacía por default, que es exactamente
el comportamiento viejo del camino local): cada ARN de la lista recibe un access
entry con `arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy` y
alcance `type = cluster` (EKS user guide, "Associate access policies with access
entries"). Los ARNs llevan el id de cuenta, así que el valor no vive en el
repositorio: llega como `TF_VAR_cluster_admin_principal_arns` desde la variable
`CLUSTER_ADMIN_ARNS`.

**El gate del sandbox no es solo un nombre de perfil.** `var.sandbox_account_id`
(sin default, valor real en el `terraform.tfvars` git-ignored, placeholder
`000000000000` en `example.tfvars`) se compara con
`data.aws_caller_identity.current.account_id` en una precondition, al lado del
gate de AZ. El runner ya exige un `AWS_PROFILE` cuyo nombre contenga `sandbox`,
pero un nombre de perfil es una cadena que alguien escribe: esta es la mitad
técnica de la misma regla.

**Karpenter va con política inline y sin manejo de spot.** Dos banderas del
submódulo, las dos por el mismo apply fallido del 2026-09-04:

- `enable_inline_policy = true` — "This can be enabled when the error
  `LimitExceeded: Cannot exceed quota for PolicySize: 6144` is received since
  standard IAM policies have a limit of 6,144 characters versus an inline role
  policy's limit of 10,240" (`modules/karpenter/variables.tf` de
  terraform-aws-eks v21.25.0).
- `enable_spot_termination = false` — todo el lab es on-demand (las siete celdas,
  el `loader`, el `tools` y las dos NodePool del arco fijan
  `karpenter.sh/capacity-type: on-demand`), así que la cola SQS y las cuatro
  reglas de EventBridge del submódulo nunca verían un evento. Con la bandera en
  `false` no se crean, y las sentencias de interrupción salen de la política del
  controlador.

Como no hay cola, `manifests/base/karpenter-values.yaml` ya no manda
`settings.interruptionQueue`. El
chart lo tolera: "Interruption queue is the name of the SQS queue used for
processing interruption events from EC2. Interruption handling is disabled if not
specified." con default `""` (`charts/karpenter/values.yaml`,
aws/karpenter-provider-aws v1.14.1), y el Deployment solo emite la variable
`INTERRUPTION_QUEUE` dentro de un `{{- with .Values.settings.interruptionQueue }}`
(`charts/karpenter/templates/deployment.yaml`, mismo tag).

**Karpenter no provisiona el benchmark.** Está para dos slides: el arco
generacional y el clip de scale-from-zero. Elige por precio entre los tipos
permitidos y no tiene señal de rendimiento; por eso la lista de familias está
cerrada y `limits.cpu` vale 16 por pool, es decir un solo nodo `.4xlarge` a la
vez.

Son dos NodePool, una por arquitectura: `aad-arc-amd64` (familias `m5`, `m6i`,
`m7i`, `m8i`, `kubernetes.io/arch = amd64`, `EC2NodeClass`
`aad-bottlerocket-amd64`) y `aad-arc-arm64` (`m6g`, `m7g`, `m8g`, `m9g`,
`arm64`, `aad-bottlerocket-arm64`). Con una sola pool multi-arquitectura las
generaciones Graviton arrancarían por la clase amd64 —arrancan igual, porque el
alias `bottlerocket@latest` resuelve la AMI por arquitectura— pero quedarían
etiquetadas `aad/arch: amd64`, que es justo la etiqueta que lee el arco. El arco
parchea `instance-family` en la pool que corresponde a la generación:

```bash
kubectl patch nodepool aad-arc-arm64 --type merge -p \
  '{"spec":{"template":{"spec":{"requirements":[
     {"key":"karpenter.k8s.aws/instance-family","operator":"In","values":["m7g"]},
     {"key":"karpenter.k8s.aws/instance-size","operator":"In","values":["4xlarge"]},
     {"key":"kubernetes.io/arch","operator":"In","values":["arm64"]},
     {"key":"karpenter.sh/capacity-type","operator":"In","values":["on-demand"]}]}}}}'
```

## Cosas con las que se tropezó

- La fuente del submódulo es `terraform-aws-modules/eks/aws//modules/karpenter`.
  Con `terraform-aws-modules/eks//modules/karpenter` el init falla: una
  dirección de registro necesita tres o cuatro componentes.
- El provider de Helm 3.x cambió `kubernetes` y `exec` de bloques a atributos
  (`kubernetes = { ... exec = { ... } }`). La sintaxis de 2.x no compila. (El
  provider salió del todo el 2026-09-04: el chart de Karpenter se instala desde
  la laptop, no con `helm_release` — ver la sección "Karpenter (solo el día del
  arco o del clip)" de `manifests/base/README.md`.)
- En el módulo v21 la entrada se llama `addons` y la salida `cluster_addons`.
  También `name` y `kubernetes_version`, no `cluster_name` ni `cluster_version`.
- El submódulo de Karpenter agrega sufijo aleatorio al nombre del rol de nodo si
  no se pone `node_iam_role_use_name_prefix = false`, y ese nombre está escrito
  a mano en las dos `EC2NodeClass`.
- No hay output con el nombre pelado de la node group: `node_group_id` es
  `<cluster>:<node group>`, así que `nodegroup_names` corta por el `:`.
- El valor `karpenter.sh/discovery` de los YAML es el nombre del clúster escrito
  literalmente, en las dos `EC2NodeClass`. Por eso `var.cluster_name` lleva un
  `validation` que no deja cambiarlo sin editar antes esos dos archivos.
- `data.aws_ssm_parameter.value` viene marcado como sensible; para compararlo en
  una precondition se usa `insecure_value` (el parámetro es público).
- `data.aws_ecrpublic_authorization_token` solo se emite en `us-east-1`, por eso
  llevaba `region` explícita. (Salió del código el 2026-09-04 junto con el
  `helm_release`, que era su único consumidor. El `helm install` manual no pide
  token: el límite real es el pull no autenticado, "Rate of unauthenticated
  image pulls: 1 per second, not adjustable"
  (https://docs.aws.amazon.com/AmazonECR/latest/public/public-service-quotas.html),
  que una instalación manual y esporádica no roza.)
- El ARN de la política del driver EBS decía
  `arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicyV2` y el apply
  del 2026-09-04 murió ahí con `NoSuchEntity`. V2 existe (creada el 2026-04-16),
  pero es una "AWS managed policy" común y su ARN **no** lleva el tramo
  `service-role/`: es `arn:aws:iam::aws:policy/AmazonEBSCSIDriverPolicyV2`
  (https://docs.aws.amazon.com/aws-managed-policy/latest/reference/AmazonEBSCSIDriverPolicyV2.html).
  El valor viejo era la mezcla de los dos y no nombraba nada. Se quedó con
  `arn:aws:iam::aws:policy/AmazonEBSCSIDriverPolicyV2`, la política V2 sin el
  tramo `service-role/`.
- El apply del 2026-09-04 también cortó con `LimitExceeded: Cannot exceed quota
  for PolicySize: 6144` en la política del controlador de Karpenter. La cuota
  (L-ED111B8C, "Managed policy length") no es ajustable, así que no hay aumento
  que pedir: el submódulo se pasó a `enable_inline_policy = true` (una política
  inline de rol llega a 10.240 caracteres) y a `enable_spot_termination = false`,
  que además saca del documento las sentencias de interrupción.

## Pendiente de verificar el día del apply

- La versión de Bottlerocket publicada para `aws-k8s-1.36`. Si es menor a
  1.64.0 el plan corta solo; el fallback está comentado en `thp.toml`. Atención con
  el alcance: el gate prueba que la AMI fijada soporta la perilla, no que el
  nodo la tenga puesta. Antes de medir cualquier celda tuned hay que leerlo en
  el nodo, y si no dice `[always]` la corrida no vale.

  ```bash
  kubectl debug node/<nodo-tuned> -it --image=busybox -- \
    cat /host/sys/kernel/mm/transparent_hugepage/enabled
  # tiene que decir [always]; con [madvise] la celda tuned no está tuneada
  ```
- Que la política `static` del CPU manager quede efectivamente puesta. Igual que
  con THP, el gate prueba que el ajuste existe, no que el nodo lo tenga aplicado:

  ```bash
  kubectl -n aad exec deploy/java -- cat /sys/fs/cgroup/cpuset.cpus.effective
  # tiene que listar 15 vCPU (por ejemplo 1-15); con 0-15 el pod no tiene cpuset
  # exclusivo y la celda no vale
  ```
- Que `CpuOptions` sea aceptado en el launch template de una managed node group.
  La documentación de EKS solo enumera lo prohibido y `CpuOptions` no aparece;
  la conclusión es por ausencia y se confirma en el primer apply.
- Capacidad de `m9g.4xlarge`, `m8i.4xlarge` y `m8a.4xlarge` en la AZ elegida. El gate de
  ofertas ya descarta la AZ que ni siquiera vende el tipo, pero ofrecer no es
  tener: con una sola AZ y `max_size` chico, `InsufficientInstanceCapacity`
  sigue siendo un riesgo real, y se confirma recién en el apply. El plan B de la
  spec es mover todas las node groups de AZ antes que cambiar de talla.
