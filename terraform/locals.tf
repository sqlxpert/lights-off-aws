# Start, stop and back up AWS resources tagged with cron schedules
# github.com/sqlxpert/lights-off-aws/  GPLv3  Copyright Paul Marcelin

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
locals {
  caller_arn_parts = provider::aws::arn_parse(data.aws_caller_identity.current.arn)
  # Provider functions added in Terraform v1.8.0
  # arn_parse added in Terraform AWS provider v5.40.0

  partition = local.caller_arn_parts["partition"]

  region = (
    var.lights_off_region == ""
    ? data.aws_region.current.region
    : var.lights_off_region
  )
  # data.aws_region.region added,
  # data.aws_region.name marked deprecated
  # in Terraform AWS provider v6.0.0

  lights_off_tags = merge(
    {
      terraform = "1"
      # CloudFormation stack tag values must be at least 1 character long!
      # https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_Tag.html#API_Tag_Contents

      source = "https://github.com/sqlxpert/lights-off-aws/blob/main/terraform"
    },
    var.lights_off_tags,
  )
}
