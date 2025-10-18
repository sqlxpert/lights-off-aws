# Start, stop and back up AWS resources tagged with cron schedules
# github.com/sqlxpert/lights-off-aws/  GPLv3  Copyright Paul Marcelin



locals {
  lights_off_stackset_regions = (
    length(var.lights_off_stackset_regions) == 0
    ? [local.region]
    : var.lights_off_stackset_regions
  )
}

data "aws_region" "lights_off_stackset" {
  for_each = toset(local.lights_off_stackset_regions)

  region = each.key
}



data "aws_organizations_organization" "current" {}
data "aws_organizations_organizational_unit" "lights_off_stackset" {
  for_each = toset(var.lights_off_stackset_organizational_unit_names)

  parent_id = data.aws_organizations_organization.current.roots[0].id
  name      = each.key
}



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

  source = "${path.module}/../cloudformation/lights_off_aws.yaml"

  tags = local.lights_off_tags
}



# Both aws_cloudformation_stack_set_instance and aws_cloudformation_stack_set
# need operation_preferences . Updating aws_cloudformation_stack_set.parameters
# affects all StackSet instances.

resource "aws_cloudformation_stack_set" "lights_off" {
  name = "LightsOff${var.lights_off_stackset_name_suffix}"

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
    region_order            = sort(local.lights_off_stackset_regions)
    region_concurrency_type = "PARALLEL"
    max_concurrent_count    = 2
    failure_tolerance_count = 2
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

resource "aws_cloudformation_stack_set_instance" "lights_off" {
  for_each = data.aws_region.lights_off_stackset

  stack_set_name = aws_cloudformation_stack_set.lights_off.name

  call_as = var.lights_off_stackset_call_as

  operation_preferences {
    region_order            = sort(local.lights_off_stackset_regions)
    region_concurrency_type = "PARALLEL"
    max_concurrent_count    = 2
    failure_tolerance_count = 2
  }

  stack_set_instance_region = each.value.region
  deployment_targets {
    organizational_unit_ids = sort([
      for organizational_unit_key, organizational_unit
      in data.aws_organizations_organizational_unit.lights_off_stackset
      : organizational_unit.id
    ])
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
