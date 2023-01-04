from pulumi_aws import s3
from pulumi import export, ResourceOptions

from settings import general_tags, saleor_storefront_bucket_name, saleor_dashboard_bucket_name, saleor_media_bucket_name, saleor_static_bucket_name

"""
Create three S3 buckets: for the admin dashboard static frontend, media bucket and static assets bucket
"""

# Create the saleor dashboard bucket:
saleor_dashboard_bucket = s3.Bucket("saleor-dashboard-bucket",
    bucket=saleor_dashboard_bucket_name,
    force_destroy=True,
    tags=general_tags
)

# Disable ACL's for saleor dashboard bucket:
saleor_dashboard_bucket_ownership_controls = s3.BucketOwnershipControls("saleor-dashboard-bucket-acl",
    bucket=saleor_dashboard_bucket.id,
    rule=s3.BucketOwnershipControlsRuleArgs(
        object_ownership="BucketOwnerEnforced",
    ))

# Create the saleor media bucket:
saleor_media_bucket = s3.Bucket("saleor-media-bucket",
    bucket=saleor_media_bucket_name,
    force_destroy=True,
    tags=general_tags
)

# Disable ACL's for saleor media bucket:
saleor_media_bucket_ownership_controls = s3.BucketOwnershipControls("saleor-media-bucket-acl",
    bucket=saleor_media_bucket.id,
    rule=s3.BucketOwnershipControlsRuleArgs(
        object_ownership="BucketOwnerEnforced",
    ))

# Create the saleor static assets bucket:
saleor_static_bucket = s3.Bucket("saleor-static-bucket",
    bucket=saleor_static_bucket_name,
    force_destroy=True,
    tags=general_tags
)
# Disable ACL's for saleor static bucket:
saleor_static_bucket_ownership_controls = s3.BucketOwnershipControls("saleor-static-bucket-acl",
    bucket=saleor_static_bucket.id,
    rule=s3.BucketOwnershipControlsRuleArgs(
        object_ownership="BucketOwnerEnforced",
    ))