# Start, stop and back up AWS resources tagged with cron schedules
# github.com/sqlxpert/lights-off-aws/  GPLv3  Copyright Paul Marcelin



variable "lights_off_stackset_name_suffix" {
  type        = string
  description = "Optional CloudFormation StackSet name suffix, for blue/green deployments or other scenarios in which multiple StackSets created from the same template are needed."

  default = ""
}



locals {
  lights_off_stackset_call_as_values = [
    "SELF",
    "DELEGATED_ADMIN"
  ]

  lights_off_stackset_call_as_values_string = join(
    " , ",
    local.lights_off_stackset_call_as_values
  )
}

variable "lights_off_stackset_call_as" {
  type        = string
  description = "The purpose of the AWS account from which the CloudFormation StackSet is being created: DELEGATED_ADMIN , or SELF for the management account."

  default = "SELF"

  validation {
    error_message = "value must be one of: ${local.lights_off_stackset_call_as_values_string} ."

    condition = contains(
      local.lights_off_stackset_call_as_values,
      var.lights_off_stackset_call_as
    )
  }
}



variable "lights_off_stackset_params" {
  type = object({
    Enable                       = optional(bool, true)
    EnableSchedCloudFormationOps = optional(bool, true)

    BackupRoleName                      = optional(string, "")
    BackupVaultName                     = optional(string, "")
    DoLambdaFnRoleAttachLocalPolicyName = optional(string, "")
    SqsKmsKey                           = optional(string, "")
    CloudWatchLogsKmsKey                = optional(string, "")

    BackupStartWindowMinutes    = optional(number, 60)
    BackupCompleteWindowMinutes = optional(number, 360)
    BackupColdStorageAfterDays  = optional(number, -1)
    BackupDeleteAfterDays       = optional(number, -1)

    FindLambdaFnMemoryMB            = optional(number, 128)
    FindLambdaFnTimeoutSecs         = optional(number, 60)
    FindLambdaFnScheduleExprCronUtc = optional(string, "01,11,21,31,41,51 * * * ? *")

    DoLambdaFnReservedConcurrentExecutions             = optional(number, -1)
    DoLambdaFnMaximumConcurrency                       = optional(number, 5)
    RequireSameAccountKmsKeyPolicyForEc2StartInstances = optional(bool, false)
    DoLambdaFnBatchSize                                = optional(number, 3)
    DoLambdaFnMemoryMB                                 = optional(number, 128)
    DoLambdaFnTimeoutSecs                              = optional(number, 30)

    OperationQueueVisibilityTimeoutSecs  = optional(number, 90)
    QueueMessageBytesMax                 = optional(number, 32768)
    ErrorQueueMessageRetentionPeriodSecs = optional(number, 604800)
    ErrorQueueAdditionalPolicyStatements = optional(string, "")

    LogRetentionInDays = optional(number, 7)
    LogLevel           = optional(string, "ERROR")

    PlaceholderSuggestedStackName       = optional(string, "")
    PlaceholderSuggestedStackPolicyBody = optional(string, "")
    PlaceholderHelp                     = optional(string, "")
    PlaceholderAdvancedParameters       = optional(string, "")

    # Repeat defaults from cloudformation/lights_off_aws.yaml

    # For a StackSet, we must cover all parameters here or in
    # aws_cloudformation_stack_set.lifecycle.ignore_changes
  })

  description = "Lights Off CloudFormation StackSet parameter map. Keys, all optional, are parameter names from cloudformation/lights_off_aws.yaml ; parameters are described there. CloudFormation and Terraform data types match, except for Boolean parameters. Terraform converts bool values to CloudFormation String values automatically. For BackupRoleName in the StackSet module, include any role path prefix in Terraform, just as explained in the CloudFormation parameter description. Follow Terraform string escape rules for double quotation marks, etc. inside ErrorQueueAdditionalPolicyStatements ."

  default = {}
}

variable "lights_off_tags" {
  type        = map(string)
  description = "Tag map for CloudFormation StackSet and other AWS resources. Keys, all optional, are tag keys. Values are tag values. This takes precedence over the Terraform AWS provider's default_tags and over tags attributes defined by the module. To remove tags defined by the module, set the terraform and source tags to null . Warnings: Each AWS service may have different rules for tag key and tag value lengths, characters, and disallowed tag key or tag value contents. CloudFormation propagates StackSet tags to stack instances and to resources. CloudFormation requires StackSet tag values to be at least 1 character long; empty tag values are not allowed."

  default = {}

  validation {
    error_message = "CloudFormation requires StackSet tag values to be at least 1 character long; empty tag values are not allowed."

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




variable "lights_off_stackset_organizational_unit_names" {
  type        = list(string)
  description = "List of the names (not the IDs) of root-level organizational units in which to create instances of the CloudFormation StackSet. The organizational units must exist. Within a region, deployments proceed in alphabetical order by OU ID (not by name). Deprecated. Start with, or switch to, lights_off_stackset_organizational_unit_ids ."

  default = []
}

variable "lights_off_stackset_organizational_unit_ids" {
  type        = list(string)
  description = "List of the IDs of the organizational units in which to automatically create instances of the CloudFormation StackSet. Within a region, deployments proceed in alphabetical order by OU ID. Leave the list empty if you create all aws_cloudformation_stack_set_instance resources manually."

  default = []
}



variable "lights_off_stackset_regions" {
  type        = list(string)
  description = "List of region codes for the regions in which to create instances of the CloudFormation StackSet. The empty list causes the module to use lights_off_region . Initial deployment of automatically created StackSet instances will proceed in alphabetical order by region code."

  default = []
}

locals {
  region_concurrency_type_values = [
    "SEQUENTIAL",
    "PARALLEL"
  ]
  region_concurrency_type_values_string = join(
    " , ",
    local.region_concurrency_type_values
  )

  concurrency_mode_values = [
    "STRICT_FAILURE_TOLERANCE",
    "SOFT_FAILURE_TOLERANCE"
  ]
  concurrency_mode_values_string = join(
    " , ",
    local.concurrency_mode_values
  )
}

variable "lights_off_stackset_operation_preferences" {
  type = object({
    concurrency_mode             = optional(string, "STRICT_FAILURE_TOLERANCE")
    region_concurrency_type      = optional(string, "PARALLEL")
    region_order                 = optional(list(string))
    max_concurrent_percentage    = optional(number)
    max_concurrent_count         = optional(number, 2)
    failure_tolerance_percentage = optional(number)
    failure_tolerance_count      = optional(number, 2)
  })

  description = "operation_preferences for the Lights Off CloudFormation StackSet and any automatically-created StackSet instances. See registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudformation_stack_set#operation_preferences-argument-reference and registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudformation_stack_set_instance#operation_preferences-argument-reference . The default region_order is lights_off_stackset_regions in alphabetic order. _percentage takes precedence over the corresponding _count . An output is provided so that you can reference the final operation_preferences for any manually-created StackSet instances."

  default = {}

  validation {
    error_message = "if specified, must be one of: ${local.concurrency_mode_values_string} ."

    condition = contains(
      local.concurrency_mode_values,
      var.lights_off_stackset_operation_preferences["concurrency_mode"]
    )
  }

  validation {
    error_message = "if specified, must be one of: ${local.region_concurrency_type_values_string} ."

    condition = contains(
      local.region_concurrency_type_values,
      var.lights_off_stackset_operation_preferences["region_concurrency_type"]
    )
  }
}



variable "lights_off_region" {
  type        = string
  description = "Region code for the region from which to create the CloudFormation StackSet and in which to create supporting AWS resources such as an S3 bucket to hold the template. The empty string causes the module to use the default region configured for the Terraform AWS provider."

  default = ""
}
