# Start, stop and back up AWS resources tagged with cron schedules
# github.com/sqlxpert/lights-off-aws/  GPLv3  Copyright Paul Marcelin

output "lights_off_stackset_name" {
  type        = string
  description = "Name of the Lights Off StackSet, derived from the lights_off_stackset_name_suffix variable. If you create StackSet instances manually, set aws_cloudformation_stack_set_instance.stack_set_name to this value."

  value = aws_cloudformation_stack_set.lights_off.name
}

output "lights_off_stackset_regions" {
  type        = set(string)
  description = "Final set of StackSet instance regions, derived from the lights_off_stackset_regions variable. If you create StackSet instances manually, set stack_set_instance_region for each instance to an element of this set."

  value = local.regions_set
}

output "lights_off_stackset_operation_preferences" {
  type = object({
    concurrency_mode             = string
    region_concurrency_type      = string
    region_order                 = list(string)
    max_concurrent_percentage    = optional(number)
    max_concurrent_count         = optional(number)
    failure_tolerance_percentage = optional(number)
    failure_tolerance_count      = optional(number)
  })
  description = "Final operation_preferences for the Lights Off CloudFormation StackSet and any automatically-created StackSet instances. If you create StackSet instances manually, set operation_preferences attributes by referencing this map."

  value = local.lights_off_stackset_operation_preferences
}
