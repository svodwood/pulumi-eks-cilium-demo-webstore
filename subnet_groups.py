from pulumi_aws import rds, elasticache

from settings import general_tags
from vpc import demo_vpc, demo_db_subnets

demo_postgresql_subnet_group = rds.SubnetGroup("demo-postgresql-subnet-group",
    subnet_ids=[s.id for s in demo_db_subnets],
    description="Saleor PostgreSQL Subnet Group",
    tags={**general_tags, "Name": f"demo-postgresql-subnet-group"}
)

demo_redis_subnet_group = elasticache.SubnetGroup("demo-redis-subnet-group",
    subnet_ids=[s.id for s in demo_db_subnets],
    description="Saleor Redis Subnet Group",
    tags={**general_tags, "Name": f"demo-redis-subnet-group"}
)