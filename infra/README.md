# infra — el clúster EKS del lab

Un clúster EKS con siete managed node groups: cinco celdas de medición (un
silicio en una configuración), un `loader` y un `tools`. Las celdas viven en
`min_size = 0`; el runner las sube a 1 (o a 2 en la celda de red) mientras dura
la corrida y las devuelve a 0. Terraform no se ejecuta nunca desde el runner.

> El `apply` y el `destroy` los hace una persona, con el perfil sandbox, y
> solamente cuando el speaker lo autoriza. Escalar una celda de 0 a 1 está
> igual de gated que un `apply`.

## Versiones fijadas (verificadas el 2026-09-04)

| Qué | Valor | Fuente |
|---|---|---|
| Terraform | `>= 1.15` (local 1.15.2; el módulo pide `>= 1.5.7`) | https://raw.githubusercontent.com/terraform-aws-modules/terraform-aws-eks/v21.25.0/versions.tf |
| Provider `hashicorp/aws` | `~> 6.63` (6.63.0, 2026-09-03) | el mismo `versions.tf` exige `>= 6.59` |
| Provider `hashicorp/helm` | `~> 3.3` (3.3.0) | https://registry.terraform.io/v1/providers/hashicorp/helm |
| `terraform-aws-modules/eks/aws` | `~> 21.25` (21.25.0, 2026-08-14) | https://github.com/terraform-aws-modules/terraform-aws-eks/releases |
| `kubernetes_version` | `1.36` (EKS 2026-06-02, soporte estándar hasta 2027-08-02) | https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions.html |
| Karpenter (chart OCI) | `1.14.1` (2026-08-21) | `helm show chart oci://public.ecr.aws/karpenter/karpenter --version 1.14.1` |
| Bottlerocket | variante `aws-k8s-1.36`, mínimo **1.64.0** para THP | https://bottlerocket.dev/en/os/1.64.x/api/settings/kernel/ |
| `ami_type` | `BOTTLEROCKET_x86_64` / `BOTTLEROCKET_ARM_64` | https://docs.aws.amazon.com/eks/latest/APIReference/API_Nodegroup.html |
| Add-ons | `coredns`, `kube-proxy`, `vpc-cni`, `eks-pod-identity-agent`, `aws-ebs-csi-driver`, `metrics-server` | https://docs.aws.amazon.com/eks/latest/userguide/workloads-add-ons-available-eks.html y https://docs.aws.amazon.com/eks/latest/userguide/community-addons.html |

Las tres CRD de Karpenter (`infra/karpenter/`) usan `karpenter.sh/v1` y
`karpenter.k8s.aws/v1`: son las únicas versiones que sirve el chart 1.14.1
(`crds/karpenter.sh_nodepools.yaml`, `crds/karpenter.k8s.aws_ec2nodeclasses.yaml`).

## Las siete node groups

| Node group | Instancia | AMI | min/max/desired | Etiqueta | Distintivo |
|---|---|---|---|---|---|
| `aws-aad-mng-x86-stock` | `m8i.4xlarge` | x86_64 | 0/2/0 | `aad/cell=x86-stock` | Bottlerocket tal cual |
| `aws-aad-mng-x86-tuned` | `m8i.4xlarge` | x86_64 | 0/2/0 | `aad/cell=x86-tuned` | THP `always` |
| `aws-aad-mng-x86-smtoff` | `m8i.4xlarge` | x86_64 | 0/1/0 | `aad/cell=x86-smtoff` | THP `always` + `cpu_options` 8 núcleos, 1 hilo |
| `aws-aad-mng-arm-stock` | `m9g.4xlarge` | ARM_64 | 0/2/0 | `aad/cell=arm-stock` | Bottlerocket tal cual |
| `aws-aad-mng-arm-tuned` | `m9g.4xlarge` | ARM_64 | 0/2/0 | `aad/cell=arm-tuned` | THP `always` |
| `aws-aad-mng-loader` | `c7i.4xlarge` | x86_64 | 1/1/1 | `aad/role=loader` | k6, go-ycsb, cliente llama |
| `aws-aad-mng-tools` | `m7g.large` | ARM_64 | 1/1/1 | `aad/role=tools` | Pyroscope y el controlador de Karpenter |

Las cinco celdas llevan el taint `aad/sut=true:NO_SCHEDULE`. En la API de EKS el
efecto se escribe en mayúsculas y con guion bajo (`NO_SCHEDULE`); dentro de un
NodePool de Karpenter, en cambio, se escribe `NoSchedule`.

`max_size = 2` en las cuatro celdas de red, no 1: la celda de iperf3 necesita un
segundo nodo del mismo tipo para el cliente (spec sección 4), y la spec sección 3
dice `max=1`. Se resolvió a favor de la sección 4 porque `max_size` no cuesta
nada mientras `desired_size` siga en 0 y el runner es quien lo mueve.
`x86-smtoff` no corre la celda de red y se queda en 1.

## Reproducir

```bash
cd infra
cp example.tfvars terraform.tfvars   # terraform.tfvars está git-ignored
$EDITOR terraform.tfvars             # vpc_id, CIDRs y AZs reales del sandbox

export AWS_PROFILE=<perfil-sandbox>  # tiene que contener "sandbox"
terraform init
terraform apply                      # GATED: solo con autorización explícita

aws eks update-kubeconfig --region us-east-1 --name aws-aad-eks-lab

# Las CRD de Karpenter recién existen después del apply, así que la NodePool y
# las dos EC2NodeClass se aplican con kubectl, no con Terraform.
kubectl apply -f karpenter/   # desde infra/; equivale a infra/karpenter/ desde la raíz
```

Al final del día de lab:

```bash
# Primero los nodos de Karpenter: no están en el estado de Terraform y el
# destroy no los toca.
kubectl delete nodepool aad-arc --ignore-not-found
kubectl get nodes -l aad/role=arc            # tiene que quedar vacío

terraform destroy                    # GATED igual que el apply
aws ec2 describe-instances --filters Name=tag:Project,Values=armed-and-dangerous \
  Name=instance-state-name,Values=running --query 'Reservations[].Instances[].InstanceId'
# tiene que devolver []
```

## Decisiones que conviene conocer

**Una sola AZ para todo lo que mide.** Se crea una subnet pública en `var.availability_zone`
y ahí viven las siete node groups y los nodos de Karpenter: loader y SUT siempre
en la misma AZ (requisito del runbook de performance de Graviton). EKS exige
"at least two subnets that are in different Availability Zones" para el control
plane, así que hay una segunda subnet chica en otra AZ que se pasa únicamente en
`control_plane_subnet_ids` y nunca en `subnet_ids`: ningún nodo puede caer ahí.
La VPC es preexistente (`var.vpc_id`), se reutiliza su IGW y se crea una route
table propia para no tocar las del dueño.

**THP sin reboot.** `infra/userdata/thp.toml` es el user data de las tres celdas
tuned. Con `ami_type = BOTTLEROCKET_*` y sin AMI propia, `bootstrap_extra_args`
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

**EBS CSI con Pod Identity.** Sin el driver ningún PVC liga y el StatefulSet de
MongoDB queda en Pending (fue el golpe del clúster de kcd). El rol
`aws-aad-ebs-csi` confía en `pods.eks.amazonaws.com` y lleva
`AmazonEBSCSIDriverPolicyV2`, que alcanza porque el driver etiqueta solo lo que
provisiona dinámicamente.

**Karpenter no provisiona el benchmark.** Está para dos slides: el arco
generacional (se parchea el requirement `instance-family` una generación por
vez) y el clip de scale-from-zero. Elige por precio entre los tipos permitidos y
no tiene señal de rendimiento; por eso la lista de familias está cerrada y
`limits.cpu` vale 16, es decir un solo nodo `.4xlarge` a la vez.

## Cosas con las que se tropezó

- La fuente del submódulo es `terraform-aws-modules/eks/aws//modules/karpenter`.
  Con `terraform-aws-modules/eks//modules/karpenter` el init falla: una
  dirección de registro necesita tres o cuatro componentes.
- El provider de Helm 3.x cambió `kubernetes` y `exec` de bloques a atributos
  (`kubernetes = { ... exec = { ... } }`). La sintaxis de 2.x no compila.
- En el módulo v21 la entrada se llama `addons` y la salida `cluster_addons`.
  También `name` y `kubernetes_version`, no `cluster_name` ni `cluster_version`.
- El submódulo de Karpenter agrega sufijo aleatorio al nombre del rol de nodo si
  no se pone `node_iam_role_use_name_prefix = false`, y ese nombre está escrito
  a mano en las dos `EC2NodeClass`.
- No hay output con el nombre pelado de la node group: `node_group_id` es
  `<cluster>:<node group>`, así que `nodegroup_names` corta por el `:`.
- El valor `karpenter.sh/discovery` de los YAML es el nombre del clúster escrito
  literalmente. Si cambia `var.cluster_name` hay que cambiarlo en los tres
  archivos de `infra/karpenter/`.
- `data.aws_ssm_parameter.value` viene marcado como sensible; para compararlo en
  una precondition se usa `insecure_value` (el parámetro es público).
- `data.aws_ecrpublic_authorization_token` solo se emite en `us-east-1`, por eso
  lleva `region` explícita.

## Pendiente de verificar el día del apply

- La versión de Bottlerocket publicada para `aws-k8s-1.36`. Si es menor a
  1.64.0 el plan corta solo; el fallback está comentado en `thp.toml`. Ojo con
  el alcance: el gate prueba que la AMI fijada soporta la perilla, no que el
  nodo la tenga puesta. Antes de medir cualquier celda tuned hay que leerlo en
  el nodo, y si no dice `[always]` la corrida no vale.

  ```bash
  kubectl debug node/<nodo-tuned> -it --image=busybox -- \
    cat /host/sys/kernel/mm/transparent_hugepage/enabled
  # tiene que decir [always]; con [madvise] la celda tuned no está tuneada
  ```
- Que `CpuOptions` sea aceptado en el launch template de una managed node group.
  La documentación de EKS solo enumera lo prohibido y `CpuOptions` no aparece;
  la conclusión es por ausencia y se confirma en el primer apply.
- Capacidad de `m9g.4xlarge` y `m8i.4xlarge` en la AZ elegida. Con una sola AZ y
  `max_size` chico, `InsufficientInstanceCapacity` es un riesgo real; el plan B
  de la spec es mover todas las node groups de AZ antes que cambiar de talla.
