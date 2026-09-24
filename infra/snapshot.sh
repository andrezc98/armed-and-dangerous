#!/usr/bin/env bash
# Read-only snapshot of the lab as it stands, for the diagrams and slides that
# get drawn after `terraform destroy` (the cluster only exists on lab days).
#
#   AWS_PROFILE=<perfil-sandbox> infra/snapshot.sh [results/<date>]
#
# Writes results/<date>/inventory-raw/ (git-ignored: ARNs and ids carry the
# account number) and results/<date>/inventory/ (the same files with the account
# id replaced by <account>, safe to commit). Nodes are filed by their aad/cell or
# aad/role label, so running it again while another SUT node group is up adds
# that node and keeps the ones already captured.
set -euo pipefail

REGION=us-east-1
CLUSTER=aws-aad-eks-lab
DAY=${1:-results/$(date +%F)}
RAW=$DAY/inventory-raw
OUT=$DAY/inventory
mkdir -p "$RAW/nodes" "$RAW/nodegroups" "$RAW/addons" "$OUT"

aws() { command aws --region "$REGION" --output json "$@"; }
k() { kubectl "$@"; }

echo "# cluster, add-ons, access"
aws eks describe-cluster --name "$CLUSTER" > "$RAW/cluster.json"
for a in $(aws eks list-addons --cluster-name "$CLUSTER" --query 'addons[]' --output text); do
  aws eks describe-addon --cluster-name "$CLUSTER" --addon-name "$a" > "$RAW/addons/$a.json"
done
aws eks list-access-entries --cluster-name "$CLUSTER" > "$RAW/access-entries.json"

echo "# node groups and their launch templates (Bottlerocket settings decoded)"
for ng in $(aws eks list-nodegroups --cluster-name "$CLUSTER" --query 'nodegroups[]' --output text); do
  aws eks describe-nodegroup --cluster-name "$CLUSTER" --nodegroup-name "$ng" > "$RAW/nodegroups/$ng.json"
  lt=$(python3 -c "import json,sys;d=json.load(open(sys.argv[1]))['nodegroup'].get('launchTemplate') or {};print(d.get('id',''),d.get('version',''))" "$RAW/nodegroups/$ng.json")
  if [ -n "${lt% *}" ]; then
    aws ec2 describe-launch-template-versions --launch-template-id "${lt% *}" --versions "${lt#* }" \
      > "$RAW/nodegroups/$ng.launch-template.json"
    python3 - "$RAW/nodegroups/$ng.launch-template.json" "$RAW/nodegroups/$ng.userdata.toml" <<'PY'
import base64, json, sys
data = json.load(open(sys.argv[1]))["LaunchTemplateVersions"][0]["LaunchTemplateData"]
open(sys.argv[2], "w").write(base64.b64decode(data.get("UserData", "")).decode(errors="replace"))
PY
  fi
done

echo "# EC2: instances up now, their AMIs, network"
aws ec2 describe-instances --filters Name=tag:Project,Values=armed-and-dangerous \
  Name=instance-state-name,Values=running > "$RAW/instances.json"
amis=$(python3 -c "import json,sys;print(' '.join(sorted({i['ImageId'] for r in json.load(open(sys.argv[1]))['Reservations'] for i in r['Instances']})))" "$RAW/instances.json")
[ -n "$amis" ] && aws ec2 describe-images --image-ids $amis > "$RAW/amis.json"
vpc=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['cluster']['resourcesVpcConfig']['vpcId'])" "$RAW/cluster.json")
aws ec2 describe-vpcs --vpc-ids "$vpc" > "$RAW/vpc.json"
aws ec2 describe-subnets --filters Name=vpc-id,Values="$vpc" > "$RAW/subnets.json"
aws ec2 describe-security-groups --filters Name=vpc-id,Values="$vpc" > "$RAW/security-groups.json"
aws ec2 describe-route-tables --filters Name=vpc-id,Values="$vpc" > "$RAW/route-tables.json"

echo "# ECR: what the lab pulled"
for r in aad-java aad-go aad-iperf3 aad-ycsb; do
  aws ecr describe-images --repository-name "$r" > "$RAW/ecr-$r.json"
done

echo "# Kubernetes: versions, workloads, storage, helm"
k version -o json > "$RAW/k8s-version.json"
k get nodes -o json > "$RAW/nodes-all.json"
k get daemonsets,deployments,statefulsets,services -A -o json > "$RAW/workloads.json"
k get pods -A -o json > "$RAW/pods.json"
k get storageclass -o json > "$RAW/storageclasses.json"
k get configmaps -n aad -o json > "$RAW/configmaps-aad.json"
helm list -A -o json > "$RAW/helm-releases.json"
for rel in $(helm list -A -q); do
  ns=$(helm list -A -o json | python3 -c "import json,sys;print([r['namespace'] for r in json.load(sys.stdin) if r['name']=='$rel'][0])")
  helm get values "$rel" -n "$ns" -a -o json > "$RAW/helm-$rel-values.json"
done

echo "# per node: object + kubelet config, filed by aad/cell or aad/role"
python3 - "$RAW/nodes-all.json" <<'PY' > "$RAW/.node-names"
import json, sys
for n in json.load(open(sys.argv[1]))["items"]:
    labels = n["metadata"]["labels"]
    print(n["metadata"]["name"], labels.get("aad/cell") or labels.get("aad/role") or "other")
PY
while read -r name key; do
  k get node "$name" -o json > "$RAW/nodes/$key.node.json"
  k get --raw "/api/v1/nodes/$name/proxy/configz" > "$RAW/nodes/$key.kubelet-configz.json" || true
done < "$RAW/.node-names"
rm -f "$RAW/.node-names"

echo "# provenance"
{
  echo "captured_at: $(date -u +%FT%TZ)"
  echo "git_commit: $(git rev-parse HEAD)"
  echo "kubectl_context: $(kubectl config current-context | sed -E 's/[0-9]{12}/<account>/g')"
} > "$RAW/provenance.txt"

echo "# sanitized copy -> $OUT"
account=$(command aws sts get-caller-identity --query Account --output text)
(cd "$RAW" && find . -type f) | while read -r f; do
  mkdir -p "$OUT/$(dirname "$f")"
  sed "s/$account/<account>/g" "$RAW/$f" > "$OUT/$f"
done
if grep -rq "$account" "$OUT"; then echo "account id still present in $OUT" >&2; exit 1; fi
echo "done: $(find "$OUT" -type f | wc -l | tr -d ' ') files"
