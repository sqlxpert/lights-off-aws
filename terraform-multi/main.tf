# Start, stop and back up AWS resources tagged with cron schedules
# github.com/sqlxpert/lights-off-aws/  GPLv3  Copyright Paul Marcelin



# Remove when var.lights_off_stackset_organizational_unit_names is removed.
data "aws_organizations_organization" "current" {}
data "aws_organizations_organizational_unit" "lights_off_stackset" {
  for_each = toset(var.lights_off_stackset_organizational_unit_names)

  parent_id = data.aws_organizations_organization.current.roots[0].id
  name      = each.key
}
# This data source, by its pair of required arguments, must call
# organizations:ListOrganizationalUnitsForParent . Sure enough,
# https://github.com/hashicorp/terraform-provider-aws/blob/5c9e51b/internal/service/organizations/organizational_unit_data_source.go#L52
# To check the existence of arbitrary OUs before passing them to
# CloudFormation, with only OU IDs to go on, we'd need a data source that calls
# DescribeOrganizationalUnit , but there is no such data source as of 2026-03.
# https://github.com/search?q=repo%3Ahashicorp%2Fterraform-provider-aws+DescribeOrganizationalUnit&type=code



resource "aws_s3_bucket" "lights_off_cloudformation" {
  force_destroy = true

  region = local.region

  tags = local.lights_off_tags
}

resource "aws_s3_bucket_versioning" "lights_off_cloudformation" {
  bucket = aws_s3_bucket.lights_off_cloudformation.bucket
  region = local.region

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "lights_off_cloudformation" {
  bucket = aws_s3_bucket.lights_off_cloudformation.bucket
  region = local.region

  ignore_public_acls = true
  block_public_acls  = true

  restrict_public_buckets = true
  block_public_policy     = true
}

resource "aws_s3_bucket_ownership_controls" "lights_off_cloudformation" {
  bucket = aws_s3_bucket.lights_off_cloudformation.bucket
  region = local.region

  rule {
    object_ownership = "BucketOwnerEnforced" # Disable S3 ACLs
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "lights_off_cloudformation" {
  bucket = aws_s3_bucket.lights_off_cloudformation.bucket
  region = local.region

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256" # S3-managed keys
    }
  }
}

resource "aws_s3_object" "lights_off_cloudformation" {
  bucket = aws_s3_bucket.lights_off_cloudformation.bucket
  region = local.region

  depends_on = [
    aws_s3_bucket_versioning.lights_off_cloudformation,
    aws_s3_bucket_public_access_block.lights_off_cloudformation,
    aws_s3_bucket_ownership_controls.lights_off_cloudformation,
    aws_s3_bucket_server_side_encryption_configuration.lights_off_cloudformation,
  ]

  key = "lights_off_aws.yaml"

  source = "${local.cloudformation_path}/lights_off_aws.yaml"
  etag   = filemd5("${local.cloudformation_path}/lights_off_aws.yaml")
  # A template change will yield a new S3 object version.

  tags = local.lights_off_tags
}



# Both aws_cloudformation_stack_set_instance and aws_cloudformation_stack_set
# need operation_preferences . Updating aws_cloudformation_stack_set.parameters
# affects all StackSet instances.

resource "aws_cloudformation_stack_set" "lights_off" {
  name        = "LightsOff${var.lights_off_stackset_name_suffix}"
  description = "Start, stop and back up AWS resources tagged with cron schedules. github.com/sqlxpert/lights-off-aws/  GPLv3  Copyright Paul Marcelin"

  template_url = join("", [
    "https://${aws_s3_bucket.lights_off_cloudformation.bucket_regional_domain_name}/",
    aws_s3_object.lights_off_cloudformation.key,
    "?versionId=${aws_s3_object.lights_off_cloudformation.version_id}"
  ])

  region = local.region

  call_as          = var.lights_off_stackset_call_as
  permission_model = "SERVICE_MANAGED"
  capabilities     = ["CAPABILITY_IAM"]

  operation_preferences {
    # Applies only to aws_cloudformation_stack_set_instance ,
    # not to aws_cloudformation_stack_set :
    # concurrency_mode        = local.operation_preferences["concurrency_mode"]
    region_concurrency_type = local.operation_preferences["region_concurrency_type"]
    region_order            = local.operation_preferences["region_order"]

    max_concurrent_percentage = lookup(
      local.operation_preferences,
      "max_concurrent_percentage",
      null
    )
    max_concurrent_count = lookup(
      local.operation_preferences,
      "max_concurrent_count",
      null
    )

    failure_tolerance_percentage = lookup(
      local.operation_preferences,
      "failure_tolerance_percentage",
      null
    )
    failure_tolerance_count = lookup(
      local.operation_preferences,
      "failure_tolerance_count",
      null
    )
  }

  auto_deployment {
    enabled = false
  }

  parameters = var.lights_off_stackset_params

  tags = local.lights_off_tags

  timeouts {
    update = "4h"
  }

  lifecycle {
    ignore_changes = [
      administration_role_arn,
      operation_preferences[0].region_order,
    ]
  }
}



locals {
  organizational_unit_ids = sort(toset(concat([
    for organizational_unit_key, organizational_unit
    in data.aws_organizations_organizational_unit.lights_off_stackset
    : organizational_unit.id
    ],
    var.lights_off_stackset_organizational_unit_ids,
  )))
  define_instances = (length(local.organizational_unit_ids) > 0)
}

resource "aws_cloudformation_stack_set_instance" "lights_off" {
  for_each = (
    local.define_instances ? data.aws_region.lights_off_stackset : toset([])
  )

  stack_set_name = aws_cloudformation_stack_set.lights_off.name

  call_as = var.lights_off_stackset_call_as

  operation_preferences {
    concurrency_mode        = local.operation_preferences["concurrency_mode"]
    region_concurrency_type = local.operation_preferences["region_concurrency_type"]
    region_order            = local.operation_preferences["region_order"]

    max_concurrent_percentage = lookup(
      local.operation_preferences,
      "max_concurrent_percentage",
      null
    )
    max_concurrent_count = lookup(
      local.operation_preferences,
      "max_concurrent_count",
      null
    )

    failure_tolerance_percentage = lookup(
      local.operation_preferences,
      "failure_tolerance_percentage",
      null
    )
    failure_tolerance_count = lookup(
      local.operation_preferences,
      "failure_tolerance_count",
      null
    )
  }

  stack_set_instance_region = each.key
  deployment_targets {
    organizational_unit_ids = local.organizational_unit_ids
  }
  retain_stack = false

  timeouts {
    create = "4h"
    update = "4h"
    delete = "4h"
  }

  lifecycle {
    ignore_changes = [
      operation_preferences[0].region_order,
    ]
  }
}
