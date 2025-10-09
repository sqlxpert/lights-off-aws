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
  description = "Lights Off CloudFormation stack tag map. Keys, all optional, are tag keys. Values are tag values. This takes precedence over the Terraform AWS provider's default_tags and over tags attributes defined by the module, if the same tag key appears here. To remove tags defined by the module, set terraform and source to null . Warning: CloudFormation propagates stack tags to stack resources, and each AWS service may have different rules for tag key and tag value lengths, characters, and disallowed tag key or tag value contents."

  default = {}
}

variable "lights_off_stack_name_suffix" {
  type        = string
  description = "Optional CloudFormation stack name suffix, for blue/green deployments or other scenarios in which multiple stacks created from the same template are needed in the same region, in the same AWS account."

  default = ""
}
