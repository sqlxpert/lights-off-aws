# Start, stop and back up AWS resources tagged with cron schedules
# github.com/sqlxpert/lights-off-aws/  GPLv3  Copyright Paul Marcelin

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
locals {
  caller_arn_parts = provider::aws::arn_parse(data.aws_caller_identity.current.arn)
  # Provider functions added in Terraform v1.8.0
  # arn_parse added in Terraform AWS provider v5.40.0

  partition = local.caller_arn_parts["partition"]

  region = try(
    data.aws_region.current.region, # Added in AWS provider v6.0.0
    data.aws_region.current.name    # Marked deprecated in AWS provider v6.0.0
  )

  account_id = local.caller_arn_parts["account_id"]
}
