# Start, stop and back up AWS resources tagged with cron schedules
# github.com/sqlxpert/lights-off-aws/  GPLv3  Copyright Paul Marcelin

output "scp_protect_lights_off_tags_arn" {
  value       = aws_organizations_policy.scp_protect_lights_off_tags.arn
  description = "ARN of service control policy policy protecting Lights Off schedule tags"
}
output "scp_protect_lights_off_tags_id" {
  value       = aws_organizations_policy.scp_protect_lights_off_tags.id
  description = "Physical identifier of service control policy"
}
