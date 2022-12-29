from pulumi_aws import elasticache, cloudwatch, ec2, ssm
from pulumi import export, Output

from settings import general_tags, redis_instance_size, demo_private_subnet_cidrs, redis_connection_string_ssm_parameter_name
from subnet_groups import demo_redis_subnet_group
from vpc import demo_vpc

"""
Create the Redis Cloudwatch log group:
"""
demo_redis_loggroup = cloudwatch.LogGroup("demo-redis-loggroup", 
    name=f"/aws/elasticache/redis",
    tags=general_tags,
    retention_in_days=1
)

"""
Create a Redis cluster security group:
"""
demo_redis_security_group = ec2.SecurityGroup(f"demo-redis-security-group",
    description="Redis security group",
    vpc_id=demo_vpc.id,
    tags={**general_tags, "Name": "demo-redis-security-group"}
)

# Allow tcp Redis traffic from application subnets:
demo_redis_security_group_inbound = ec2.SecurityGroupRule("demo-redis-security-group-inbound",
    type="ingress",
    from_port=6379,
    to_port=6379,
    protocol="tcp",
    cidr_blocks=demo_private_subnet_cidrs,
    security_group_id=demo_redis_security_group.id
)

# Allow outbound ANY:
demo_redis_security_group_oubound = ec2.SecurityGroupRule("demo-redis-security-group-outbound",
    type="egress",
    to_port=0,
    protocol="-1",
    from_port=0,
    cidr_blocks=["0.0.0.0/0"],
    security_group_id=demo_redis_security_group.id
)

"""
Create a Redis cluster:
"""
demo_redis_cluster = elasticache.ReplicationGroup("demo-saleor-core-redis-cluster",
    automatic_failover_enabled=True,
    description="Saleor Core Cache",
    node_type=redis_instance_size,
    multi_az_enabled=True,
    parameter_group_name="default.redis7",
    port=6379,
    num_cache_clusters=2,
    subnet_group_name=demo_redis_subnet_group,
    security_group_ids=[demo_redis_security_group.id],
    log_delivery_configurations=[
        elasticache.ReplicationGroupLogDeliveryConfigurationArgs(
            destination=demo_redis_loggroup,
            destination_type="cloudwatch-logs",
            log_format="text",
            log_type="slow-log",
        )
    ],
    tags={**general_tags, "Name": "demo-saleor-core-redis-cluster"}
)
export("redis-primary-endpoint", demo_redis_cluster.primary_endpoint_address)
export("redis-reader-endpoint", demo_redis_cluster.reader_endpoint_address)

redis_endpoint = Output.concat("redis://", demo_redis_cluster.primary_endpoint_address, ":6379")

"""
Populate SSM parameter store with the Redis connection string:
"""
demo_redis_cluster_connection_string = ssm.Parameter("saleor-redis-connection-string",
    name=redis_connection_string_ssm_parameter_name,
    description="Redis connection string for Saleor Core in CACHE_URL format",
    type="SecureString",
    value=redis_endpoint,
    tags={**general_tags, "Name": "saleor-redis-cluster-connection-string"}
)