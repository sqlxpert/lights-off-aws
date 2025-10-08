# Start, stop and back up AWS resources tagged with cron schedules
# github.com/sqlxpert/lights-off-aws/  GPLv3  Copyright Paul Marcelin

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
locals {
  caller_arn_parts = provider::aws::arn_parse(data.aws_caller_identity.current.arn)
  partition        = local.caller_arn_parts["partition"]
  region           = data.aws_region.current.region
  account_id       = local.caller_arn_parts["account_id"]
}
