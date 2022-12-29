from pulumi_aws import rds, ec2, ssm
from pulumi import export, ResourceOptions, Output

from settings import general_tags, postgres_instance_size, demo_db_subnet_cidrs, demo_private_subnet_cidrs, sql_user, sql_password, db_name, sql_connection_string_ssm_parameter_name
from subnet_groups import demo_postgresql_subnet_group
from vpc import demo_vpc

"""
Create a PostgreSQL cluster security group:
"""
demo_sql_security_group = ec2.SecurityGroup(f"demo-sql-security-group",
    description="PostgreSQL security group",
    vpc_id=demo_vpc.id,
    tags={**general_tags, "Name": "demo-sql-security-group"}
)

# Allow tcp Redis traffic from application subnets:
demo_sql_security_group_inbound = ec2.SecurityGroupRule("demo-sql-security-group-inbound",
    type="ingress",
    from_port=5432,
    to_port=5432,
    protocol="tcp",
    cidr_blocks=demo_private_subnet_cidrs,
    security_group_id=demo_sql_security_group.id
)

# Allow outbound ANY:
demo_sql_security_group_oubound = ec2.SecurityGroupRule("demo-sql-security-group-outbound",
    type="egress",
    to_port=0,
    protocol="-1",
    from_port=0,
    cidr_blocks=["0.0.0.0/0"],
    security_group_id=demo_sql_security_group.id
)
"""
Create a PostgreSQL cluster:
"""
demo_sql_cluster = rds.Instance("demo-saleor-core-sql-cluster",
    db_subnet_group_name=demo_postgresql_subnet_group.name,
    vpc_security_group_ids=[demo_sql_security_group.id],
    storage_encrypted=True,
    allocated_storage=20,
    storage_type="gp3",
    identifier="saleor",
    multi_az=True,
    engine="postgres",
    engine_version="13.7",
    port=5432,
    performance_insights_enabled=False,
    network_type="IPV4",
    instance_class=postgres_instance_size,
    skip_final_snapshot=True,
    iam_database_authentication_enabled=False,
    auto_minor_version_upgrade=False,
    apply_immediately=True,
    username=sql_user,
    password=sql_password,
    db_name=db_name,
    tags={**general_tags, "Name": "demo-saleor-core-sql-cluster"},
    opts=ResourceOptions(delete_before_replace=True)
)

export("postgres-endpoint", demo_sql_cluster.endpoint)
postgres_endpoint = Output.concat("postgres://", sql_user, ":", sql_password, "@", demo_sql_cluster.endpoint, "/", db_name)

"""
Populate SSM parameter store with the SQL connection string:
"""
demo_sql_cluster_connection_string = ssm.Parameter("saleor-sql-connection-string",
    name=sql_connection_string_ssm_parameter_name,
    description="PostgreSQL connection string for Saleor Core in DATABASE_URL format",
    type="SecureString",
    value=postgres_endpoint,
    tags={**general_tags, "Name": "saleor-sql-cluster-connection-string"}
)