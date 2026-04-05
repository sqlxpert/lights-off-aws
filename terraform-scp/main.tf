# Start, stop and back up AWS resources tagged with cron schedules
# github.com/sqlxpert/lights-off-aws/  GPLv3  Copyright Paul Marcelin

resource "aws_organizations_policy" "scp_protect_lights_off_tags" {
  type        = "SERVICE_CONTROL_POLICY"
  name        = "Ec2RdsCFnProtectTags-${var.scp_name_suffix}"
  description = "EC2 instance, EBS volume, RDS/Aurora database instance/cluster, and CloudFormation stack/StackSet tags: Matching IAM principals cannot add, change, or remove 'sched-' tags used by Lights Off. GPLv3, Copyright Paul Marcelin. github.com/sqlxpert"
  tags        = local.scp_tags

  # I prefer data.aws_iam_policy_document , but a HEREDOC allows source parity
  # with CloudFormation (except for variables) and permits insertion of values
  # that the user specifies in JSON (native for the IAM policy language):
  content = <<-END_POLICY
    {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Effect": "Deny",
          "Action": [
            "ec2:CreateTags",
            "ec2:DeleteTags"
          ],
          "Resource": [
            "${provider::aws::arn_build(local.partition, "ec2", "*", "*", "instance/*")}"
          ],
          "Condition": {
            "ForAnyValue:StringEquals": {
              "aws:TagKeys": [
                "sched-start",
                "sched-stop",
                "sched-hibernate"
              ]
            },
            ${var.scp_principal_condition}
          }
        },
        {
          "Effect": "Deny",
          "Action": [
            "ec2:CreateTags",
            "ec2:DeleteTags"
          ],
          "Resource": [
            "${provider::aws::arn_build(local.partition, "ec2", "*", "*", "volume/*")}",
            "${provider::aws::arn_build(local.partition, "ec2", "*", "*", "instance/*")}"
          ],
          "Condition": {
            "ForAnyValue:StringEquals": {
              "aws:TagKeys": [
                "sched-backup"
              ]
            },
            ${var.scp_principal_condition}
          }
        },
        {
          "Effect": "Deny",
          "Action": [
            "rds:AddTagsToResource",
            "rds:RemoveTagsFromResource"
          ],
          "Resource": [
            "${provider::aws::arn_build(local.partition, "rds", "*", "*", "db:*")}",
            "${provider::aws::arn_build(local.partition, "rds", "*", "*", "cluster:*")}"
          ],
          "Condition": {
            "ForAnyValue:StringEquals": {
              "aws:TagKeys": [
                "sched-start",
                "sched-stop",
                "sched-backup"
              ]
            },
            ${var.scp_principal_condition}
          }
        },
        {
          "Effect": "Deny",
          "Action": [
            "cloudformation:TagResource",
            "cloudformation:UntagResource"
          ],
          "Resource": [
            "${provider::aws::arn_build(local.partition, "cloudformation", "*", "*", "stack/*")}",
            "${provider::aws::arn_build(local.partition, "cloudformation", "*", "*", "stackset/*")}"
          ],
          "Condition": {
            "ForAnyValue:StringEquals": {
              "aws:TagKeys": [
                "sched-set-Enable-true",
                "sched-set-Enable-false"
              ]
            },
            ${var.scp_principal_condition}
          }
        }
      ]
    }
  END_POLICY
}

resource "aws_organizations_policy_attachment" "scp_protect_lights_off_tags" {
  for_each = toset(var.enable_scp ? var.scp_target_ids : [])

  policy_id = aws_organizations_policy.scp_protect_lights_off_tags.id
  target_id = each.key
}
