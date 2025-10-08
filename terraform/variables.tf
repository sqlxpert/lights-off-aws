# Start, stop and back up AWS resources tagged with cron schedules
# github.com/sqlxpert/lights-off-aws/  GPLv3  Copyright Paul Marcelin

variable "lights_off_params" {
  type        = map(any)
  description = "Lights Off CloudFormation stack parameter map. Keys, all optional, are parameter names from ../cloudformation/lights_off_aws.yaml ; parameters are described there. Terraform performs automatic type conversion in most cases. Specifying a value other than the empty string for BackupRoleName , BackupVaultName , DoLambdaFnRoleAttachLocalPolicyName , SqsKmsKey or CloudWatchLogsKmsKey causes Terraform to look up the resource, which must exist. For BackupRoleName , omit any role path prefix in Terraform, contrary to the CloudFormation parameter description."

  default = {
    Enable = true

    EnableSchedCloudFormationOps = true

    # Omit in Terraform unless you use the sched-backup tag and AWS Backup has
    # already been configured:
    # BackupRoleName  = "AWSBackupDefaultServiceRole"
    # BackupVaultName = "Default"

    DoLambdaFnRoleAttachLocalPolicyName = ""

    SqsKmsKey            = ""
    CloudWatchLogsKmsKey = ""
  }
}

variable "lights_off_tags" {
  type        = map(any)
  description = "Lights Off CloudFormation stack tag map. Keys, all optional, are tag keys. Values are tag values. This map takes precedence over the Terraform AWS provider's tag_keys map, if the same tag key appears in both. Warning: CloudFormation propagates stack tags to AWS resources, and each AWS service may have different restrictions on tag key and tag value lengths, allowed characters, and disallowed prefixes."

  default = {}
}

variable "lights_off_stack_name_suffix" {
  type        = string
  description = "Optional CloudFormation stack name suffix, for blue/green deployments or other scenarios in which multiple stacks created from the same template are needed in the same region, in the same AWS account."

  default = ""
}
