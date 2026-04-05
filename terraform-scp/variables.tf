# Start, stop and back up AWS resources tagged with cron schedules
# github.com/sqlxpert/lights-off-aws/  GPLv3  Copyright Paul Marcelin

variable "scp_name_suffix" {
  type        = string
  description = "Service control policy name suffix, for blue/green deployments or other scenarios in which you install multiple instances of this module. If you have also installed the CloudFormation template equivalent to this Terraform module, this suffix must differ from the stack name(s)."

  default = "LightsOffScp"
}

variable "enable_scp" {
  type        = bool
  description = "Whether to apply the service control policy to its designated targets. Change this to false to detach the SCP but preserve the list of its targets."

  default = true
}

variable "scp_target_ids" {
  type        = list(string)
  description = "Up to 100 r- root ID strings, ou- organizational unit ID strings, and/or AWS account ID numbers to which the SCP will apply. To view the SCP before applying it, leave this empty, or start with enable_scp set to false . Exercise caution when applying this SCP, because it generally does reduce existing permissions."

  default = []
}

variable "scp_principal_condition" {
  type        = string
  description = "One or more condition expressions determining which roles (or other IAM principals) are not allowed to add, change, or remove Light Off schedule tags, in AWS accounts subject to the SCP. Separate multiple expressions with commas. Follow Terraform string escape rules for double quotation marks (prefix with a backslash) and any IAM policy variables (double the dollar sign). The default means that a tagging request will be denied if it is not made by the manage-lights-off role. (Separately, you would have to create the manage-lights-off role and attach an IAM policy allowing the role to read, add, change, and remove tags.) \"ForAnyValue:StringEquals\" is forbidden; to use this condition operator, write a custom policy. For condition operators, see https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_condition_operators.html . For condition keys, see https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_condition-keys.html#condition-keys-principal-properties"

  default = "\"ArnNotLike\": { \"aws:PrincipalArn\": \"arn:aws:iam::*:role/manage-lights-off\" }"

  validation {
    error_message = "\"ForAnyValue:StringEquals\" is forbidden. To use this condition operator, write a custom policy."

    condition = length(regexall(
      "\"ForAnyValue:StringEquals\"",
      var.scp_principal_condition
    )) == 0
  }

  validation {
    error_message = "scp_principal_condition must not be blank."

    condition = (length(var.scp_principal_condition) >= 1)
  }
}

variable "scp_tags" {
  type        = map(string)
  description = "Tag map for the SCP. Keys, all optional, are tag keys. Values are tag values. This takes precedence over the Terraform AWS provider's default_tags and over tags attributes defined by the module. To remove tags defined by the module, set the terraform , name_suffix , source and rights tags to null ."

  default = {}
}
