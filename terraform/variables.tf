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
