# infra/ecr — los repositorios privados de las imágenes propias

Cuatro repositorios ECR privados (`aad-java`, `aad-go`, `aad-iperf3`,
`aad-ycsb`) en la cuenta sandbox. Es un root de Terraform **aparte** de `infra/`,
con su propio estado, a propósito: el clúster se crea y se destruye cada día de
lab y los repositorios no.

> **Este root se aplica una vez y NO se destruye entre días de lab.** El
> `terraform destroy` del cierre del día (README raíz, "Cierre del día de lab")
> es el de `infra/` y solamente el de `infra/`. Destruir este borraría las
> imágenes y el día siguiente empezaría con un `docker buildx --push` de media
> hora.

## Por qué ECR y no un registro público

- El pull sale del endpoint regional con el rol IAM del nodo: no hace falta
  ningún secreto de registro en el clúster, ni salida a un registro externo un
  día pago.
- Es una charla de AWS Community Day; el registro que la audiencia espera ver es
  ECR.
- Nada en git lleva el id de cuenta: los manifiestos nombran las imágenes por
  nombre pelado (`aad-java:UNSET`) y el registro se agrega al renderizar
  (`runner/README.md`).

Un espejo en ECR Public para que la audiencia pueda hacer `docker pull` queda
como opcional del Task 12 del plan; no hace falta para correr el lab.

## Versiones y campos verificados (2026-09-04)

| Qué | Valor | Fuente |
|---|---|---|
| Terraform | `>= 1.15` (local 1.15.2) | mismo piso que `infra/versions.tf` |
| Provider `hashicorp/aws` | `~> 6.63` (6.63.0) | mismo pin que `infra/`, `infra/.terraform.lock.hcl` |
| `aws_ecr_repository.image_tag_mutability` | `IMMUTABLE` | https://github.com/hashicorp/terraform-provider-aws/blob/v6.63.0/website/docs/r/ecr_repository.html.markdown — "Must be one of: `MUTABLE`, `IMMUTABLE`, `IMMUTABLE_WITH_EXCLUSION`, or `MUTABLE_WITH_EXCLUSION`. Defaults to `MUTABLE`." |
| `aws_ecr_repository.image_scanning_configuration.scan_on_push` | `true` | misma página — "Indicates whether images are scanned after being pushed to the repository (true) or not scanned (false)." |
| `aws_ecr_lifecycle_policy` | `repository` + `policy` | https://github.com/hashicorp/terraform-provider-aws/blob/v6.63.0/website/docs/r/ecr_lifecycle_policy.html.markdown — `repository` es "Name of the repository to apply the policy", `policy` es "The policy document. This is a JSON formatted string." |
| Regla `tagged` + `tagPatternList` | obligatorio | https://docs.aws.amazon.com/AmazonECR/latest/userguide/lifecycle_policy_parameters.html — "If you specify `tagged`, then you must also specify a `tagPrefixList` value or a `tagPatternList` value"; y "it's best practice to use a `tagPatternList`" |
| `countType: imageCountMoreThan` | conservar 5 | misma página — "images are sorted from youngest to oldest based on `pushed_at_time` and then all images greater than the specified count are expired or archived" |
| Login de Docker | `aws ecr get-login-password --region <region> \| docker login --username AWS --password-stdin <account>.dkr.ecr.<region>.amazonaws.com` | https://docs.aws.amazon.com/AmazonECR/latest/userguide/registry_auth.html (verbatim; el token "is valid for 12 hours"). Referencia del comando CLI: https://docs.aws.amazon.com/cli/latest/reference/ecr/get-login-password.html — sinopsis `get-login-password [--debug] [--region <value>] ...`, sin argumento posicional ni requerido más allá de las opciones. |

`IMMUTABLE` no es una preferencia de seguridad, es el control de la medición: el
tag es la fecha del push y es lo que `results/images.json` le pasa al runner (un
tag por imagen, no uno solo para las cuatro - ver más abajo). Un tag que se
puede mover significa que dos días de lab renderizan el mismo YAML y bajan dos
binarios distintos.

**Recuperación de un re-push el mismo día:** `IMMUTABLE` hace que un segundo
`docker push` con el mismo tag falle con `ImageTagAlreadyExistsException`. La
salida es volver a correr el build con OTRO tag y solo la imagen que hace
falta: `TAG=<fecha>-r2 PUSH=1 apps/build-multiarch.sh <imagen>`. El script
mergea el resultado en `results/images.json` (conserva el tag de las otras
tres, no las toca) y el runner sigue tomando el tag de cada imagen de ese mismo
archivo, sin intervención; `--image-tag <tag>` es solo para pisar puntualmente
una celda, no hace falta para este flujo.

## El pull desde los nodos ya está permitido, no hay que agregar nada

El rol IAM de los nodos lo arma el módulo `terraform-aws-modules/eks/aws`
21.25.0 y ya trae la política de pull adjunta por defecto. Verificado en el
código del módulo que hay bajado en `infra/.terraform/modules/`:

- Managed node groups (las siete del lab):
  `modules/eks-managed-node-group/main.tf`, `aws_iam_role_policy_attachment.this`
  adjunta `AmazonEKSWorkerNodePolicy` y **`AmazonEC2ContainerRegistryReadOnly`**.
- Nodos de Karpenter (días de arco y de clip): `modules/karpenter/main.tf`,
  `aws_iam_role_policy_attachment.node` adjunta `AmazonEKSWorkerNodePolicy` y
  **`AmazonEC2ContainerRegistryPullOnly`**.

Las dos políticas alcanzan para bajar una imagen:
`AmazonEC2ContainerRegistryPullOnly` permite `ecr:GetAuthorizationToken`,
`ecr:BatchGetImage`, `ecr:GetDownloadUrlForLayer` y
`ecr:BatchImportUpstreamImage`
(https://docs.aws.amazon.com/aws-managed-policy/latest/reference/AmazonEC2ContainerRegistryPullOnly.html),
y `AmazonEC2ContainerRegistryReadOnly` es un superconjunto que suma los
`Describe*`/`List*`
(https://docs.aws.amazon.com/aws-managed-policy/latest/reference/AmazonEC2ContainerRegistryReadOnly.html).
Ambas van con `"Resource": "*"`, así que cubren los cuatro repositorios sin
política de repositorio adicional. **No se agrega ninguna política extra al rol
del nodo.**

## Reproducir

```bash
cd infra/ecr
cp example.tfvars terraform.tfvars   # terraform.tfvars está git-ignored
$EDITOR terraform.tfvars             # sandbox_account_id real

export AWS_PROFILE=<perfil-sandbox>  # tiene que contener "sandbox"
terraform init
terraform apply                      # GATED, y UNA sola vez
```

Después del apply, y **una vez por día de lab**, el registro se le deja escrito
al runner en el directorio del día (el archivo está git-ignored porque lleva el
id de cuenta):

```bash
mkdir -p ../../results/$(date +%F)
terraform output -json > ../../results/$(date +%F)/ecr.json
```

Con los repositorios creados, el push de las imágenes (GATED, lo corre una
persona) es:

```bash
cd ../../apps
AWS_PROFILE=<perfil-sandbox> PUSH=1 ./build-multiarch.sh
# mergea en results/images.json un tag + digest por imagen (sin datos de
# cuenta; conserva las imágenes que esta corrida no tocó) y ese archivo SÍ se
# commitea
```

El orden completo del día de lab vive en el README raíz, sección "Reproducir".

## Al terminar el día de lab

Nada. Este root no se toca. El `terraform destroy` del cierre es
`cd infra && terraform destroy`, nunca `cd infra/ecr`.

Si alguna vez hay que borrarlo de verdad (fin de la gira de charlas), los
repositorios tienen `force_delete` en su valor por defecto (`false`), así que un
destroy con imágenes adentro falla en vez de tirar las imágenes sin avisar: hay
que borrarlas a mano primero, deliberadamente.
