import pulumi
from pulumi_aws import config, get_caller_identity

"""
Configuration variables from pulumi settings file
"""
stack_config = pulumi.Config()
stack_name = pulumi.get_stack()
aws_provider = get_caller_identity()

"""
General cost tags populated to every single resource in the account:
"""
general_tags = {
    "stack:name": "demo-cilium-stack",
    "stack:pulumi": f"{stack_name}"
}

"""
Misc variables
"""
demo_vpc_cidr = "10.200.0.0/16"

demo_public_subnet_cidrs = [
    "10.200.0.0/20",
    "10.200.16.0/20"
]
demo_private_subnet_cidrs = [
    "10.200.32.0/20",
    "10.200.48.0/20"
]
demo_eks_cp_subnet_cidrs = [
    "10.200.64.0/24",
    "10.200.65.0/24"
]
demo_db_subnet_cidrs = [
    "10.200.66.0/24",
    "10.200.67.0/24"
]

account_id = aws_provider.account_id
deployment_region = config.region
endpoint_services = ["ecr.api","ecr.dkr","ec2","sts","logs","s3","email-smtp","cloudformation"]
cluster_descriptor = "cilium-web-demo"
cilium_release_version = "1.12.5"
redis_instance_size = "cache.t4g.micro"
postgres_instance_size = "db.t4g.small"
db_name = "saleor"
sql_connection_string_ssm_parameter_name = "saleor-sql-connection-string"
redis_connection_string_ssm_parameter_name = "saleor-redis-connection-string"

# Database credentials:
sql_user = stack_config.require_secret("sql-user")
sql_password = stack_config.require_secret("sql-password")

# Make sure to change the below bucket names since these are globally unique!

saleor_storefront_bucket_name = "saleor-storefront-cilium-demo"
saleor_dashboard_bucket_name = "saleor-dashboard-cilium-demo"
saleor_media_bucket_name = "saleor-media-silium-demo"

"""
Flux Bootstrap args
"""
flux_github_repo_owner = stack_config.require("flux-github-repo-owner")
flux_github_repo_name = stack_config.require("flux-github-repo-name")
flux_cli_version = "0.38.2"
flux_github_token = stack_config.require_secret("flux-github-token")