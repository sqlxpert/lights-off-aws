# Start, stop and back up AWS resources tagged with cron schedules
# github.com/sqlxpert/lights-off-aws/  GPLv3  Copyright Paul Marcelin

data "aws_region" "current" {}

data "aws_region" "lights_off_stackset" {
  for_each = toset(coalescelist(
    var.lights_off_stackset_regions,
    [local.region]
  ))

  region = each.key
}

locals {
  region = coalesce(
    var.lights_off_region,
    data.aws_region.current.region
  )
  # data.aws_region.region added,
  # data.aws_region.name marked deprecated
  # in Terraform AWS provider v6.0.0

  cloudformation_path = "${path.module}/cloudformation"

  module_directory = basename(path.module)
  lights_off_tags = merge(
    {
      terraform = "1"
      source    = "github.com/sqlxpert/lights-off-aws/blob/main/${local.module_directory}"
      rights    = "GPLv3. Copyright Paul Marcelin."
      # CloudFormation stack tag values must be at least 1 character long!
      # https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_Tag.html#API_Tag_Contents
    },
    var.lights_off_tags,
  )

  operation_preferences = merge(
    {
      concurrency_mode = var.lights_off_stackset_operation_preferences[
        "concurrency_mode"
      ]
      region_concurrency_type = var.lights_off_stackset_operation_preferences[
        "region_concurrency_type"
      ]
      region_order = lookup(
        var.lights_off_stackset_operation_preferences,
        "region_order",
        sort(tolist(local.regions_set))
      )

      max_concurrent_count = var.lights_off_stackset_operation_preferences[
        "max_concurrent_count"
      ]
      failure_tolerance_count = var.lights_off_stackset_operation_preferences[
        "failure_tolerance_count"
      ]
    },

    var.lights_off_stackset_operation_preferences["max_concurrent_percentage"] == null
    ? {}
    : {
      max_concurrent_count = null
      max_concurrent_percentage = var.lights_off_stackset_operation_preferences[
        "max_concurrent_percentage"
      ]
    },

    var.lights_off_stackset_operation_preferences["failure_tolerance_percentage"] == null
    ? {}
    : {
      failure_tolerance_count = null
      failure_tolerance_percentage = var.lights_off_stackset_operation_preferences[
        "failure_tolerance_percentage"
      ]
    },
  )
}
