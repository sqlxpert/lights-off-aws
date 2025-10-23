# Start, stop and back up AWS resources tagged with cron schedules
# github.com/sqlxpert/lights-off-aws/  GPLv3  Copyright Paul Marcelin



variable "lights_off_stack_name_suffix" {
  type        = string
  description = "Optional CloudFormation stack name suffix, for blue/green deployments or other scenarios in which multiple stacks created from the same template are needed in the same region, in the same AWS account."

  default = ""
}



# You may wish to customize this interface, for example by omitting IAM role
# and policy names, the AWS Backup vault name, and KMS key identifiers in
# favor of looking up those resources based on tags.

variable "lights_off_params" {
  type = object({
    Enable                       = optional(bool, true)
    EnableSchedCloudFormationOps = optional(bool, true)

    # If set, will be referenced in data sources, so resources must exist:
    BackupRoleName                      = optional(string, "")
    BackupVaultName                     = optional(string, "")
    DoLambdaFnRoleAttachLocalPolicyName = optional(string, "")
    SqsKmsKey                           = optional(string, "")
    CloudWatchLogsKmsKey                = optional(string, "")

    BackupStartWindowMinutes    = optional(number, 60)
    BackupCompleteWindowMinutes = optional(number, 360)
    BackupColdStorageAfterDays  = optional(number, -1)
    BackupDeleteAfterDays       = optional(number, -1)

    FindLambdaFnMemoryMB    = optional(number, 128)
    FindLambdaFnTimeoutSecs = optional(number, 60)

    DoLambdaFnReservedConcurrentExecutions             = optional(number, -1)
    DoLambdaFnMaximumConcurrency                       = optional(number, 5)
    RequireSameAccountKmsKeyPolicyForEc2StartInstances = optional(bool, false)
    DoLambdaFnBatchSize                                = optional(number, 3)
    DoLambdaFnMemoryMB                                 = optional(number, 128)
    DoLambdaFnTimeoutSecs                              = optional(number, 30)

    OperationQueueVisibilityTimeoutSecs  = optional(number, 90)
    QueueMessageBytesMax                 = optional(number, 32768)
    ErrorQueueMessageRetentionPeriodSecs = optional(number, 604800)

    LogRetentionInDays = optional(number, 7)
    LogLevel           = optional(string, "ERROR")

    # Repeat defaults from cloudformation/lights_off_aws.yaml
  })

  description = "Lights Off CloudFormation stack parameter map. Keys, all optional, are parameter names from cloudformation/lights_off_aws.yaml ; parameters are described there. CloudFormation and Terraform data types match, except for Boolean parameters. Terraform converts bool values to CloudFormation String values automatically. Specifying a value other than the empty string for BackupRoleName , BackupVaultName , DoLambdaFnRoleAttachLocalPolicyName , SqsKmsKey or CloudWatchLogsKmsKey causes Terraform to look up the resource, which must exist. For BackupRoleName , omit any role path prefix in Terraform, contrary to the CloudFormation parameter description. Set BackupRoleName to \"AWSBackupDefaultServiceRole\" and BackupVaultName to \"Default\" in Terraform only if AWS Backup has already been configured."

  default = {}
}



variable "lights_off_tags" {
  type        = map(string)
  description = "Tag map for CloudFormation stacks and other AWS resources. Keys, all optional, are tag keys. Values are tag values. This takes precedence over the Terraform AWS provider's default_tags and over tags attributes defined by the module. To remove tags defined by the module, set the terraform and source tags to null . Warnings: Each AWS service may have different rules for tag key and tag value lengths, characters, and disallowed tag key or tag value contents. CloudFormation propagates stack tags to stack resources. CloudFormation requires stack tag values to be at least 1 character long; empty tag values are not allowed."

  default = {}

  validation {
    error_message = "CloudFormation requires stack tag values to be at least 1 character long; empty tag values are not allowed."

    condition = alltrue([
      for value in values(var.lights_off_tags) : try(length(value) >= 1, true)
    ])
    # Use try to guard against length(null) . Allowing null is necessary here
    # as a means of preventing the setting of a given tag. The more explicit:
    #   (value == null) || (length(value) >= 1)
    # does not work with versions of Terraform released before 2024-12-16.
    # Error: Invalid value for "value" parameter: argument must not be null.
    # https://github.com/hashicorp/hcl/pull/713
  }
}



variable "lights_off_region" {
  type        = string
  description = "Region code for the region in which to create CloudFormation stacks and other AWS resources. The empty string causes the module to use the default region configured for the Terraform AWS provider."

  default = ""
}
