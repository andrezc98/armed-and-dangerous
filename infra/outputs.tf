output "cluster_name" {
  description = "EKS cluster name."
  value       = module.eks.cluster_name
}

output "configure_kubectl" {
  description = "Point kubectl at the cluster after `terraform apply`."
  value       = "aws eks update-kubeconfig --region ${var.region} --name ${module.eks.cluster_name}"
}

output "nodegroup_names" {
  description = "Cell (or role) to managed node group name. The runner feeds this to `aws eks update-nodegroup-config --nodegroup-name`."
  # node_group_id is "<cluster>:<node group>"; there is no bare name output.
  value = { for cell, ng in module.eks.eks_managed_node_groups : cell => split(":", ng.node_group_id)[1] }
}

output "karpenter_nodepool_name" {
  description = "NodePool defined in infra/karpenter/nodepool.yaml, patched per generation for the arc."
  value       = "aad-arc"
}

output "subnet_id" {
  description = "The single subnet every node runs in."
  value       = aws_subnet.nodes.id
}

output "node_security_group_id" {
  description = "Node security group, tagged karpenter.sh/discovery."
  value       = module.eks.node_security_group_id
}
