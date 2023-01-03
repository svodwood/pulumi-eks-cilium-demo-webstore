from pulumi_aws import iam, ec2, eks, config, cloudwatch
import pulumi_eks as eks_provider
from pulumi import export, ResourceOptions, Output
import pulumi_kubernetes as k8s
from pulumi_kubernetes.helm.v3 import Release, ReleaseArgs, RepositoryOptsArgs

import json

from settings import general_tags, cluster_descriptor, flux_github_repo_owner, flux_github_repo_name, flux_github_token, flux_cli_version, cilium_release_version, saleor_storefront_bucket_name, saleor_dashboard_bucket_name, saleor_media_bucket_name, saleor_static_bucket_name, sql_connection_string_ssm_parameter_name, redis_connection_string_ssm_parameter_name, deployment_region, account_id
from vpc import demo_vpc, demo_private_subnets, demo_eks_cp_subnets
from helpers import create_iam_role, create_oidc_role, create_policy

"""
Shared EKS resources: IAM policies for EKS, Karpenter and Cilium
"""

# Create an EKS cluster role:
eks_iam_role_policy_arns = [
    "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy",
    "arn:aws:iam::aws:policy/AmazonEKSVPCResourceController"
]

eks_iam_role = create_iam_role(f"{cluster_descriptor}-eks-role", "Service", "eks.amazonaws.com", eks_iam_role_policy_arns)

# Create a default node role for Karpenter:
karpenter_default_nodegroup_role_policy_arns = [
    "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",
    "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
    "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
    "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
]

# Cilium CNI service account policies:
cni_service_account_policy_arns = [
    "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy",
    "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
]

"""
A set of custom security groups: one for the EKS cluster and one for the Karpenter-managed nodes.
"""
# Both security groups created below.
"""
Node security group:
"""
# Create a custom default demo EKS cluster nodegroup security group:
demo_nodegroup_security_group = ec2.SecurityGroup(f"custom-node-attach-{cluster_descriptor}",
    description=f"{cluster_descriptor} custom node security group",
    vpc_id=demo_vpc.id,
    tags={**general_tags, "Name": f"custom-node-attach-{cluster_descriptor}", "karpenter.sh/discovery": f"{cluster_descriptor}"}
)

# Allow all node instances to communicate with each other:
demo_nodegroup_security_group_inbound_self = ec2.SecurityGroupRule(f"inbound-eks-node-self-{cluster_descriptor}",
    type="ingress",
    from_port=0,
    to_port=0,
    protocol="-1",
    self=True,
    security_group_id=demo_nodegroup_security_group.id
)

# Allow outbound ANY:
demo_nodegroup_security_group_oubound_custom_cidrs = ec2.SecurityGroupRule(f"outbound-eks-node-{cluster_descriptor}",
    type="egress",
    to_port=0,
    protocol="-1",
    from_port=0,
    cidr_blocks=["0.0.0.0/0"],
    security_group_id=demo_nodegroup_security_group.id
)

"""
Cluster security group:
"""
# Create a default demo EKS cluster security group:
demo_cluster_security_group = ec2.SecurityGroup(f"custom-cluster-attach-{cluster_descriptor}",
    description=f"{cluster_descriptor} custom security group",
    vpc_id=demo_vpc.id,
    tags={**general_tags, "Name": f"custom-cluster-attach-{cluster_descriptor}"}
)

# Allow all traffic from custom Karpenter node security group:
demo_cluster_security_group_inbound_node = ec2.SecurityGroupRule(f"inbound-eks-cp-inbound-node-{cluster_descriptor}",
    type="ingress",
    from_port=0,
    to_port=0,
    protocol="-1",
    source_security_group_id=demo_nodegroup_security_group,
    security_group_id=demo_cluster_security_group.id
)

# Allow kubectl from ANY:
demo_cluster_security_group_inbound_443 = ec2.SecurityGroupRule(f"inbound-eks-cp-443-{cluster_descriptor}",
    type="ingress",
    from_port=443,
    to_port=443,
    protocol="-1",
    cidr_blocks=["0.0.0.0/0"],
    security_group_id=demo_cluster_security_group.id
)

# Allow outbound ANY:
demo_cluster_security_group_oubound_custom_cidrs = ec2.SecurityGroupRule(f"outbound-eks-cp-{cluster_descriptor}",
    type="egress",
    to_port=0,
    protocol="-1",
    from_port=0,
    cidr_blocks=["0.0.0.0/0"],
    security_group_id=demo_cluster_security_group.id
)

# Allow all traffic from cluster SG to nodes after the cluster SG is defined:
demo_nodegroup_security_group_inbound_from_cp = ec2.SecurityGroupRule(f"inbound-eks-node-from-cp-{cluster_descriptor}",
    type="ingress",
    from_port=0,
    to_port=0,
    protocol="-1",
    source_security_group_id=demo_cluster_security_group,
    security_group_id=demo_nodegroup_security_group.id
)

"""
Instance profile for Karpenter-managed nodes:
"""

# Create a default Karpenter node role and instance profile:
karpenter_node_role = create_iam_role(f"KarpenterNodeRole-{cluster_descriptor}", "Service", "ec2.amazonaws.com", karpenter_default_nodegroup_role_policy_arns)
karpenter_instance_profile = iam.InstanceProfile(f"KarpenterNodeInstanceProfile-{cluster_descriptor}",
    role=karpenter_node_role.name,
    name=f"KarpenterNodeInstanceProfile-{cluster_descriptor}"
)

"""
EKS Control Plane:
"""

# Create an EKS log group:
demo_eks_loggroup = cloudwatch.LogGroup("demo-eks-loggroup", 
    name=f"/aws/eks/{cluster_descriptor}/cluster",
    tags=general_tags,
    retention_in_days=1
)

"""
Create an EKS control plane:
"""

# Create the cluster control plane:
demo_eks_cluster = eks_provider.Cluster(f"eks-{cluster_descriptor}",
    name=f"{cluster_descriptor}",
    vpc_id=demo_vpc.id,
    instance_role=karpenter_node_role,
    cluster_security_group=demo_cluster_security_group,
    create_oidc_provider=True,
    version="1.24",
    instance_profile_name=karpenter_instance_profile,
    skip_default_node_group=True,
    service_role=eks_iam_role,
    provider_credential_opts=eks_provider.KubeconfigOptionsArgs(
        profile_name=config.profile,
    ),
    endpoint_private_access=True,
    endpoint_public_access=True,
    enabled_cluster_log_types=["api", "audit", "authenticator", "controllerManager", "scheduler"],
    public_access_cidrs=["0.0.0.0/0"],
    subnet_ids=[s.id for s in demo_eks_cp_subnets],
    default_addons_to_remove=["coredns", "kube-proxy", "vpc-cni"],
    tags={**general_tags, "Name": f"{cluster_descriptor}"},
    fargate=False,
    opts=ResourceOptions(depends_on=[
            demo_nodegroup_security_group,
            eks_iam_role,
            demo_eks_loggroup
        ]))

demo_eks_cluster_oidc_arn = demo_eks_cluster.core.oidc_provider.arn
demo_eks_cluster_oidc_url = demo_eks_cluster.core.oidc_provider.url

# Create an IAM role for Cilium CNI:
iam_role_vpc_cni_service_account_role = create_oidc_role(f"{cluster_descriptor}-cilium", "kube-system", demo_eks_cluster_oidc_arn, demo_eks_cluster_oidc_url, "cilium-operator", cni_service_account_policy_arns)
export("cilium-oidc-role-arn", iam_role_vpc_cni_service_account_role.arn)

# Create a Karpenter IAM role scoped to karpenter namespace:
iam_role_karpenter_controller_policy = create_policy(f"{cluster_descriptor}-karpenter-policy", "karpenter_oidc_role_policy.json")
iam_role_karpenter_controller_service_account_role = create_oidc_role(f"{cluster_descriptor}-karpenter", "karpenter", demo_eks_cluster_oidc_arn, demo_eks_cluster_oidc_url, "karpenter", [iam_role_karpenter_controller_policy.arn])
export("karpenter-oidc-role-arn", iam_role_karpenter_controller_service_account_role.arn)

# Create a kubernetes provider:
role_provider = k8s.Provider(f"{cluster_descriptor}-kubernetes-provider",
    kubeconfig=demo_eks_cluster.kubeconfig,
    enable_server_side_apply=True,
    opts=ResourceOptions(depends_on=[demo_eks_cluster])
)

# Patch the aws-node DaemonSet to make sure it's unshedulable to any node in the cluster, using server side apply:
patch_aws_node = k8s.apps.v1.DaemonSetPatch("aws-node-patch",
    metadata=k8s.meta.v1.ObjectMetaPatchArgs(
        annotations={
            "pulumi.com/patchForce": "true",
        },
        name="aws-node",
        namespace="kube-system"
    ),
    spec=k8s.apps.v1.DaemonSetSpecPatchArgs(
        template=k8s.core.v1.PodTemplateSpecPatchArgs(
            spec=k8s.core.v1.PodSpecPatchArgs(
                affinity=k8s.core.v1.AffinityPatchArgs(
                    node_affinity=k8s.core.v1.NodeAffinityPatchArgs(
                        required_during_scheduling_ignored_during_execution=k8s.core.v1.NodeSelectorPatchArgs(
                            node_selector_terms=[k8s.core.v1.NodeSelectorTermPatchArgs(
                                match_expressions=[k8s.core.v1.NodeSelectorRequirementPatchArgs(
                                    key="kubernetes.io/os",
                                    operator="In",
                                    values=["no-schedule"]
                                )]
                            )]
                        )
                    )
                )
            )
        )
    ),
    opts=ResourceOptions(
        provider=role_provider,
        depends_on=[demo_eks_cluster]
    )
)

cluster_endpoint_fqdn = demo_eks_cluster.core.endpoint

"""
Create a managed node group and install Cilium via helm in parallel. A managed nodegroup will fail to reach a "Ready" state 
without the CNI daemon running and the helm chart will fail to install if no nodes are available. Let the race begin!
"""

# Create a cilium Helm release when the control plane is initialized:
cilium_cni_release = Release("cilium-cni",
    ReleaseArgs(
        chart="cilium",
        version=cilium_release_version,
        namespace="kube-system",
        repository_opts=RepositoryOptsArgs(
            repo="https://helm.cilium.io",
        ),
        values=Output.all(iam_role_vpc_cni_service_account_role.arn, cluster_endpoint_fqdn).apply(
            lambda args:
                {
                "ingressController": {
                    "enabled": True,
                },
                "eni": {
                    "enabled": True,
                    "iamRole": args[0],
                    "updateEC2AdapterLimitViaAPI": True,
                    "awsReleaseExcessIPs": True,
                    "subnetTagsFilter": "cilium-pod-interfaces=private",
                },
                "ipam": {
                    "mode": "eni",
                },
                "egressMasqueradeInterfaces": "eth0",
                "tunnel": "disabled",
                "loadBalancer": {
                    "algorithm": "maglev",
                },
                "kubeProxyReplacement": "strict",
                "k8sServiceHost": args[1].replace("https://",""),
                "hubble": {
                    "relay": {
                        "enabled": True,
                    },
                    "ui": {
                        "enabled": True
                    }
                }
            }
        )
    ),
    opts=ResourceOptions(
        provider=role_provider,
        depends_on=[demo_eks_cluster, patch_aws_node]
    )
)

# Create an initial Nodegroup when the control plane is initialized:
managed_nodegroup = eks_provider.ManagedNodeGroup("cilium-managed-nodegroup",
    cluster=demo_eks_cluster,
    node_group_name="managed-nodegroup",
    node_role=karpenter_node_role,
    subnet_ids=[s.id for s in demo_private_subnets],
    force_update_version=True,
    ami_type="BOTTLEROCKET_ARM_64",
    instance_types=["t4g.medium"],
    scaling_config={
        "desired_size": 2,
        "min_size": 2,
        "max_size": 2
    },
    capacity_type="ON_DEMAND",
    tags={**general_tags, "Name": f"cilium-managed-nodegroup"},
    taints=[
        {
            "key": "node.cilium.io/agent-not-ready",
            "value": "true",
            "effect": "NO_EXECUTE"
        }
    ],
    opts=ResourceOptions(
        depends_on=[demo_eks_cluster, patch_aws_node]
    )
)

# Install CoreDNS addon when the cluster is initialized:
core_dns_addon = eks.Addon("coredns-addon",
    cluster_name=f"{cluster_descriptor}",
    addon_name="coredns",
    addon_version="v1.8.7-eksbuild.3",
    resolve_conflicts="OVERWRITE",
    opts=ResourceOptions(
        depends_on=[managed_nodegroup, cilium_cni_release]
    )
)

"""
Flux controller set-up:
"""

# Create a service account and cluster role binding for flux controller
flux_service_account = k8s.core.v1.ServiceAccount("flux-controller-service-account",
    api_version="v1",
    kind="ServiceAccount",
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name="flux-controller",
        namespace="kube-system"
    ),
    opts=ResourceOptions(
        provider=role_provider,
        depends_on=[demo_eks_cluster]
    )
)

flux_controller_cluster_role_binding = k8s.rbac.v1.ClusterRoleBinding("flux-controller-sa-crb",
    role_ref=k8s.rbac.v1.RoleRefArgs(
        api_group="rbac.authorization.k8s.io",
        kind="ClusterRole",
        name="cluster-admin"
    ),
    subjects=[
        k8s.rbac.v1.SubjectArgs(
            kind="ServiceAccount",
            name="flux-controller",
            namespace="kube-system"
        )
    ],
    opts=ResourceOptions(
        provider=role_provider,
        depends_on=[demo_eks_cluster]
    )
)

# Create the bootstrap job for flux-cli
flux_bootstrap_job = k8s.batch.v1.Job("fluxBootstrapJob",
    opts=ResourceOptions(
        provider=role_provider,
        depends_on=[flux_service_account, flux_controller_cluster_role_binding, core_dns_addon]
    ),
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name="flux-bootstrap-job",
        namespace="kube-system",
        annotations={"pulumi.com/replaceUnready": "true"}
    ),
    spec=k8s.batch.v1.JobSpecArgs(
        backoff_limit=3,
        template=k8s.core.v1.PodTemplateSpecArgs(
            spec=k8s.core.v1.PodSpecArgs(
                service_account_name="flux-controller",
                containers=[k8s.core.v1.ContainerArgs(
                    env=[k8s.core.v1.outputs.EnvVar(
                        name="GITHUB_TOKEN",
                        value=flux_github_token
                    )],
                    command=[
                        "flux",
                        "bootstrap",
                        "github",
                        f"--owner={flux_github_repo_owner}",
                        f"--repository={flux_github_repo_name}",
                        f"--path=./clusters/{cluster_descriptor}",
                        "--private=false",
                        "--personal=true"
                    ],
                    image=f"fluxcd/flux-cli:v{flux_cli_version}",
                    name="flux-bootstrap",
                )],
                restart_policy="OnFailure",
            ),
        ),
    ))

"""
Karpenter namespace to deploy Karpenter controller into:
"""

# Create a karpenter namespace:
karpenter_namespace = k8s.core.v1.Namespace("karpenter-namespace",
    metadata={"name": "karpenter"},
    opts=ResourceOptions(
        provider=role_provider,
        depends_on=[demo_eks_cluster]
    )
)

"""
Set up a service account role for cert-manager, should you need one with this stack
"""
# cert-manager Service Account in kube-system
iam_role_cert_manager_policy = create_policy(f"{cluster_descriptor}-cert-manager-policy", "certmanager_oidc_role_policy.json")
iam_role_cert_manager_service_account_role = create_oidc_role("cert-manager-sa", "kube-system", demo_eks_cluster_oidc_arn, demo_eks_cluster_oidc_url, "cert-manager-sa", [iam_role_cert_manager_policy.arn])
export("cert-manager-oidc-role-arn", iam_role_cert_manager_service_account_role.arn)

"""
Set up a service account role for external-dns, should you need one with this stack
"""
# External DNS Service Account in kube-system
iam_role_external_dns_controller_policy = create_policy(f"{cluster_descriptor}-external-dns-policy", "external_dns_controller_oidc_role_policy.json")
iam_role_external_dns_controller_service_account_role = create_oidc_role("external-dns-controller-sa", "kube-system", demo_eks_cluster_oidc_arn, demo_eks_cluster_oidc_url, "external-dns-controller-sa", [iam_role_external_dns_controller_policy.arn])
export("external-dns-controller-oidc-role-arn", iam_role_external_dns_controller_service_account_role.arn)


"""
Set up namespace and service account for External Secrets operator
"""
external_secrets_core_namespace = k8s.core.v1.Namespace("external-secrets-namespace",
    metadata={"name": "external-secrets"},
    opts=ResourceOptions(
        provider=role_provider,
        depends_on=[demo_eks_cluster]
    )
)

# Add service account role for External Secrets SA to fetch RDS secret from Parameter Store:
external_secrets_service_account_policy = iam.Policy("external-secrets-sa-policy",
    description="External Secrets Service Account SSM Parameter Store Policy",
    policy=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Action": [
                "ssm:GetParameter",
                "ssm:GetParametersByPath",
                "ssm:GetParameters"
            ],
            "Effect": "Allow",
            "Resource": [
                f"arn:aws:ssm:{deployment_region}:{account_id}:parameter/{sql_connection_string_ssm_parameter_name}",
                f"arn:aws:ssm:{deployment_region}:{account_id}:parameter/{redis_connection_string_ssm_parameter_name}"
            ]
        }],
    })
)

# External Secrets IAM role for service account:
iam_role_external_secrets_service_account_role = create_oidc_role("external-secrets-sa", "external-secrets", demo_eks_cluster_oidc_arn, demo_eks_cluster_oidc_url, "external-secrets-sa", [external_secrets_service_account_policy.arn])
export("external-secrets-oidc-role-arn", iam_role_external_secrets_service_account_role.arn)

"""
Set up namespaces and service accounts for Saleor components
"""
# Saleor Core namespace
saleor_core_namespace = k8s.core.v1.Namespace("saleor-core-namespace",
    metadata={"name": "saleor-core"},
    opts=ResourceOptions(
        provider=role_provider,
        depends_on=[demo_eks_cluster]
    )
)

# Saleor Core service account policy:
saleor_core_service_account_policy = iam.Policy("saleor-core-sa-policy",
    description="Saleor Core Service Account S3 Bucket Policy",
    policy=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Action": [
                "s3:*"
            ],
            "Effect": "Allow",
            "Resource": [
                f"arn:aws:s3:::{saleor_media_bucket_name}",
                f"arn:aws:s3:::{saleor_media_bucket_name}/*",
                f"arn:aws:s3:::{saleor_static_bucket_name}",
                f"arn:aws:s3:::{saleor_static_bucket_name}/*"
            ]
        }],
    })
)

# Saleor Core IAM role for service account:
iam_role_saleor_core_service_account_role = create_oidc_role("saleor-core-sa", "saleor-core", demo_eks_cluster_oidc_arn, demo_eks_cluster_oidc_url, "saleor-core-sa", [saleor_core_service_account_policy.arn])
export("saleor-core-oidc-role-arn", iam_role_saleor_core_service_account_role.arn)

# Saleor Dashboard namespace
saleor_dashboard_namespace = k8s.core.v1.Namespace("saleor-dashboard-namespace",
    metadata={"name": "saleor-dashboard"},
    opts=ResourceOptions(
        provider=role_provider,
        depends_on=[demo_eks_cluster]
    )
)

# Saleor Dashboard service account policy:
saleor_dashboard_service_account_policy = iam.Policy("saleor-dashboard-sa-policy",
    description="Saleor Dashboard Service Account S3 Bucket Policy",
    policy=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Action": [
                "s3:GetObject",
                "s3:ListBucket"
            ],
            "Effect": "Allow",
            "Resource": [
                f"arn:aws:s3:::{saleor_dashboard_bucket_name}",
                f"arn:aws:s3:::{saleor_dashboard_bucket_name}/*"
            ]
        }],
    })
)

iam_role_saleor_dashboard_service_account_role = create_oidc_role("saleor-dashboard-sa", "saleor-dashboard", demo_eks_cluster_oidc_arn, demo_eks_cluster_oidc_url, "saleor-dashboard-sa", [saleor_dashboard_service_account_policy.arn])
export("saleor-dashboard-oidc-role-arn", iam_role_saleor_dashboard_service_account_role.arn)

# Saleor Storefront namespace
saleor_storefront_namespace = k8s.core.v1.Namespace("saleor-storefront-namespace",
    metadata={"name": "saleor-storefront"},
    opts=ResourceOptions(
        provider=role_provider,
        depends_on=[demo_eks_cluster]
    )
)

# Saleor Storefront service account policy:
saleor_storefront_service_account_policy = iam.Policy("saleor-storefront-sa-policy",
    description="Saleor Storefront Service Account S3 Bucket Policy",
    policy=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Action": [
                "s3:GetObject",
                "s3:ListBucket"
            ],
            "Effect": "Allow",
            "Resource": [
                f"arn:aws:s3:::{saleor_storefront_bucket_name}",
                f"arn:aws:s3:::{saleor_storefront_bucket_name}/*"
            ]
        }],
    })
)

# Saleor Storefront IAM role for service account:
iam_role_saleor_storefront_service_account_role = create_oidc_role("saleor-storefront-sa", "saleor-storefront", demo_eks_cluster_oidc_arn, demo_eks_cluster_oidc_url, "saleor-storefront-sa", [saleor_storefront_service_account_policy.arn])
export("saleor-storefront-oidc-role-arn", iam_role_saleor_storefront_service_account_role.arn)

# Saleor Static Assets namespace
saleor_assets_namespace = k8s.core.v1.Namespace("saleor-assets-namespace",
    metadata={"name": "saleor-assets"},
    opts=ResourceOptions(
        provider=role_provider,
        depends_on=[demo_eks_cluster]
    )
)

# Saleor Assets service account policy:
saleor_assets_service_account_policy = iam.Policy("saleor-assets-sa-policy",
    description="Saleor Assets Service Account S3 Bucket Policy",
    policy=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Action": [
                "s3:GetObject",
                "s3:ListBucket"
            ],
            "Effect": "Allow",
            "Resource": [
                f"arn:aws:s3:::{saleor_media_bucket_name}",
                f"arn:aws:s3:::{saleor_media_bucket_name}/*",
                f"arn:aws:s3:::{saleor_static_bucket_name}",
                f"arn:aws:s3:::{saleor_static_bucket_name}/*"
            ]
        }],
    })
)

# Saleor Assets IAM role for service account:
iam_role_saleor_assets_service_account_role = create_oidc_role("saleor-assets-sa", "saleor-assets", demo_eks_cluster_oidc_arn, demo_eks_cluster_oidc_url, "saleor-assets-sa", [saleor_assets_service_account_policy.arn])
export("saleor-assets-oidc-role-arn", iam_role_saleor_assets_service_account_role.arn)