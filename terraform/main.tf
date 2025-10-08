# Start, stop and back up AWS resources tagged with cron schedules
# github.com/sqlxpert/lights-off-aws/  GPLv3  Copyright Paul Marcelin



data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
locals {
  caller_arn_parts = provider::aws::arn_parse(data.aws_caller_identity.current.arn)
  account_id       = local.caller_arn_parts["account_id"]
  region           = data.aws_region.current.region
}



data "aws_iam_role" "lights_off_backup" {
  count = try(var.lights_off_params["BackupRoleName"], "") == "" ? 0 : 1

  name = var.lights_off_params["BackupRoleName"]
}



data "aws_backup_vault" "lights_off" {
  count = try(var.lights_off_params["BackupVaultName"], "") == "" ? 0 : 1

  name = var.lights_off_params["BackupVaultName"]
}



data "aws_iam_policy" "lights_off_do_role_attach" {
  count = try(var.lights_off_params["DoLambdaFnRoleAttachLocalPolicyName"], "") == "" ? 0 : 1

  name = var.lights_off_params["DoLambdaFnRoleAttachLocalPolicyName"]
}



data "aws_kms_alias" "aws_sqs" {
  count = try(var.lights_off_params["SqsKmsKey"], "") == "alias/aws/sqs" ? 1 : 0

  name = "alias/aws/sqs"
}

data "aws_kms_key" "lights_off_sqs" {
  count = try(contains(["", "alias/aws/sqs"], var.lights_off_params["SqsKmsKey"], "")) ? 0 : 1

  key_id = provider::aws::arn_build(
    local.caller_arn_parts["partition"],
    "kms", # service
    local.region,
    split(":", var.lights_off_params["SqsKmsKey"])[0], # account
    split(":", var.lights_off_params["SqsKmsKey"])[1]  # resource (key/KEY_ID)
  )
}



data "aws_kms_key" "lights_off_cloudwatch_logs" {
  count = try(var.lights_off_params["CloudWatchLogsKmsKey"], "") == "" ? 0 : 1

  key_id = provider::aws::arn_build(
    local.caller_arn_parts["partition"],
    "kms", # service
    local.region,
    split(":", var.lights_off_params["CloudWatchLogsKmsKey"])[0], # account
    split(":", var.lights_off_params["CloudWatchLogsKmsKey"])[1]  # resource (key/KEY_ID)
  )
}



locals {
  lights_off_params = merge(
    var.lights_off_params,
    {
      SqsKmsKey = try(
        data.aws_kms_alias.aws_sqs[0].name,
        data.aws_kms_key.lights_off_sqs[0].arn,
        null
      )
      CloudWatchLogsKmsKey = try(
        data.aws_kms_key.lights_off_cloudwatch_logs[0].arn,
        null
      )
    }
  )
}



resource "aws_cloudformation_stack" "lights_off_prereq" {
  name          = "LightsOffPrereq"
  template_body = file("${path.module}/../cloudformation/lights_off_aws_prereq.yaml")

  capabilities = ["CAPABILITY_IAM"]

  policy_body = file(
    "${path.module}/../cloudformation/lights_off_aws_prereq_policy.json"
  )
}

data "aws_iam_role" "lights_off_deploy" {
  name = aws_cloudformation_stack.lights_off_prereq.outputs["DeploymentRoleName"]
}



resource "aws_cloudformation_stack" "lights_off" {
  name          = "LightsOff"
  template_body = file("${path.module}/../cloudformation/lights_off_aws.yaml")

  policy_body = file("${path.module}/../cloudformation/lights_off_aws_policy.json")

  iam_role_arn = data.aws_iam_role.lights_off_deploy.arn

  parameters = local.lights_off_params
}
