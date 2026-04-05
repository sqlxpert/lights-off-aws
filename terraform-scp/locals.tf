# Start, stop and back up AWS resources tagged with cron schedules
# github.com/sqlxpert/lights-off-aws/  GPLv3  Copyright Paul Marcelin

data "aws_caller_identity" "current" {}
locals {
  caller_arn_parts = provider::aws::arn_parse(
    data.aws_caller_identity.current.arn
  )
  # Provider functions added in Terraform v1.8.0
  # arn_parse added in Terraform AWS provider v5.40.0

  partition = local.caller_arn_parts["partition"]

  module_directory = basename(path.module)
  scp_tags = merge(
    {
      terraform   = "1"
      name_suffix = var.scp_name_suffix
      source      = "github.com/sqlxpert/lights-off-aws/blob/main/${local.module_directory}"
      rights      = "GPLv3. Copyright Paul Marcelin."
    },
    var.scp_tags,
  )
}
