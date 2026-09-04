# infra/bootstrap — el estado remoto y el rol de GitHub Actions

Tres cosas que se crean **una sola vez**, a mano, desde la laptop, y que después
no se tocan más:

1. el bucket S3 donde viven los estados de `infra/` y de `infra/ecr/`;
2. el proveedor de identidad OIDC de GitHub en IAM;
3. el rol `aws-aad-gha`, que es lo que asumen los workflows de
   `.github/workflows/` — sin ninguna credencial guardada en el repositorio.

Este root **no** corre en CI: es el que crea el bucket donde CI guardaría su
estado, así que su propio estado es local (`terraform.tfstate`, git-ignored, en
la máquina de quien lo aplica). Si ese archivo se pierde, lo que hay en la cuenta
sigue funcionando; se recupera con `terraform import` o borrando y recreando los
tres recursos.

> `terraform destroy` de este root borra el bucket con **todos** los estados
> adentro. El bucket va con `force_destroy = false` justamente para que ese
> destroy falle mientras haya objetos. No hay motivo para correrlo.

## Versiones y campos verificados (2026-09-04)

| Qué | Valor | Fuente |
|---|---|---|
| Terraform | `>= 1.15` (local 1.15.2) | mismo piso que los otros dos roots |
| Provider `hashicorp/aws` | `~> 6.63` (6.63.0) | mismo pin que los otros dos roots |
| Backend S3 con `use_lockfile` | Terraform >= 1.10 | `use_lockfile` — "Whether to use a lockfile for locking the state file. Defaults to `false`" (https://developer.hashicorp.com/terraform/language/backend/s3); introducido en v1.10 por hashicorp/terraform#35661. En la misma página: "DynamoDB-based locking is deprecated and will be removed in a future minor version" — por eso no hay tabla DynamoDB en ningún lado |
| `thumbprint_list` del proveedor OIDC | **omitido** | "For certain OIDC identity providers (e.g., Auth0, GitHub, GitLab, Google, ...), AWS relies on its own library of trusted root certificate authorities (CAs) for validation instead of using any configured thumbprints" (aws provider 6.63.0, `r/iam_openid_connect_provider`), y del lado de IAM: "AWS secures communication with OIDC identity providers (IdPs) using our library of trusted root certificate authorities (CAs) [...] If your OIDC IdP relies on a certificate that is not signed by one of these trusted CAs, only then we secure communication using the thumbprints" (https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc.html) |
| URL y audiencia del proveedor | `https://token.actions.githubusercontent.com` / `sts.amazonaws.com` | "For the provider URL: Use `https://token.actions.githubusercontent.com`" y "For the 'Audience': Use `sts.amazonaws.com` if you are using the official action" (https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws) |
| Condición `sub` | `StringEquals` sobre `repo:<owner>/<repo>:environment:lab` | "If you use a workflow with an environment, the `sub` field must reference the environment name: `repo:ORG-NAME/REPO-NAME:environment:ENVIRONMENT-NAME`" (misma página) |
| Política del rol | `arn:aws:iam::aws:policy/AdministratorAccess` | decisión de este lab, ver abajo |

### Antes de aplicar: el formato del claim `sub`

`var.github_sub` viene con la forma clásica
(`repo:andrezc98/armed-and-dangerous:environment:lab`). **Hay que confirmarla
contra el repositorio real.** GitHub documenta que "for repositories created
after July 15, 2026, or that have opted in to immutable subject claims, the
`sub` claim includes immutable owner and repository IDs", y ahí la forma pasa a
ser `repo:OWNER@OWNER-ID/REPO@REPO-ID:environment:lab`
(https://docs.github.com/en/actions/reference/security/oidc). Como este
repositorio todavía no existe en GitHub, va a caer en ese caso: si el default
queda como está, cada job muere en `AssumeRoleWithWebIdentity` con
`Not authorized to perform sts:AssumeRoleWithWebIdentity`.

Después de crear el repositorio, el valor exacto se lee del token del propio
job (el primer `plan` fallido lo dice en el error) o se arma con los ids:

```bash
gh api repos/<owner>/<repo> --jq '.owner.id, .id'
# -> github_sub = "repo:<owner>@<owner-id>/<repo>@<repo-id>:environment:lab"
```

y se pone en `terraform.tfvars` antes del apply.

### Por qué `AdministratorAccess`

El rol construye y destruye un clúster EKS entero con su VPC, sus roles IAM, sus
access entries, sus add-ons y el submódulo de Karpenter, más cuatro repositorios
ECR, en una cuenta sandbox personal que no tiene nada más adentro. Escribir el
mínimo privilegio de esa superficie es un proyecto aparte y habría que rehacerlo
en cada bump de módulo; el radio de explosión ya es la cuenta entera. El gate que
importa es la política de confianza: **un repositorio, un environment**, con
`StringEquals` en `aud` y en `sub`, más la precondition de
`terraform_data.sandbox_account` adentro de los otros dos roots. Least privilege
queda pendiente y no se aplica este root en una cuenta que tenga algo real.

## Aplicar (una sola vez)

```bash
export AWS_PROFILE=<perfil-sandbox> AWS_REGION=us-east-1

cd infra/bootstrap
cp example.tfvars terraform.tfvars   # terraform.tfvars está git-ignored
$EDITOR terraform.tfvars             # sandbox_account_id real; github_sub si aplica

terraform init
terraform apply                      # GATED
```

Salidas:

```bash
terraform output -raw state_bucket   # aws-aad-tfstate-<sufijo generado>
terraform output -raw gha_role_arn   # arn:aws:iam::<cuenta>:role/aws-aad-gha
```

Ninguno de los dos se commitea: el ARN lleva el id de cuenta y el nombre del
bucket es generado.

## Las variables del repositorio en GitHub

Son **variables**, no secrets. Ninguna es sensible en el sentido de una
credencial: un id de cuenta y un ARN no dan acceso a nada por sí solos, y como
variables quedan visibles en el log del run, que es justo lo que se quiere para
auditar contra qué cuenta corrió cada job. Lo que no puede pasar es que queden
**commiteadas**, y por eso no están en `ci.tfvars`.

```bash
gh variable set AWS_ROLE_ARN      --body "$(terraform output -raw gha_role_arn)"
gh variable set TF_STATE_BUCKET   --body "$(terraform output -raw state_bucket)"
gh variable set SANDBOX_ACCOUNT_ID --body "<los 12 dígitos de la cuenta sandbox>"
gh variable set ADMIN_CIDRS       --body '["<egress /32 de la laptop>"]'
gh variable set CLUSTER_ADMIN_ARNS --body '["<ARN de la identidad que corre kubectl>"]'
```

| Variable | Para qué | Forma |
|---|---|---|
| `AWS_ROLE_ARN` | `role-to-assume` de los dos workflows | ARN del rol |
| `TF_STATE_BUCKET` | `-backend-config="bucket=..."` en el `init` | nombre del bucket |
| `SANDBOX_ACCOUNT_ID` | `TF_VAR_sandbox_account_id`, la precondition de cuenta | 12 dígitos |
| `ADMIN_CIDRS` | `TF_VAR_admin_cidrs`, quién llega al endpoint público de la API | lista HCL, p. ej. `["203.0.113.7/32"]` |
| `CLUSTER_ADMIN_ARNS` | `TF_VAR_cluster_admin_principal_arns`, el access entry de la laptop | lista HCL de ARNs IAM |

`ADMIN_CIDRS` cambia cada día de lab (`curl -s https://checkip.amazonaws.com`).
`CLUSTER_ADMIN_ARNS` es el punto que se pasa por alto fácil: cuando el `apply` lo
hace CI, el creador del clúster es el rol de CI, y la laptop que corre `kubectl`,
las CRD de Karpenter y el runner todo el día **no es admin de nada**. Se saca con
`aws sts get-caller-identity --query Arn --output text` y se deja ahí. La
alternativa manual, si se prefiere no tenerlo en Terraform, son dos comandos por
día de lab:

```bash
aws eks create-access-entry --cluster-name aws-aad-eks-lab --principal-arn <arn>
aws eks associate-access-policy --cluster-name aws-aad-eks-lab --principal-arn <arn> \
  --access-scope type=cluster \
  --policy-arn arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy
```

## Migrar los estados locales al bucket

Los dos roots ya tienen su `backend "s3"` en `versions.tf` con todo menos el
nombre del bucket. Una vez por root, con el estado local todavía al lado:

```bash
cd infra
cp backend.hcl.example backend.hcl        # backend.hcl está git-ignored
$EDITOR backend.hcl                       # bucket = <terraform output -raw state_bucket>
terraform init -migrate-state -backend-config=backend.hcl
# Terraform pregunta si copia el estado existente al backend nuevo: sí.

cd ecr
cp backend.hcl.example backend.hcl
$EDITOR backend.hcl
terraform init -migrate-state -backend-config=backend.hcl
```

Después de migrar, los `terraform.tfstate` locales quedan como respaldo muerto y
se pueden borrar; el que manda es el del bucket. Desde la laptop, cualquier
comando posterior necesita el `-backend-config=backend.hcl` en el `init`.
