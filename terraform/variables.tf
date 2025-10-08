# Start, stop and back up AWS resources tagged with cron schedules
# github.com/sqlxpert/lights-off-aws/  GPLv3  Copyright Paul Marcelin

variable "lights_off_params" {
  type        = map(any)
  description = "Map for setting Lights Off CloudFormation stack parameters. Keys, all optional, are parameter names from ../cloudformation/lights_off_aws.yaml . If you set a value other than the empty string for BackupRoleName , BackupVaultName , DoLambdaFnRoleAttachLocalPolicyName , SqsKmsKey , or CloudWatchLogsKmsKey , the module will reference the appropriate Terraform AWS provider data source. For BackupRoleName , omit any role path prefix here in Terraform. Do not set BackupRoleName or BackupVaultName here in Terraform unless you use the sched-backup tag and AWS Backup has already been configured. General note: Terraform performs automatic type conversion when passing values to CloudFormation."

  default = {
    Enable = true

    EnableSchedCloudFormationOps = true

    # Omit these unless you use the sched-backup tag and AWS Backup has already
    # been configured. If mentioned here in Terraform, the default service role
    # and the default vault must already exist.
    # BackupRoleName  = "AWSBackupDefaultServiceRole"
    # BackupVaultName = "Default"

    DoLambdaFnRoleAttachLocalPolicyName = ""

    SqsKmsKey            = ""
    CloudWatchLogsKmsKey = ""
  }
}
