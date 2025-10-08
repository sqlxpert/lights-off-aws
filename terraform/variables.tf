# Start, stop and back up AWS resources tagged with cron schedules
# github.com/sqlxpert/lights-off-aws/  GPLv3  Copyright Paul Marcelin

variable "lights_off_params" {
  type        = map(any)
  description = "Map of parameters for the Lights Off CloudFormation stack. Keys, all optional, are parameter names from ../cloudformation/lights_off_aws.yaml . Keep in mind type conversions that Terraform can perform automatically. If you set a value other than the empty string for BackupRoleName , BackupVaultName , DoLambdaFnRoleAttachLocalPolicyName , SqsKmsKey , or CloudWatchLogsKmsKey , the module will reference the appropriate Terraform AWS provider data source."

  default = {
    Enable = true

    EnableSchedCloudFormationOps = true

    BackupRoleName  = "AWSBackupDefaultServiceRole"
    BackupVaultName = "Default"

    DoLambdaFnRoleAttachLocalPolicyName = ""

    SqsKmsKey            = ""
    CloudWatchLogsKmsKey = ""
  }
}
