# Lights Off!

Ever forget to turn the lights off? Now you can:

- Stop EC2 instances and RDS/Aurora databases overnight by tagging them with
  cron schedules, to cut AWS costs.

- Set, and see, AWS Backup times in resource tags, not central backup plans.

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
     \+ 20 minutes, rounded upward to :00, :10, :20, :30, :40, or :50.

3. Create a
   [CloudFormation stack](https://console.aws.amazon.com/cloudformation/home).
   Select Upload a template file, then select Choose file and navigate to a
   locally-saved copy of
   [lights_off_aws.yaml](/cloudformation/lights_off_aws.yaml?raw=true)
   . On the next page, set:

   - Stack name: `LightsOff`

4. After about 20 minutes, check whether the EC2 instance is stopped. Restart
   it and delete the `sched-stop` tag.

## Tag Keys (Operations)

||`sched-stop`|`sched-hibernate`|`sched-reboot`|`sched-backup`|
|:---|:---:|:---:|:---:|:---:|
||**`sched-start`**|**`sched-start`**|||
|EC2|||||
|[Instance](https://console.aws.amazon.com/ec2/v2/home#Instances)|&check;|&check;|&check;|Image (AMI)|
|[EBS Volume](https://console.aws.amazon.com/ec2/v2/home#Volumes)||||Snapshot|
|RDS/Aurora|||||
|[Database Instance](https://console.aws.amazon.com/rds/home#databases:)|&check;||&check;|Snapshot|
|[Database Cluster](https://console.aws.amazon.com/rds/home#databases:)|&check;||&check;|Snapshot|

All backups are handled by AWS Backup.

## Tag Values (Schedules)

### Single Terms

  |Type|Literal Values ([strftime](http://manpages.ubuntu.com/manpages/noble/man3/strftime.3.html#description))|Wildcard|
  |:---|:---:|:---:|
  |Day of month|`d=01` ... `d=31`|`d=_`|
  |Day of week ([ISO 8601](https://en.wikipedia.org/wiki/ISO_8601#Week_dates))|`u=1` (Monday) ... `u=7` (Sunday)||
  |Hour|`H=00` ... `H=23`|`H=_`|
  |Minute (multiple of 10)|`M=00` , `M=10` , `M=20` , `M=30` , `M=40` , `M=50`||

### Compound Terms

  |Type|Note|Literal Values|
  |:---|:---:|:---:|
  |Once a day|d=_ or d=_NN_ or u=_N_ first!|`H:M=00:00` ... `H:M=23:50`|
  |Once a week||`uTH:M=1T00:00` ... `uTH:M=7T23:50`|
  |Once a month||`dTH:M=01T00:00` ... `dTH:M=31T23:50`|

### Examples

  |Tag Value|Scenario|Meaning|
  |:---:|:---:|:---:|
  |`d=01 d=15 H=03 H=19 M=00`|cron|1st and 15th days of the month, at 03:00 and 19:00|
  |`d=_ H:M=03:00 H=_ M=15 M=45`|Extra daily operation|Every day, once a day at 03:00 _plus_ every hour at 15 and 45 minutes after the hour|
  |`uTH:M=2T03:00 uTH:M=5T19:00 d=_ H=11 M=15`|2 extra weekly operations|Tuesdays at 03:00, Fridays at 19:00, _plus_ every day at 11:15|
  |`dTH:M=01T03:00 u=3 H=19 M=15`|Extra monthly operation|1st day of the month at 03:00, _plus_ Wednesdays at 19:15|

### Rules

- [Universal Coordinated Time](https://www.timeanddate.com/worldclock/timezone/utc)
- 24-hour clock
- Days before times, hours before minutes
- The day, the hour and the minute must all be specified in some way
- Instead of the end of the month, specify the start, `dTH:M=01T00:00`
- Multiple operations on the same resource at the same time are _all_ canceled

Space was chosen as the separator and underscore, as the wildcard, because
[RDS does not allow commas or asterisks](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_Tagging.html#Overview.Tagging).

## Backups

### AWS Backup Configuration

Before you can use the `sched-backup` tag, a few steps may be necessary.

1. Backup vault

   AWS Backup creates the `Default` vault the first time you use the AWS
   Console to access the
   [list of vaults](https://console.aws.amazon.com/backup/home#/backupvaults)
   in a given AWS account and region. Otherwise, see
   [Backup vault creation](https://docs.aws.amazon.com/aws-backup/latest/devguide/create-a-vault.html),
   [AWS::Backup::BackupVault](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-backup-backupvault.html)
   , or
   [aws_backup_vault](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/backup_vault)
   .

   Update the `BackupVaultName` CloudFormation stack parameter if necessary.

2. Backup role

   AWS Backup creates `AWSBackupDefaultServiceRole` the first time you use the
   AWS Console to make a backup in a given AWS account. Otherwise, see
   [Default service role for AWS Backup](https://docs.aws.amazon.com/aws-backup/latest/devguide/iam-service-roles.html#default-service-roles).

   Update `BackupRoleName` in CloudFormation if necessary.

3. Backup vault policy

   If you've added `"Deny"` statements, be sure that `FindLambdaFnRole` still
   has access.

4. KMS key policies

   No action is necessary if your EBS volumes and RDS/Aurora databases are
   unencrypted, or if they are encrypted with the default `aws/ebs` and
   `aws/rds` keys and you are using `AWSBackupDefaultServiceRole` .

   For custom keys, you must (a) modify the key policies _or_ (b) attach
   custom policies to a custom backup role. If your keys are in a different
   AWS account than your disks and databases, you must do (a) _and_ (b).
   See
   [Encryption for backups in AWS Backup](https://docs.aws.amazon.com/aws-backup/latest/devguide/encryption.html),
   [How EBS uses AWS KMS](https://docs.aws.amazon.com/kms/latest/developerguide/services-ebs.html),
   and
   [Overview of encrypting Amazon RDS resources](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Overview.Encryption.html#Overview.Encryption.Overview).

If Lights Off can't submit a backup job (the "Do" function [log](#logging)
shows that `start_backup_job` failed with a `403` error), or if AWS Backup
can't start a successfully submitted job, a permission problem is likely.
Check with your AWS administrator in case service and resource control
policies (SCPs and RCPs), permission boundaries, or session policies apply.

### Accessing Backups

- Use AWS Backup to list and delete backups.
- Use EC2 and RDS to view the underlying images and snapshots.
- Use AWS Backup, or EC2 and RDS, to restore (create new resources from)
  backups.

### Backup Tags

AWS Backup copies resource tags to backups. Lights Off adds `sched-time` to
indicate when the backup was _scheduled_ to occur, in
[ISO 8601](https://en.wikipedia.org/wiki/ISO_8601#Combined_date_and_time_representations)
form (example: `2024-12-31T14:00Z`).

## On/Off Switch

- You can toggle the `Enable` parameter of your Lights Off CloudFormation
  stack.
- While Enable is `false`, scheduled operations do not happen; they are
  skipped permanently.

## Logging

- Check the
  [LightsOff CloudWatch log groups](https://console.aws.amazon.com/cloudwatch/home#logsV2:log-groups$3FlogGroupNameFilter$3DLightsOff-).
- Log entries are JSON objects. Entries from Lights Off include `"type"` and
  `"value"` keys.
- For more or less data, change the `LogLevel` in CloudFormation.

## Advanced Installation

### Multi-Account, Multi-Region (CloudFormation StackSet)

To deploy Lights Off to multiple AWS accounts and/or multiple regions,

1. Delete any standalone Lights Off CloudFormation stacks in the target AWS
   accounts and regions.

2. Complete the prerequisites for creating a StackSet with
   [service-managed permissions](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-orgs-enable-trusted-access.html).

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

### Least-Privilege

<details>
  <summary>View least-privilege installation details</summary>

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

For a multi-account CloudFormation StackSet deployment, you can use
[self-managed permissions](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-prereqs-self-managed.html)
by creating a customer-managed IAM policy covering the inline policies from
`DeploymentRole` in
[lights_off_aws_prereq.yaml](/cloudformation/lights_off_aws_prereq.yaml) ,
attaching your policy to `AWSCloudFormationStackSetExecutionRole` , and
propagating the policy and the role policy attachment to all target AWS
accounts.
</details>

## Security

_In accordance with the software license, nothing in this section creates a
warranty, an indemnification, an assumption of liability, etc. Use this
software at your own risk. You are encouraged to evaluate the source code._

<details>
  <summary>View security details</summary>

### Security Design Goals

- Least-privilege roles for the AWS Lambda functions that find resources and
  do scheduled operations. The "Do" function is authorized to perform a small
  set of operations, and at that, only when a resource has the correct tag
  key. (AWS Backup creates backups, using a role that you can configure.)

- A least-privilege queue policy. The operation queue can only consume
  messages from the "Find" function and produce messages for the "Do" function
  (or a dead-letter queue, if an operation fails). Encryption in transit is
  required.

- Readable IAM policies, formatted as CloudFormation YAML rather than JSON,
  and broken down into discrete statements by service, resource or principal.

- Optional encryption at rest with the AWS Key Management System (KMS), for
  queue message bodies (which contain resource identifiers) and for logs (may
  contain resource metadata).

- No data storage other than in queues and logs, with short or configurable
  retention periods.

- Tolerance for clock drift in a distributed system. The "Find" function
  starts 1 minute into the 10-minute cycle and operation queue entries expire
  9 minutes in.

- An optional CloudFormation service role for least-privilege deployment.

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
  to `"Deny"` in the remaining statements, and use this inverted policy as a
  permission boundary.

- Add policies to prevent people from directly invoking the AWS Lambda
  functions and from passing their roles to other functions.

- Log infrastructure changes using AWS CloudTrail, and set up alerts.

- Automatically copy backups to an AWS Backup vault in an isolated account.

- Separate production workloads. You might choose not to deploy Lights Off to
  AWS accounts used for production, or you might add a custom policy to the
  "Do" function's role, denying authority to reboot and stop production
  resources ( `AttachLocalPolicy` in CloudFormation).

</details>

## Bonus: Delete and Recreate Expensive Resources on a Schedule

<details>
  <summary>View scheduled stack update details</summary>

Lights Off can delete and recreate all kinds of expensive AWS infrastructure
in your own CloudFormation stacks, based on cron schedules in stack tags.

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
  restored?
  [AWS Backup restore testing](https://docs.aws.amazon.com/aws-backup/latest/devguide/restore-testing.html)
  can help.

- Be aware: of charges for AWS Lambda functions, SQS queues, CloudWatch Logs,
  KMS, backup storage, and early deletion of cold storage backups; of the
  minimum billable period when you stop an EC2 instance or RDS database with
  a commercial license; of ongoing storage charges for stopped EC2 instances
  and RDS databases; and of the resumption of charges when RDS restarts a
  stopped database after the 7-day limit. Other charges may apply!

- Test the AWS Lambda functions, SQS queues, and IAM policies in your own AWS
  environment. To help improve Lights Off, please submit
  [bug reports and feature requests](https://github.com/sqlxpert/lights-off-aws/issues),
  as well as [proposed changes](https://github.com/sqlxpert/lights-off-aws/pulls).

## Progress

Paul wrote TagSchedOps, the first version of this project, before Systems
Manager, Data Lifecycle Manager or AWS Backup existed. The project remains a
simple alternative to
[Systems Manager Automation runbooks for
stopping EC2 instances](https://docs.aws.amazon.com/systems-manager-automation-runbooks/latest/userguide/automation-aws-stopec2instance.html),
etc. It is now integrated with AWS Backup, leveraging the security and
management benefits (including backup retention lifecycle policies) but
offering a simple alternative to
[backup plans](https://docs.aws.amazon.com/aws-backup/latest/devguide/about-backup-plans.html).
Despite new features, the code has gotten shorter.

|Year|AWS Lambda Python Lines|Core CloudFormation YAML Lines|
|:---:|:---:|:---:|
|2017| &asymp; 775|&asymp; 2,140|
|2022|630|800 &check;|
|2025|525 &check;|820|

## Dedication

This project is dedicated to ej, Marianne and R&eacute;gis, and also to the
wonderful colleagues I've worked with over the years. Thank you to Corey for
sharing the original version with the AWS user community, and to Lee for
suggesting the new name.

## Licenses

|Scope|Link|Included Copy|
|:---:|:---:|:---:|
|Source code files, and source code embedded in documentation files|[GNU General Public License (GPL) 3.0](http://www.gnu.org/licenses/gpl-3.0.html)|[LICENSE-CODE.md](/LICENSE-CODE.md)|
|Documentation files (including this readme file)|[GNU Free Documentation License (FDL) 1.3](http://www.gnu.org/licenses/fdl-1.3.html)|[LICENSE-DOC.md](/LICENSE-DOC.md)|

Copyright Paul Marcelin

Contact: `marcelin` at `cmu.edu` (replace "at" with `@`)
