# Lights Off!

Ever forget to turn the lights off? Now you can:

- Stop, restart and back up EC2 instances and RDS/Aurora databases with
  cron-style schedules in their tags.

- Set and view AWS Backup schedules in resource tags, not central backup
  plans.

- Easily deploy this solution across multiple AWS accounts and regions.

Jump to:
[Quick Start](#quick-start)
&bull;
[Tags](#tag-keys-operations)
&bull;
[Schedules](#tag-values-schedules)
&bull;
[Multi-Account, Multi-Region](#multi-account-multi-region-cloudformation-stackset)
&bull;
[Security](#security)

## Quick Start

1. Log in to the AWS Console as an administrator.

2. Tag a running, non-essential
   [EC2 instance](https://console.aws.amazon.com/ec2/v2/home#Instances)
   with:

   - `sched-stop` : `d=_ H:M=11:30` , replacing 11:30 with the
     [current UTC time](https://www.timeanddate.com/worldclock/timezone/utc)
     \+ 20 minutes, rounded **up** to `:00` , `:10` , `:20` , `:30` , `:40` ,
     or `:50` .

3. Create a
   [CloudFormation stack](https://console.aws.amazon.com/cloudformation/home).
   Select Upload a template file, then select Choose file and navigate to a
   locally-saved copy of
   [lights_off_aws.yaml](/cloudformation/lights_off_aws.yaml?raw=true)
   . On the next page, set:

   - Stack name: `LightsOff`

4. After about 20 minutes, check whether the EC2 instance is in the stopped
   state. Restart it and delete the `sched-stop` tag.

## Tag Keys (Operations)

||`sched-stop`|`sched-hibernate`|`sched-reboot`|`sched-reboot-failover`|`sched-backup`|
|:---|:---:|:---:|:---:|:---:|:---:|
||**`sched-start`**|**`sched-start`**||||
|EC2||||||
|[Instance](https://console.aws.amazon.com/ec2/v2/home#Instances)|&check;|&check;|&check;||Image (AMI)|
|[EBS Volume](https://console.aws.amazon.com/ec2/v2/home#Volumes)|||||Volume Snapshot|
|RDS/Aurora||||||
|[Database Instance](https://console.aws.amazon.com/rds/home#databases:)|&check;||&check;|&check;|Database Snapshot|
|[Database Cluster](https://console.aws.amazon.com/rds/home#databases:)|&check;||&check;||Cluster Snapshot|

All backups, regardless of underlying type, are managed in [AWS Backup](https://console.aws.amazon.com/backup/home#/backupvaults).

## Tag Values (Schedules)

### Simple Terms

  |Type|Wildcard|Literals ([strftime](http://manpages.ubuntu.com/manpages/noble/man3/strftime.3.html#description))|
  |:---|:---:|:---:|
  |Day of month|`d=_`|`d=01` ... `d=31`|
  |Day of week ([ISO 8601](https://en.wikipedia.org/wiki/ISO_8601#Week_dates))||`u=1` (Monday) ... `u=7` (Sunday)|
  |Hour|`H=_`|`H=00` ... `H=23`|
  |Minute (multiple of 10)||`M=00` , `M=10` , `M=20` , `M=30` , `M=40` , `M=50`|

### Compound Terms

  |Type|Note|Literals|
  |:---|:---:|:---:|
  |Once a day|`d=` or `u=` first!|`H:M=00:00` ... `H:M=23:50`|
  |Once a week||`uTH:M=1T00:00` ... `uTH:M=7T23:50`|
  |Once a month||`dTH:M=01T00:00` ... `dTH:M=31T23:50`|

### Examples

  |Tag Value|Scenario|Meaning|
  |:---:|:---:|:---:|
  |`d=01 d=15 H=03 H=19 M=00`|cron|03:00 and 19:00 the 1st and 15th days of the month|
  |`d=_ H:M=08:50 H=_ M=10 M=40`|Extra daily operation|10 and 40 minutes after the hour, every hour, _plus_ 08:50 every day|
  |`uTH:M=2T03:30 uTH:M=5T07:20 d=_ H=11 M=00`|2 extra weekly operations|11:00 every day, _plus_  03:30 every Tuesday and 07:20 every Friday|
  |`dTH:M=01T05:20 u=3 H=22 M=10`|Extra monthly operation|22:10 every Wednesday, _plus_ 05:20 the 1st day of the month|

### Rules

- [Universal Coordinated Time](https://www.timeanddate.com/worldclock/timezone/utc)
- 24-hour clock
- Days before times, hours before minutes
- The day, the hour and the minute must all be specified in some way
- Instead of end-of-month, use start-of-month ( `dTH:M=01T00:00` )
- Scheduling multiple operations on the same resource at the same time
  produces an error

Space was chosen as the separator and underscore, as the wildcard, because
[RDS does not allow commas or asterisks](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_Tagging.html#Overview.Tagging).

## Backups

### Services

- Use AWS Backup to list and delete backups.
- Use EC2 and RDS to view the underlying images and snapshots.
- Use AWS Backup, or EC2 and RDS, to restore (create new resources from)
  backups.

### Tags

AWS Backup copies resource tags to backups on a best effort basis. For
convenience, Lights Off adds an
[ISO 8601](https://en.wikipedia.org/wiki/ISO_8601#Combined_date_and_time_representations)
`sched-time` tag (example: `2024-12-31T14:00Z`) to indicate when the backup
was _scheduled_ to occur.

## On/Off Switch

- You can toggle the `Enable` parameter of your Lights Off CloudFormation
  stack.
- While Enable is `false`, scheduled operations do not happen; they are
  skipped permanently.

## Logging

- Check the
  [LightsOff CloudWatch log groups](https://console.aws.amazon.com/cloudwatch/home#logsV2:log-groups$3FlogGroupNameFilter$3DLightsOff-).
- Log entries are JSON objects. For application log entries, reference the
  `type` key for a consistent classification and the `value` key for the data.
  System log entries use other keys.
- For more or fewer log entries, change the `LogLevel` parameter in
  CloudFormation.

## Advanced Installation

### Least-Privilege

You can use a
[CloudFormation service role](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-iam-servicerole.html)
to delegate only the privileges needed to create the Lights Off stack. First,
create the `LightsOffPrereq` stack from
[lights_off_aws_prereq.yaml](/cloudformation/lights_off_aws_prereq.yaml?raw=true)
. Next, when you create the `LightsOff` stack from
[lights_off_aws.yaml](/cloudformation/lights_off_aws.yaml?raw=true) ,
scroll to the Permissions section and set IAM role - optional to
`LightsOffPrereq-DeploymentRole` . If your own privileges are limited, you
might need permission to pass the deployment role to CloudFormation. See the
`LightsOffPrereq-SampleDeploymentRolePassRolePol` IAM policy for an example.

### Multi-Account, Multi-Region (CloudFormation StackSet)

<details>
  <summary>View multi-account, multi-region details</summary>

To deploy Lights Off to multiple AWS accounts and/or multiple regions,

1. Delete any standalone Lights Off CloudFormation stacks in the target AWS
   accounts and regions.

2. Complete the prerequisites for creating a StackSet with
   [service-managed permissions](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-orgs-enable-trusted-access.html).

   - Not recommended: In a strict least-privilege environment, you can deploy
     a StackSet with
     [self-managed permissions](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-prereqs-self-managed.html)
     by creating a customer-managed IAM policy covering the inline policies
     from `DeploymentRole` in
     [lights_off_aws_prereq.yaml](/cloudformation/lights_off_aws_prereq.yaml)
     , attaching your policy to `AWSCloudFormationStackSetExecutionRole`, and
     propagating the policy and the role policy attachment to all target AWS
     accounts.

3. In the management AWS account (or a delegated administrator account),
   create a
   [CloudFormation StackSet](https://console.aws.amazon.com/cloudformation/home#/stacksets).
   Select Upload a template file, then select Choose file and upload a
   locally-saved copy of
   [lights_off_aws.yaml](/cloudformation/lights_off_aws.yaml?raw=true) . On
   the next page, set:

   - StackSet name: `LightsOff`

4. Two pages later, under Deployment targets, select Deploy to Organizational
   Units (OUs). Enter the AWS OU ID of the target Organizational Unit. Lights
   Off will be deployed to all AWS accounts within this Organizational Unit.
   Toward the bottom of the page, specify the target regions.

</details>

## Security

_In accordance with the software license, nothing in this section creates a
warranty, an indemnification, an assumption of liability, etc. Use this
software entirely at your own risk. You are encouraged to evaluate the code,
which is open-source._

<details>
  <summary>View security details</summary>

### Security Design Goals

- Least-privilege roles for the AWS Lambda functions that find resources and
  do scheduled operations. The "Do" function is authorized to perform a small
  set of operations, and at that, only when a resource has the correct tag key
  (The AWS Backup service creates backups, using a role that you can specify.)

- A least-privilege queue policy. The operation queue can only consume
  messages from the "Find" function and produce messages for the "Do" function
  (or a dead-letter queue, if an operation fails). Encryption in transit is
  required.

- Readable IAM policies, formatted as CloudFormation YAML rather than as JSON
  and broken down into discrete statements by service, resource or principal.

- Optional encryption at rest with custom AWS Key Management System (KMS)
  keys, for queue message bodies (which contain resource identifiers) and for
  log entries (which may contain resource metadata).

- No data storage other than in queues and logs. Retention periods for the
  dead letter queue and the logs are configurable. The fixed retention period
  for the operation queue is short.

- Tolerance for clock drift in a distributed system. The "Find" function
  starts 1 minute into the 10-minute cycle and operation queue entries expire
  9 minutes in.

- An optional, least-privilege CloudFormation service role for deployment.

### Security Steps You Can Take

- Only allow trusted people and services to tag AWS resources. You can
  deny the right to add, change and delete `sched-` tags by including the
  [aws:TagKeys condition key](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_tags.html#access_tags_control-tag-keys)
  in a permission boundary.

- Never authorize a role that can create backups (or, in this case, set tags
  to schedule backups) delete backups as well.

- Prevent people from modifying components, most of which can be identified by
  `LightsOff` in ARNs and in the automatic `aws:cloudformation:stack-name`
  tag. Limiting permissions so that the deployment role is _necessary_ for
  stack modifications is ideal. Short of that, you could copy the deployment
  role policies, delete statements with `"Resource": "*"` , change `"Effect"`
  to `"Deny"` in the remaining statements, and make this inverted version into
  a permission boundary.

- Add policies to prevent people from directly invoking the AWS Lambda
  functions and from passing their roles to other functions.

- Log infrastructure changes using AWS CloudTrail, and set up alerts.

- Automatically copy backups to an AWS Backup vault in an isolated account.

- Separate production workloads. You might choose not to deploy Lights Off to
  AWS accounts used for production, or you might customize the "Do" function's
  role, removing the authority to reboot and stop production resources (
  `AttachLocalPolicy` ).

</details>

## Bonus: Delete and Recreate Expensive Resources on a Schedule

<details>
  <summary>View scheduled stack update setup details</summary>

As a bonus, Lights Off can delete and recreate all kinds of expensive AWS
infrastructure in your own CloudFormation stacks, based on cron-style
schedules in stack tags.

Deleting AWS Client VPN resources overnight, while developers are asleep, is
a sample use case. See
[10-minute AWS Client VPN](https://github.com/sqlxpert/10-minute-aws-client-vpn#automatic-scheduling)
for potential savings of $600 per year.

To make your own CloudFormation template compatible, see
[lights_off_aws_bonus_cloudformation_example.yaml](/cloudformation/lights_off_aws_bonus_cloudformation_example.yaml)
. CloudFormation "transforms" are not currently supported.

Not every resource needs to be deleted and recreated; condition the creation
of _expensive_ resources on the `Enable` parameter. In the AWS Client VPN
stack, the server and client certificates, endpoints and network security
groups are never deleted, because they don't cost anything. The expensive VPN
attachments can be deleted and recreated with no need to reconfigure clients.

Set the `sched-set-Enable-true` and `sched-set-Enable-false` tags on
your own CloudFormation stack. At the scheduled times, Lights Off will perform
a stack update, toggling the value of the `Enable` parameter to `true` or
`false` while leaving other parameters, and template itself, unchanged.
(Capitalize **E**nable in the tag keys, just as in the parameter name.)
</details>

## Extensibility

<details>
  <summary>View extensibility details</summary>

Lights Off takes advantage of patterns in boto3, the AWS software development
kit (SDK) for Python, and in the underlying AWS API. Adding more AWS services,
resource types, and operations is easy. For example, supporting RDS _database
clusters_ (individual _database instances_ were always supported) required
adding:

```python
    AWSRsrcType(
      "rds",
      ("DB", "Cluster"),
      {
        ("start", ): {},
        ("stop", ): {},
        ("reboot", ): {},
        ("backup", ): {"class": AWSOpBackUp},
      },
      rsrc_id_key_suffix="Identifier",
      tags_key="TagList",
    )
```

Most method names can be derived mechanically if you use the verb from the
method name in the tag key and divide the resource type name into words. Given
the tag key `sched-start` and the words `DB` and `Cluster` , the method name
`start_db_cluster` follows.

Optionally, you can add a dictionary of static keyword arguments. You can also
sub-class the `AWSOp` class if a method requires complex arguments.

The `start_backup_job` method takes an Amazon Resource Name (ARN), whose
format is consistent for all resource types. As long as AWS Backup supports
the resource type you're interested in, there is no extra work to do.

Adding statements like the one below to the Identity and Access Management
(IAM) policy for the role used by the "Do" AWS Lambda function authorizes
operations on a new resource type. You must also authorize the role used by
the "Find" function to describe (list) resources of the new type.

```yaml
          - Effect: Allow
            Action: rds:StartDBCluster
            Resource: !Sub "arn:${AWS::Partition}:rds:${AWS::Region}:${AWS::AccountId}:cluster:*"
            Condition:
              StringLike: { "aws:ResourceTag/sched-start": "*" }
```

What AWS resources and operations would _you_ like to add?
</details>

## Advice

- Test your backups often! Are they finishing on-schedule? Can they be
  restored? The
  [AWS Backup restore testing feature](https://docs.aws.amazon.com/aws-backup/latest/devguide/restore-testing.html)
  can help.

- Be aware: of charges for AWS Lambda functions, SQS queues, CloudWatch Logs,
  KMS, backup storage, and early deletion of cold storage backups; of the
  minimum billing period when you stop an RDS database or an EC2 instance with
  a commercial license; of ongoing storage charges for stopped EC2 instances
  and RDS databases; and of resumption of charges when RDS restarts a stopped
  database after the 7-day limit. Other charges may apply!

- Test the AWS Lambda functions, SQS queues, and IAM policies in your own AWS
  environment. To help improve Lights Off, please submit
  [bug reports and feature requests](https://github.com/sqlxpert/lights-off-aws/issues),
  as well as [proposed changes](https://github.com/sqlxpert/lights-off-aws/pulls).

## Progress

This project was originally called TagSchedOps. Paul wrote the first version
in 2017, before Systems Manager, Data Lifecycle Manager or AWS Backup existed.
It remains a simple alternative to
[Systems Manager Automation runbooks for
stopping](https://docs.aws.amazon.com/systems-manager-automation-runbooks/latest/userguide/automation-aws-stopec2instance.html)
and starting EC2 instances and RDS databases. It is now integrated
with AWS Backup, leveraging the security and management benefits (including
backup retention lifecycle policies) but offering a simple alternative to
[backup plans](https://docs.aws.amazon.com/aws-backup/latest/devguide/about-backup-plans.html).
Despite adding features, I have cut many lines of code.

|Year|AWS Lambda Python Lines|Core CloudFormation YAML Lines|
|:---:|:---:|:---:|
|2017| &asymp; 775|&asymp; 2,140|
|2018|750|No change|
|2022|630|800 &check;|
|2025|520 &check;|815|

## Dedication

This work is dedicated to ej, Marianne and R&eacute;gis, and also to the
wonderful colleagues I've worked with over the years. Thank you to Lee for
suggesting the name and to Corey for sharing the original version with the AWS
user community.

## Licenses

|Scope|Link|Included Copy|
|:---:|:---:|:---:|
|Source code files, and source code embedded in documentation files|[GNU General Public License (GPL) 3.0](http://www.gnu.org/licenses/gpl-3.0.html)|[LICENSE-CODE.md](/LICENSE-CODE.md)|
|Documentation files (including this readme file)|[GNU Free Documentation License (FDL) 1.3](http://www.gnu.org/licenses/fdl-1.3.html)|[LICENSE-DOC.md](/LICENSE-DOC.md)|

Copyright Paul Marcelin

Contact: `marcelin` at `cmu.edu` (replace "at" with `@`)
