# Start, stop and back up AWS resources tagged with cron schedules
# github.com/sqlxpert/lights-off-aws/  GPLv3  Copyright Paul Marcelin

output "lights_off_stackset_name" {
  type        = string
  description = "Name of the Lights Off StackSet, derived from the lights_off_stackset_name_suffix variable. If you create StackSet instances manually, set aws_cloudformation_stack_set_instance.stack_set_name to this value."

  value = aws_cloudformation_stack_set.lights_off.name
}

output "lights_off_stackset_operation_preferences" {
  type = object({
    concurrency_mode             = optional(string)
    region_concurrency_type      = string
    region_order                 = list(string)
    max_concurrent_percentage    = optional(number)
    max_concurrent_count         = optional(number)
    failure_tolerance_percentage = optional(number)
    failure_tolerance_count      = optional(number)
  })
  description = "Final operation_preferences for the Lights Off CloudFormation StackSet (except that concurrency_mode does not apply at this level and is ignored) and any automatically-defined StackSet instances. If you create StackSet instances manually, set each attribute of the aws_cloudformation_stack_set_instance.operation_preferences block according to this map, and set aws_cloudformation_stack_set_instance.stack_set_instance_region to an element of the region_order list. Additional type constraint: corresponding _percentage and _count keys will never both be present."

  value = local.operation_preferences
}
