# Lights Off!

Ever forget to turn the lights off? Now you can:

- Stop EC2 instances and RDS/Aurora databases temporarily by tagging them with
  cron schedules, to cut AWS costs. Schedules (not references to schedules) go
  directly in the tags.

- Trigger AWS Backup with cron schedules in resource tags.

- Delete expensive infrastructure temporarily by tagging your own
  CloudFormation stacks with cron schedules.

- Easily deploy this tool to multiple AWS accounts and regions.

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

---

>&#128274; Software supply chain security is on everyone's mind. This tool's
two Lambda functions share one Python source file that's short enough to read
(750&nbsp;lines total). I made GitHub releases immutable as of `v3.6.0`
(2026-04-06). AWS
[manages patching](https://docs.aws.amazon.com/lambda/latest/dg/runtime-management-shared.html#:~:text=Lambda%20is%20responsible%20for%20applying,Auto%20runtime%20update%20mode.)
of the stock Lambda runtime, which provides the Python standard library and the
AWS software development kit (boto, boto3).
>
>AWS's
[Instance Scheduler](https://github.com/aws-solutions/instance-scheduler-on-aws),
the closest competing tool, has well over 10,000&nbsp;lines of Python spread
across more than 100&nbsp;files. As of 2026-04-05, the latest release was still
mutable:
[v3.2.1 (2026-03-27)](https://github.com/aws-solutions/instance-scheduler-on-aws/releases/tag/v3.2.1).
Instance Scheduler depends on numerous
[Python modules](https://github.com/aws-solutions/instance-scheduler-on-aws/blob/e547564/source/app/.projen/deps.json)
and
[npm packages](https://github.com/aws-solutions/instance-scheduler-on-aws/blob/e547564/package.json).
It helps itself to permission to
[modify and stop any EC2 instance](https://github.com/aws-solutions/instance-scheduler-on-aws/blob/f6611ff/source/instance-scheduler/lib/iam/ec2-scheduling-permissions-policy.ts#L23-L29)
and
[delete any RDS snapshot](https://github.com/aws-solutions/instance-scheduler-on-aws/blob/f6611ff/source/instance-scheduler/lib/iam/rds-scheduling-permissions-policy.ts#L21-L28).
It also
[sends data to AWS](https://github.com/aws-solutions/instance-scheduler-on-aws/blob/ad5a47b/README.md#collection-of-operational-metrics).
Instance Scheduler is powerful, and I have tremendous respect for its authors,
but you'd need your own expert to run it securely.

Click to view the Lights Off architecture diagram:

[<img src="/media/lights-off-aws-architecture-and-flow-thumb.png" alt="An Event Bridge Scheduler rule triggers the 'Find' Amazon Web Services Lambda function every 10 minutes. The function calls 'describe' methods, checks the resource records returned for tag keys such as 'sched-start', and uses regular expressions to check the tag values for day, hour, and minute terms. Current day and time elements are inserted into the regular expressions using 'strftime'. If there is a match, the function sends a message to a Simple Queue Service queue. The 'Do' function, triggered in response, checks whether the message has expired. If not, this function calls the method indicated by the message attributes, passing the message body for the parameters. If the request is successful or a known exception occurs and it is not okay to re-try, the function is done. If an unknown exception occurs, the message remains in the operation queue, becoming visibile again after 90 seconds. After 3 tries, a message goes from the operation queue to the error (dead letter) queue." height="144" />](/media/lights-off-aws-architecture-and-flow.png?raw=true "Architecture diagram and flowchart for Lights Off, AWS!")

Lights Off addresses Cloud Efficiency Hub report
[CER-0096: Missing Scheduled Shutdown for Non-Production EC2 Instances](https://hub.pointfive.co/inefficiencies/missing-scheduled-shutdown-for-non-production-ec2-instances),
and more!

## Quick Start

 1. Log in to the AWS Console as an administrator.

 2. Tag a running, non-essential
    [EC2 instance](https://console.aws.amazon.com/ec2/home#Instances)
    with:

    - `sched-stop` : `d=_ H:M=11:30` , replacing 11:30 with the
      [current UTC time](https://www.timeanddate.com/worldclock/timezone/utc) +
      20 minutes, rounded upward to :00, :10, :20, :30, :40, or :50.

 3. Install Lights Off using CloudFormation or Terraform.

    - **CloudFormation**<br/>_Easy_ &check;

      [Create a CloudFormation stack](https://console.aws.amazon.com/cloudformation/home#/stacks/create).

      Select "Upload a template file", then select "Choose file" and navigate
      to a locally-saved copy of
      [cloudformation/lights_off_aws.yaml](/../../blob/v3.6.1/cloudformation/lights_off_aws.yaml?raw=true)
      [right-click to save as...].

      On the next page, set:

      - Stack name: `LightsOff`

    - **Terraform**

      Check that you have at least:

      - [Terraform v1.10.0 (2024-11-27)](https://github.com/hashicorp/terraform/releases/tag/v1.10.0)
      - [Terraform AWS provider v6.0.0 (2025-06-18)](https://github.com/hashicorp/terraform-provider-aws/releases/tag/v6.0.0)

      Add the following child module to your existing root module:

      ```terraform
      module "lights_off" {
        source = "git::https://github.com/sqlxpert/lights-off-aws.git//terraform?ref=v3.6.1"
        # Reference a specific version from github.com/sqlxpert/lights-off-aws/releases
        # Check that the release is immutable!
      }
      ```

      Have Terraform download the module's source code. Review the plan before
      typing `yes` to allow Terraform to proceed with applying the changes.

      ```shell
      terraform init
      terraform apply
      ```

 4. Wait for resource creation to complete.

    <details>
      <summary>If there is an "UnreservedConcurrentExecution" error...</summary>

    <br/>

    Request that
    [Service Quotas &rarr; AWS services  &rarr; AWS Lambda &rarr; Concurrent executions](https://console.aws.amazon.com/servicequotas/home/services/lambda/quotas/L-B99A9384)
    be increased. The default is `1000`&nbsp;.

    Lights Off needs 1&nbsp;unit for a time-critical function. New AWS accounts
    start with a quota of 10, but Lambda always holds back 10, which leaves 0
    available! Within a given AWS account, the quota is set separately for
    each region.

    </details>

 5. After about 20 minutes, check whether the EC2 instance is stopped. Restart
    it and delete the `sched-stop` tag.

Jump to:
[Extra Setup](#extra-setup)
&bull;
[Multi-Account, Multi-Region](#multi-account-multi-region-cloudformation-stackset)

## Tag Keys (Operations)

||`sched-stop`|`sched-hibernate`|`sched-backup`|
|:---|:---:|:---:|:---:|
||**`sched-start`**|||
|EC2:||||
|[Instance](https://console.aws.amazon.com/ec2/home#Instances)|[&check;](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/Stop_Start.html)|[&check;](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/hibernating-prerequisites.html)|&rarr; Image (AMI)|
|[EBS Volume](https://console.aws.amazon.com/ec2/home#Volumes)|||&rarr; Snapshot|
|RDS and Aurora:||||
|[Database Instance](https://console.aws.amazon.com/rds/home#databases:)|[&check;](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_StopInstance.html)||&rarr; Snapshot|
|[Database Cluster](https://console.aws.amazon.com/rds/home#databases:)|[&check;](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-cluster-stop-start.html)||&rarr; Snapshot|

>Whether a database operation is at the cluster or instance level depends on
your choice of Aurora or RDS, and for RDS, on your database's configuration.

## Tag Values (Schedules)

### Work Week Examples

These cover Monday to Friday daytime work hours, 07:30 to 19:30, year-round
(see
[time zone converter](https://www.timeanddate.com/worldclock/converter.html?p1=1440&p2=103&p3=224&p4=75&p5=64&p6=179&p7=175&p8=136&p9=133&p10=195&p11=367&p12=54)).

|Locations|Hours Saved|`sched-start`|`sched-stop`|
|:---|:---:|:---:|:---:|
|USA Mainland|**> 50%**|`u=1 u=2 u=3 u=4 u=5 H:M=11:30`|`u=2 u=3 u=4 u=5 u=6 H:M=03:30`|
|North America<br/>(from&nbsp;Hawaii<br/>to&nbsp;Newfoundland)|**> 40%**|`u=1 u=2 u=3 u=4 u=5 H:M=10:00`|`u=2 u=3 u=4 u=5 u=6 H:M=05:30`|
|Europe|**> 50%**|`u=1 u=2 u=3 u=4 u=5 H:M=04:30`|`u=1 u=2 u=3 u=4 u=5 H:M=19:30`|
|India|**> 60%**|`u=1 u=2 u=3 u=4 u=5 H:M=02:00`|`u=1 u=2 u=3 u=4 u=5 H:M=14:00`|
|North America<br/>+&nbsp;Europe|**> 20%**|`u=1 H:M=04:30`|`u=6 H:M=05:30`|
|North America<br/>+&nbsp;Europe<br/>+&nbsp;India|**> 20%**|`u=1 H:M=02:00`|`u=6 H:M=05:30`|
|Europe<br/>+&nbsp;India|**> 40%**|`u=1 u=2 u=3 u=4 u=5 H:M=02:00`|`u=1 u=2 u=3 u=4 u=5 H:M=19:30`|

#### Stopping an RDS or Aurora Database Longer than 7 Days

<details>
  <summary>To stop a database indefinitely...</summary>

<br/>

RDS and Aurora automatically start stopped databases after 7&nbsp;days. Install
[github.com/sqlxpert/step-stay-stopped-aws-rds-aurora](https://github.com/sqlxpert/step-stay-stopped-aws-rds-aurora#get-started)
to re-stop them automatically, _or_ set a once-a-week `sched-start` and add
days to `sched-stop`&nbsp;:

|Locations|`sched-start`|`sched-stop`|
|:---|:---:|:---:|
|USA Mainland|`uTH:M=6T02:30`|`d=_ H:M=03:30`|
|North America (from&nbsp;Hawaii to&nbsp;Newfoundland)|`uTH:M=6T04:30`|`d=_ H:M=05:30`|
|Europe|`uTH:M=5T18:30`|`d=_ H:M=19:30`|
|India|`uTH:M=5T13:00`|`d=_ H:M=14:00`|
|North America +&nbsp;Europe|`uTH:M=6T04:30`|&#9888;&nbsp;`u=6 u=7 H:M=05:30`|
|North America +&nbsp;Europe +&nbsp;India|`uTH:M=6T04:30`|&#9888;&nbsp;`u=6 u=7 H:M=05:30`|
|Europe +&nbsp;India|`uTH:M=5T18:30`|`d=_ H:M=19:30`|

- If the database usually takes longer than 1&nbsp;hour to start, change
  `sched-start` to an earlier time (and to the preceding weekday, if
  necessary).
- For most time zone combinations, `sched-stop` can be made daily. If a
  database takes longer than usual to start, another stop attempt will occur
  the next day. If you start the database manually, it will be stopped
  automatically at the end of the day.
- &#9888; For North&nbsp;America&nbsp;+&nbsp;Europe&nbsp;[+&nbsp;India], stop
  attempts will occur only on weekends. If you start the database manually,
  stop it manually when you are finished.
- Set the database's weekly maintenance window to a time period when the
  database will be running.

</details>

### Rules

- Coordinated Universal Time (UTC)
- 24-hour clock
- Days before times, hours before minutes
- The day, the hour and the minute must all be resolved
- Multiple operations on the same resource at the same time are _all_ canceled

Space was chosen as the separator and underscore, as the wildcard, because
[RDS does not allow commas or asterisks](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_Tagging.html#Overview.Tagging).

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
|Once a day|`d=_` or d=_NN_ or u=_N_ first!|`H:M=00:00` ... `H:M=23:50`|
|Once a week||`uTH:M=1T00:00` ... `uTH:M=7T23:50`|
|Once a month||`dTH:M=01T00:00` ... `dTH:M=31T23:50`|

### Backup Examples

|`sched-backup`|Description|
|:---:|:---:|
|`d=01 d=15 H=03 H=19 M=00`|Traditional cron: 1st and 15th days of the month, at 03:00 and 19:00|
|`d=_ H:M=03:00 H=_ M=15 M=45`|Every day, at 03:00 _plus_ every hour at 15 and 45 minutes after the hour|
|`dTH:M=01T00:00`|Start of month _(instead of end of month)_|
|`dTH:M=01T03:00 uTH:M=5T19:00 d=_ H=11 M=15`|1st day of the month at 03:00, _plus_ Friday at 19:00, _plus_ every day at 11:15|

## Extra Setup

### Starting EC2 Instances with Encrypted EBS Volumes

In most cases, you can use the `sched-start` tag without setup.

<details>
  <summary>If you use custom KMS encryption keys from a different AWS account...</summary>

<br/>

The `sched-start` tag works for EC2 instances with EBS volumes if:

- Your EBS volumes are unencrypted, or
- You use the default, AWS-managed `aws/ebs` encryption key, or
- You use custom keys in the same AWS account as each EC2 instance, the key
  policies contain the default `"Enable IAM User Permissions"` statement, and
  they do not contain `"Deny"` statements.

Because your custom keys are in a different AWS account than your EC2
instances, you must add a statement like the following to the key policies:

```json
    {
      "Sid": "LightsOffEc2StartInstancesWithEncryptedEbsVolumes",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "kms:CreateGrant",
      "Resource": "*",
      "Condition": {
        "ForAnyValue:StringLike": {
          "aws:PrincipalOrgPaths": "o-ORG_ID/r-ROOT_ID/ou-PARENT_ORG_UNIT_ID/*"
        },
        "ArnLike": {
          "aws:PrincipalArn": "arn:aws:iam::ACCOUNT:role/*LightsOff*-DoLambdaFnRole-*"
        },
        "StringLike": {
          "kms:ViaService": "ec2.*.amazonaws.com"
        },
        "Bool": {
          "kms:GrantIsForAWSResource": "true"
        }
      }
    }
```

- One account: Delete the entire `"ForAnyValue:StringLike"` section and
  replace _ACCOUNT_ with the account number of the AWS account in which you
  have installed Lights Off.

- AWS Organizations: Replace _ACCOUNT_ with `*` and _o-ORG_ID_ , _r-ROOT_ID_ ,
  and _ou-PARENT_ORG_UNIT_ID_ with the identifiers of your organization, your
  organization root, and the organizational unit in which you have installed
  Lights Off. `/*` at the end of this organization path stands for child OUs,
  if any. Do not use a path less specific than `"o-ORG_ID/*"`&nbsp;.

>If an EC2 instance does not start as scheduled, a KMS key permissions error is
possible.

</details>

### Making Backups

You can use the `sched-backup` tag with minimal setup if you work in a small
number of regions and/or AWS accounts. Use the AWS Console to view the
[list of AWS Backup vaults](https://console.aws.amazon.com/backup/home#/backupvaults)
one time in each AWS account and region. Make one backup in each AWS account
([AWS Backup](https://console.aws.amazon.com/backup/home#) &rarr; My account
&rarr; Dashboard &rarr; On-demand backup). If you use _custom_ KMS keys, they
must be in the same AWS account as the disks and databases encrypted with
them.

<details>
  <summary>If you work across many regions and/or AWS accounts...</summary>

<br/>

Because you want to use the `sched-backup` tag in a complex AWS environment,
you must address the following AWS Backup requirements:

 1. Vault

    AWS Backup creates the `Default` vault the first time you open the
    [list of vaults](https://console.aws.amazon.com/backup/home#/backupvaults)
    in a given AWS account and region, using the AWS Console. Otherwise, see
    [Backup vault creation](https://docs.aws.amazon.com/aws-backup/latest/devguide/create-a-vault.html)
    and
    [AWS::Backup::BackupVault](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-backup-backupvault.html)
    or
    [aws_backup_vault](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/backup_vault)&nbsp;.
    Update the `BackupVaultName` CloudFormation stack parameter if necessary.

 2. Vault policy

    If you have added `"Deny"` statements, be sure that `DoLambdaFnRole` still
    has access.

 3. Backup role

    AWS Backup creates `AWSBackupDefaultServiceRole` the first time you make a
    backup in a given AWS account using the AWS Console
    ([AWS Backup](https://console.aws.amazon.com/backup/home#) &rarr; My
    account &rarr; Dashboard &rarr; On-demand backup). Otherwise, see
    [Default service role for AWS Backup](https://docs.aws.amazon.com/aws-backup/latest/devguide/iam-service-roles.html#default-service-roles).
    Update the `BackupRoleName` parameter if necessary.

 4. KMS key policies

    `AWSBackupDefaultServiceRole` works if:

    - Your EBS volumes and RDS/Aurora databases are unencrypted, or
    - You use the default, AWS-managed `aws/ebs` and `aws/rds` encryption keys,
      or
    - You use custom keys in the same AWS account as each disk and database,
      the key policies contain the default `"Enable IAM User Permissions"`
      statement, and they do not contain `"Deny"` statements.

    If your custom keys are in a different AWS account than your disks and
    databases, you must modify the key policies. See
    [Encryption for backups in AWS Backup](https://docs.aws.amazon.com/aws-backup/latest/devguide/encryption.html),
    [How EBS uses KMS](https://docs.aws.amazon.com/kms/latest/developerguide/services-ebs.html),
    [Overview of encrypting RDS resources](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Overview.Encryption.html#Overview.Encryption.Overview),
    and
    [Key policies in KMS](https://docs.aws.amazon.com/kms/latest/developerguide/key-policies.html).

>If no backup jobs appear in AWS Backup, or if jobs do not start, a permissions
problem is likely.

</details>

### Hidden Policies

Service and resource control policies (SCPs and RCPs), permissions boundaries,
and session policies can interfere with the installation or usage of Lights
Off. Check with your AWS administrator!

## Accessing Backups

|Goal|Services|
|:---|:---:|
|List backups|AWS Backup|
|View underlying images and/or snapshots|EC2 and RDS|
|Restore (create new resources from) backups|EC2 and RDS, or AWS Backup|
|Delete backups|AWS Backup|

AWS Backup copies resource tags to backups. Lights Off adds `sched-time` to
indicate when the backup was _scheduled_ to occur, in
[ISO 8601](https://en.wikipedia.org/wiki/ISO_8601#Combined_date_and_time_representations)
basic format (example: `20241231T1400Z`).

## On/Off Switch

- You can toggle the `Enable` parameter of your Lights Off CloudFormation
  stack, CloudFormation StackSet, or Terraform module.
- While Enable is `false`, scheduled operations do not happen; they are
  skipped permanently.

## Logging and Monitoring

 1. Check the
    [LightsOff CloudWatch log group](https://console.aws.amazon.com/cloudwatch/home#logsV2:log-groups$3FlogGroupNameFilter$3DLightsOff-).
    - Log entries are JSON objects.
      - Lights Off includes `"level"` , `"type"` and `"value"` keys.
      - Other software components may use different keys.
    - For more data, change the `LogLevel` parameter.
    - Scrutinize log entries at the `ERROR` level.
      - All entries with the `"stackTrace"` key represent unexpected exceptions
        that require correction. These are unusual.
      - "Find" function log streams:
        All other entries at the `ERROR` level require correction.
      - "Do" function log streams:
        Some other entries at the `ERROR` level do not require correction.

        <details>
          <summary>What to consider when evaluating errors...</summary>

          <br/>

          The state of an AWS resource might change between the "Find" and "Do"
          steps; this sequence is fundamentally non-atomic. An operation might
          also be repeated due to queue message delivery logic; operations are
          idempotent. If a state change is favorable or an operation is
          repeated, Lights Off logs success responses or expected exceptions
          (depending on the AWS service) at the `INFO` level. For RDS database
          _instance_ start/stop operations, however, expected exceptions are
          logged at the `ERROR` level because Lights Off cannot determine
          whether they represent actual errors or harmless repetition (such as
          trying to start a database instance that has already been started).

          For complete details, see the technical article
          [Idempotence: Doing It More than Once](https://sqlxpert.github.io/2025/05/17/idempotence-doing-it-more-than-once.html).

        </details>

 2. Check the `ErrorQueue`
    [SQS queue](https://console.aws.amazon.com/sqs/v3/home#/queues)
    for "Find" and "Do" events that were not delivered, or not fully
    processed.

 3. Check
    [CloudTrail Event history](https://console.aws.amazon.com/cloudtrailv2/home?ReadOnly=false/events#/events?ReadOnly=false)
    for the final stages of `sched-start` and `sched-backup` operations.
    - CloudTrail events with an "Error code" may indicate permissions problems,
      typically due to the local security configuration.
    - To see more events, change "Read-only" from `false` to `true` .

### Why No Built-In Monitoring?

<details>
  <summary>Whether and how to monitor Lights Off...</summary>

<br/>

Two strengths of this tool are its distributed design and its simplicity.

Lights Off operates independently in each region, in each AWS account. Every
(region, account) pair has its own log and error queue. Operation does not
depend on central resources, other than an optional customer-managed
multi-region KMS key. Centralized logging and monitoring would introduce a
single point of failure and add complexity, only to duplicate AWS features that
can cover all of your applications.

Consider monitoring Lights Off through...

- The [organization CloudTrail](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/creating-trail-organization.html)
  or
- [CloudWatch Logs data centralization](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CloudWatchLogs_Centralization.html)

...which might already be configured in your organization.

The fetish for metrics, dashboards, and alerts raises a deeper question. Is it
_worth_ paging someone over an unsuccessful EC2 instance stop request? Probably
not! If large amounts of money are at stake, you need
[AWS Budgets](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-controls.html).
The thresholds, notifications, and actions you define there cover any and all
tools, applications, provisioning processes, and people, not just Lights Off.

Backups _are_ worth monitoring, but at the point of consumption, not at the
point of creation. No matter how you create backups, you should implement an
automated process to restore critical ones (the first hourly backup of the day,
for example) and validate the results.
[AWS Backup restore testing](https://docs.aws.amazon.com/aws-backup/latest/devguide/restore-testing.html)
solves this problem.

When your organization becomes large and formal, you will graduate from
friendly, locally-managed `sched-backup` tags to centralized
[backup plans](https://docs.aws.amazon.com/aws-backup/latest/devguide/about-backup-plans.html).
Then, you can use
[AWS Backup Audit Manager](https://docs.aws.amazon.com/aws-backup/latest/devguide/controls-and-remediation.html)
to continuously check your resources, your plans, and the presence of your
backups. (You will still have to validate the backups.) Consider quitting
before your job shifts from making software to making PowerPoint presentations.

Employees, consultants, and vendors who demonstrate pretty dashboards should
instead start by asking what is material to you. You should ask whether AWS
provides standard ways to gather the information you actually care about.

</details>

## Advanced Installation

### Multi-Account, Multi-Region (CloudFormation StackSet)

For reliability, Lights Off works completely independently in each region, in
each AWS account. To deploy to multiple regions and/or AWS accounts,

 1. Delete any standalone Lights Off CloudFormation _stacks_ in the target AWS
    accounts and regions (including any instances of the basic `//terraform`
    module; you will be installing one instance of the `//terraform-multi`
    module).

 2. Complete the prerequisites for creating a _StackSet_ with
    [service-managed permissions](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-orgs-enable-trusted-access.html).

 3. Make sure that the AWS Lambda `Concurrent executions` quota is sufficient
    in every target AWS account, in every target region. See the note in
    [Quick Start](#quick-start) Step&nbsp;4.

 4. Install Lights Off as a CloudFormation StackSet, using CloudFormation or
    Terraform. You must use your AWS organization's management account, or a
    delegated administrator AWS account.

    - **CloudFormation**<br/>_Easy_ &check;

      [Create a CloudFormation StackSet](https://console.aws.amazon.com/cloudformation/home#/stacksets/create).

      Select "Upload a template file", then select "Choose file" and upload a
      locally-saved copy of
      [cloudformation/lights_off_aws.yaml](/../../blob/v3.6.1/cloudformation/lights_off_aws.yaml?raw=true)
      [right-click to save as...].

      On the next page, set:

      - StackSet name: `LightsOff`

      On the "Set deployment options" page, under "Accounts", select "Deploy
      stacks in organizational units". Enter the `ou-` ID(s). Lights Off will
      be deployed to all AWS accounts within the organizational unit(s). Next,
      "Specify Regions".

    - **Terraform**

      Your module block will now resemble:

      ```terraform
      module "lights_off_stackset" {
        source = "git::https://github.com/sqlxpert/lights-off-aws.git//terraform-multi?ref=v3.6.1"
        # Reference a specific version from github.com/sqlxpert/lights-off-aws/releases
        # Check that the release is immutable!

        lights_off_stackset_regions                 = ["us-east-1", "us-west-2",]
        lights_off_stackset_organizational_unit_ids = ["ou-0123-abcdefg",]
      }
      ```

      You can customize
      [concurrency and error handling](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-concepts.html#stackset-ops-options)
      for StackSet operations by setting the
      `lights_off_stackset_operation_preferences` module variable. These
      preferences apply to the StackSet as a whole, if you update the
      CloudFormation template or change a parameter. They also apply to
      StackSet instances affected when you change the region list or the
      organizational unit list. The module automatically defines StackSet
      instances based on the cross product
      `lights_off_stackset_regions`&nbsp;&times;&nbsp;`lights_off_stackset_organizational_unit_ids`&nbsp;.

      <details>
        <summary>Defining your own StackSet instances...</summary>

      <br/>

      Your CloudFormation StackSet deployment targets might be more complex
      than the cross product
      `lights_off_stackset_regions`&nbsp;&times;&nbsp;`lights_off_stackset_organizational_unit_ids`&nbsp;.
      You might want to deploy Lights Off in different regions, depending on
      the organizational unit, or in different OUs, depending on the region.
      You might also want to include or exclude specific AWS account numbers.
      You can also selectively override CloudFormation parameter values.

      |Goal|Explanation|
      |:---|:---|
      |Vary combinations of regions and organizational units|[CreateStackInstances](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_CreateStackInstances.html)|
      |Include or exclude accounts|[DeploymentTargets](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_DeploymentTargets.html#API_DeploymentTargets_Contents)|
      |Override parameters|[`aws_cloudformation_stack_set_instance`](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudformation_stack_set_instance#argument-reference)`.`[`parameter_overrides`](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudformation_stack_set_instance#parameter_overrides-1)|

      To define all Lights Off StackSet instances yourself, leave the
      `lights_off_stackset_organizational_unit_ids` list empty, or do not set
      this module variable at all.

      To define some or all StackSet instances yourself, add one or more
      resource blocks after the module block:

      ```terraform
      resource "aws_cloudformation_stack_set_instance" "lights_off" {
        stack_set_name = module.lights_off_stackset.lights_off_stackset_name

        stack_set_instance_region = "us-east-1"
        # Use an element of module.lights_off_stackset.lights_off_stackset_regions

        operation_preferences {
          # Arbitrary HashiCorp Configuration Language (HCL) syntax rules
          # forbid assigning an entire object value to a block, and instead
          # require assigning the attributes one by one.
          # https://developer.hashicorp.com/terraform/language/attr-as-blocks#:~:text=this%20page%20only%20applies,prior%20to%20Terraform%20v0.12

          concurrency_mode        = module.lights_off_stackset.operation_preferences["concurrency_mode"]
          region_concurrency_type = module.lights_off_stackset.operation_preferences["region_concurrency_type"]
          region_order            = module.lights_off_stackset.operation_preferences["region_order"]

          max_concurrent_percentage = lookup(
            module.lights_off_stackset.operation_preferences,
            "max_concurrent_percentage",
            null
          )
          max_concurrent_count = lookup(
            module.lights_off_stackset.operation_preferences,
            "max_concurrent_count",
            null
          )

          failure_tolerance_percentage = lookup(
            module.lights_off_stackset.operation_preferences,
            "failure_tolerance_percentage",
            null
          )
          failure_tolerance_count = lookup(
            module.lights_off_stackset.operation_preferences,
            "failure_tolerance_count",
            null
          )
        }

        # ...other attributes...
      }
      ```

      </details>

### Installation with Terraform

[Quick Start](#quick-start)
Step&nbsp;3 includes the option to install Lights Off as a Terraform module in
one region in one AWS account. This is the basic `//terraform` module.

The
[enhanced region support](https://registry.terraform.io/providers/hashicorp/aws/6.0.0/docs/guides/enhanced-region-support)
added in v6.0.0 of the Terraform AWS provider makes it possible to deploy
resources in multiple regions _in one AWS account_ without configuring a
separate provider for each region. Lights Off is compatible because the
Terraform module was written for AWS provider v6, the original CloudFormation
templates always let
[CloudFormation assign unique physical names](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/resources-section-structure.html#resources-section-physical-id)
to account-wide, non-regional resources like IAM roles, and the CloudFormation
parameters were already region-independent. Your module block will now
resemble:

```terraform
module "lights_off" {
  source = "git::https://github.com/sqlxpert/lights-off-aws.git//terraform?ref=v3.6.1"
  # Reference a specific version from github.com/sqlxpert/lights-off-aws/releases
  # Check that the release is immutable!

  for_each          = toset(["us-east-1", "us-west-2",])
  lights_off_region = each.key
}
```

For installation in multiple AWS accounts (regardless of the number of
regions), wrapping a CloudFormation _StackSet_ in HashiCorp Configuration
Language remains much easier than configuring Terraform to deploy identical
resources in multiple AWS accounts. The
[Multi-Account, Multi-Region (CloudFormation StackSet)](#multi-account-multi-region-cloudformation-stackset)
installation instructions include the option to do this using a Terraform
module, in Step&nbsp;4. This is the `//terraform-multi` module.

### Least-Privilege Installation

<details>
  <summary>Least-privilege installation details...</summary>

#### CloudFormation Stack Least-Privilege

You can use a
[CloudFormation service role](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-iam-servicerole.html)
to delegate only the privileges needed to create the `LightsOff` stack. (This
is done for you if you use Terraform at Step&nbsp;3 of the
[Quick Start](#quick-start).)

First, create the `LightsOffPrereq` stack from
[cloudformation/lights_off_aws_prereq.yaml](/../../blob/v3.6.1/cloudformation/lights_off_aws_prereq.yaml?raw=true)&nbsp;.

Under "Additional settings" &rarr; "Stack policy - optional", you can "Upload a
file" and select a locally-saved copy of
[cloudformation/lights_off_aws_prereq_policy.json](/../../blob/v3.6.1/cloudformation/lights_off_aws_prereq_policy.json?raw=true)&nbsp;.
The stack policy prevents inadvertent replacement or deletion of the deployment
role during stack updates, but it cannot prevent deletion of the entire
`LightsOffPrereq` stack.

Next, when you create the `LightsOff` stack from
[cloudformation/lights_off_aws.yaml](/../../blob/v3.6.1/cloudformation/lights_off_aws.yaml?raw=true)&nbsp;,
set "Permissions - optional" &rarr; "IAM role - optional" to
`LightsOffPrereq-DeploymentRole`&nbsp;. If your own privileges are limited, you
might need permission to pass the deployment role to CloudFormation. See the
`LightsOffPrereq-SampleDeploymentRolePassRolePol` IAM policy for an example.

#### CloudFormation StackSet Least-Privilege

For a CloudFormation _StackSet_, you can use
[self-managed permissions](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-prereqs-self-managed.html)
by copying the inline IAM policy of `LightsOffPrereq-DeploymentRole` to a
customer-managed IAM policy, attaching your policy to
`AWSCloudFormationStackSetExecutionRole` and propagating the policy and the
role policy attachment to all target AWS accounts.

#### Terraform Least-Privilege

If you do not give Terraform full AWS administrative permissions, you must give
it permission to:

- List, describe, get tags for, create, tag, update, untag and delete
  IAM roles, update the "assume role" (role trust or "resource-based")
  policy, and put and delete in-line policies
- Create, tag, describe, update, untag and delete
  `arn:aws:s3:::terraform-*` S3 buckets
  and put, tag, list, get, untag and delete
  `arn:aws:s3:::terraform-*/*` S3 objects
- List, describe, create, tag, update, untag, and delete CloudFormation
  stacks
- Set and get CloudFormation stack policies
- Pass `LightsOffPrereq-DeploymentRole-*` to CloudFormation
- List, describe, and get tags for, all `data` sources. For a list, run:

  ```shell
  grep 'data "' terraform*/*.tf | cut --delimiter=' ' --fields='1,2' | sort | uniq
  ```

Open the
[AWS Service Authorization Reference](https://docs.aws.amazon.com/service-authorization/latest/reference/reference_policies_actions-resources-contextkeys.html#actions_table),
go through the list of services on the left, and consult the "Actions"
table for each of:

- `AWS Identity and Access Management (IAM)`
- `Amazon S3`
- `CloudFormation`
- `AWS Security Token Service`
- `AWS Backup` (if you use the `sched-backup` tag)
- `AWS Key Management Service` (if you encrypt the SQS queues and/or the
  CloudWatch log group with KMS keys)
- `AWS Organizations` (if you create a CloudFormation StackSet with the
  `//terraform-multi` module)

In most cases, you can scope Terraform's permissions to one workload by
regulating resource naming and tagging, and then by using:

- [ARN patterns in `Resource` lists](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_resource.html#reference_policies_elements_resource_wildcards)
- [ARN patterns in `Condition` entries](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_condition_operators.html#Conditions_ARN)
- [Request tag and then resource tag `Condition` entries](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_tags.html)

Check Service and Resource Control Policies (SCPs and RCPs), as well as
resource policies (such as AWS Backup vault policies and KMS key
policies).

The basic `//terraform` module creates the `LightsOffPrereq` stack, which
defines the IAM role that gives CloudFormation the permissions it needs to
create the `LightsOff` stack. Terraform itself does not need the deployment
role's permissions.

</details>

## Security

>In accordance with the software license, nothing in this document creates a
warranty, an indemnification, an assumption of liability, etc. Use this
software at your own risk. You are encouraged to evaluate the source code.

### Security Design Goals

<details>
  <summary>Security goals...</summary>

<br/>

- Least-privilege roles for the AWS Lambda functions that find resources and
  do scheduled operations. The "Do" function is authorized to perform a small
  set of operations, and at that, only when a resource has the correct tag
  key. (AWS Backup creates backups, using a role that you can configure.)
- A least-privilege queue policy. The operation queue can only consume
  messages from the "Find" function and produce messages for the "Do" function,
  or the error queue, if an operation fails. Encryption in transit is
  required for both queues.
- Readable IAM policies, broken down into discrete statements by service,
  resource or principal. Policies are formatted as CloudFormation YAML rather
  than as native JSON, except when it's necessary to allow insertion of
  custom, user-specified JSON.
- Optional encryption at rest with the AWS Key Management System (KMS), for
  queue message bodies (may contain resource identifiers) and for log entries
  (may contain resource metadata).
- No data storage other than in queues and logs, with short or configurable
  retention periods.
- Tolerance for clock drift in a distributed system. The "Find" function
  starts 1&nbsp;minute into the 10-minute cycle and operation queue entries
  expire 9&nbsp;minutes in.
- An optional CloudFormation service role for least-privilege deployment.

</details>

### Security Steps You Can Take

<details>
  <summary>Security actions...</summary>

<br/>

- Only allow trusted people and services to tag AWS resources. A sample
  [service control policy](#service-control-policy) is available.
- Prevent people who can set the `sched-backup` tag from deleting backups.
- Prevent people from modifying components, most of which can be identified by
  `LightsOff` in ARNs and in the automatic `aws:cloudformation:stack-name`
  tag. Limiting permissions so that the deployment role is _necessary_ for
  CloudFormation stack modifications is ideal.
- Prevent people from directly invoking the AWS Lambda functions and from
  passing the function roles to arbitrary functions.
- Log infrastructure changes using AWS CloudTrail, and set up alerts.
- Automatically copy backups to an AWS Backup vault in an isolated account.
  Lights Off is compatible with my
  [Backup Events](https://github.com/sqlxpert/backup-events-aws)
  utility.
- Separate production workloads. You might choose not to deploy Lights Off to
  AWS accounts used for production, or you might add a custom policy to the
  "Do" function's role, denying authority to stop production resources. See the
  `AttachLocalPolicy` parameter.
- If you use Terraform, do not use it with an AWS access key and do not give it
  full AWS administrative privileges. Instead, follow AWS's
  [Best practices for using the Terraform AWS Provider: Security best practices](https://docs.aws.amazon.com/prescriptive-guidance/latest/terraform-aws-provider-best-practices/security.html).
  Do the extra work of defining a least-privilege IAM role for deploying each
  workload. Configure Terraform to assume workload-specific roles. The
  CloudFormation service role is one element, but achieving least-privilege
  also requires limiting _Terraform's_ privileges.

</details>

### Service Control Policy

<details>
  <summary>Protecting schedule tags...</summary>

<br/>

A sample service control policy is available to prevent tampering with Lights
Off schedule tags.

This SCP offers two-way protection: roles subject to the SCP can neither remove
nor add schedule tags. They cannot change existing schedule tag values, either.

In your AWS Organizations management account, in the region where you manage
infrastructure-as-code templates for non-regional resources, create a
CloudFormation stack from
[cloudformation/scp_protect_lights_off_tags.yaml](/../../blob/v3.6.1/cloudformation/scp_protect_lights_off_tags.yaml?raw=true)&nbsp;.

Or, reference the equivalent Terraform module:

```terraform
module "lights_off_scp" {
  source = "git::https://github.com/sqlxpert/lights-off-aws.git//terraform-scp?ref=v3.6.1"
  # Reference a specific version from github.com/sqlxpert/lights-off-aws/releases
  # Check that the release is immutable!

  scp_target_ids = [
    "ou-0123-abcdefg",
  ]
}
```

In either case, specify the number of the account or the `ou-` ID of the
organizational unit that you use for testing SCPs.

Test the SCP before applying it broadly, because it generally reduces existing
EC2, EBS, and RDS/Aurora tagging permissions. Human users or automated
processes might rely on those permissions. This is especially true of backup
restoration, blue/green deployment, and cluster scaling workflows, which might
copy tags to new resources.

You will need at least one SCP-exempt role in every AWS account, to manage
schedule tags. I recommend
[IAM Identity Center permission sets](https://docs.aws.amazon.com/singlesignon/latest/userguide/permissionsets.html).
You can customize `ScpPrincipalCondition` / `scp_principal_condition` to
[reference permission set roles](https://docs.aws.amazon.com/singlesignon/latest/userguide/referencingpermissionsets.html).

The SCP works by denying certain tag addition/change and removal requests. It
cannot _add_ permissions that have been denied by another SCP, or that were
never allowed by a role's attached or inline policies.

SCPs do not affect roles or other IAM principals in the AWS&nbsp;Organizations
management account.

</details>

## Advice

- Test Lights Off in your own AWS environment. After following the suggestions
  in the
  [Logging and Monitoring](#logging-and-monitoring)
  section, please
  [report bugs](https://github.com/sqlxpert/lights-off-aws/issues).

- Be aware: of charges for S3 (holds CloudFormation templates, even if you use
  Terraform), EventBridge Scheduler, AWS Lambda, SQS, CloudWatch Logs, KMS,
  backup storage, and early deletion from cold storage; of the minimum charge
  when you stop an EC2 instance with a commercial license, or any RDS database;
  of the resumption of charges when RDS/Aurora restarts a stopped database
  after 7&nbsp;days; and of ongoing storage charges and potential public IP
  address charges while EC2 instances and RDS/Aurora databases are stopped.
  What have we missed? &#128184;

- Test your backups! Are they finishing on-schedule? Can they be restored
  successfully?

## Bonus: Delete and Recreate Expensive Resources on a Schedule

<details>
  <summary>Scheduled CloudFormation stack update details...</summary>

<br/>

Lights Off can delete and recreate many types of expensive AWS infrastructure
in your own CloudFormation stacks, based on cron schedules in stack tags.

Deleting AWS Client VPN resources overnight, while developers are asleep, is
a sample use case. See
[10-minute AWS Client VPN](https://github.com/sqlxpert/10-minute-aws-client-vpn#automatic-scheduling).

To make your own CloudFormation template compatible, see
[cloudformation/lights_off_aws_bonus_cloudformation_example.yaml](/../../blob/v3.6.1/cloudformation/lights_off_aws_bonus_cloudformation_example.yaml)
.

Not every resource needs to be deleted and recreated; condition the creation
of _expensive_ resources on the `Enable` parameter. In the AWS Client VPN
stack, the VPN endpoints and VPC security groups are not deleted, because they
do not cost anything. The VPN attachments can be deleted and recreated with no
need to reconfigure VPN clients.

Set the `sched-set-Enable-true` and `sched-set-Enable-false` tags on
your own CloudFormation stack and make sure that the
`EnableSchedCloudFormationOps` parameter is set to `true` (the default) in your
Lights Off CloudFormation stack/StackSet or Terraform module. At the scheduled
times, Lights Off will perform a stack update, toggling the value of the
`Enable` parameter to `true` or `false`. (Capitalize **E**nable in the tag keys,
to match the parameter name.)

If your tagged stack lacks a CloudFormation service role, Lights Off logs an
error of `"type"` `STACK_NEEDS_SERVICE_ROLE` in a "Find" log stream in the
[log](#logging-and-monitoring).
To make scheduled updates possible, you must first perform a stack update in
which you attach an IAM role that gives CloudFormation the permissions it
needs to manage the resources defined in your stack. See the `RoleARN` request
parameter in the
[`UpdateStack` reference](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_UpdateStack.html#API_UpdateStack_RequestParameters).

&#128161; Because you can attach a different service role by performing a stack
update, you may wish to maintain two roles, a less restrictive one that you can
use for stack creation, arbitrary modification, and deletion, and a restrictive
one that you can leave in place for automated stack updates. The latter role
need only support the AWS actions invoked when the stack's `Enable` parameter
changes from `true` to `false` and vice versa.

If the status of your tagged stack is other than `CREATE_COMPLETE` or
`UPDATE_COMPLETE` at the scheduled time, Lights Off logs an error of `"type"`
`STACK_STATUS_IRREGULAR` in a "Find" log stream, instead of attempting an
update that is likely to fail and require a rollback. To resume scheduled stack
updates, resolve the underlying template error or permissions error and
successfully complete one manual stack update.

The sample
[service control policy](#service-control-policy)
does _not_ cover `sched-set-Enable-true` and `sched-set-Enable-false` tags on
CloudFormation stacks (or StackSets, whose tags would be copied to member
stack instances). Because
[UpdateStack](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_UpdateStack.html#:~:text=tags.-,If%20you%20don't%20specify,CloudFormation%20doesn't%20modify%20the%20stack's%20tags.)
overwrites the entire set of tags, distinguishing between adding a tag,
preserving an existing tag's value, explicitly removing a tag, and removing a
tag by removing all tags, requires multiple IAM policy statements for each tag
key. Only privileged roles should be allowed to create and update
CloudFormation stacks/StackSets, including their tags.

</details>

## Extensibility

<details>
  <summary>Extensibility details...</summary>

<br/>

Lights Off takes advantage of patterns in boto3, the AWS software development
kit (SDK) for Python, and in the underlying AWS API. Adding AWS services,
resource types, and operations is easy. For example, supporting Aurora
database _clusters_ (RDS database _instances_ were already supported) required
adding:

```python
    AWSRsrcType(
      "rds",
      ("DB", "Cluster"),
      {
        ("start", ): {},
        ("stop", ): {},
        ("backup", ): {},
      },
      rsrc_id_key_suffix="Identifier",
      tags_key="TagList",
    )
```

Given the words `DB` and `Cluster` in the resource type name, plus the
operation verb `start`, the `sched-start` tag key and the `start_db_cluster`
method name are derived mechanically.

If an operation method takes more than just the resource identifier, add a
dictionary of static keyword arguments. For complex arguments, sub-class the
`AWSOp` class and override `op_kwargs`&nbsp;.

The `start_backup_job` method takes an Amazon Resource Name (ARN), whose
format is consistent for all resource types. As long as AWS Backup supports
the resource type, there is no extra work to do.

Add statements like the one below to the Identity and Access Management (IAM)
policy for the role used by the "Do" AWS Lambda function, to authorize
operations. You must of course authorize the role used by the "Find" function
to describe (list) resources.

```yaml
          - Effect: Allow
            Action: rds:StartDBCluster
            Resource: !Sub "arn:${AWS::Partition}:rds:${AWS::Region}:${AWS::AccountId}:cluster:*"
            Condition:
              "Null": { "aws:ResourceTag/sched-start": "false" }
```

Let me know what resource types you'd like me to add!

</details>

## Progress

I wrote
[TagSchedOps](https://github.com/sqlxpert/aws-tag-sched-ops),
the original version of Lights Off, in 2017, before Systems Manager, Data
Lifecycle Manager or AWS Backup existed. Lights Off remains a simple
alternative to
[Systems Manager Automation runbooks for stopping EC2 instances](https://docs.aws.amazon.com/systems-manager-automation-runbooks/latest/userguide/automation-aws-stopec2instance.html),
etc. It is now integrated with AWS Backup, leveraging the security and
management benefits (including backup retention lifecycle policies) but
offering a simple alternative to
[backup plans](https://docs.aws.amazon.com/aws-backup/latest/devguide/about-backup-plans.html).

### Counting Complexity

|Year|Lambda Python Lines|Core CloudFormation YAML Lines|Core Terraform HCL Lines|
|:---:|:---:|:---:|:---:|
|2017|&asymp;&nbsp;775|&asymp;&nbsp;2,140||
|2022|630|800&nbsp;&check;||
|2025|620&nbsp;&check;|1,000|&asymp;&nbsp;270|
|2026|620|1,120|270|

Here I report "loc" figures from GitHub. Figures for CloudFormation are net of
in-line Lambda Python code. GitHub seems to count _non-blank, non-comment
lines_, for a rough indication of complexity.

In the introduction, I reported _total lines_ of code for my Lambda Python
source file, because blank lines and comment lines contribute to the reading
experience. To provide an order-of-magnitude comparison of complexity, I
counted non-blank, non-comment lines in Instance Scheduler `.py` files without
`test` in their paths. People would never read all the Python source in AWS's
Instance Scheduler, which is my point!

## Dedication

This project is dedicated to ej, Marianne and R&eacute;gis, Ivan, and to the
wonderful colleagues whom Paul has worked with over the years. Thank you to
Corey for sharing it with the AWS user community in _Last Week in AWS_
newsletter issues
[286 (2022-10-03)](https://www.lastweekinaws.com/newsletter/amazon-file-cash/#h-tools)
and
[424 (2025-05-27)](https://www.lastweekinaws.com/newsletter/putting-my-wife-on-a-pip/#h-tools),
and to Lee for suggesting the new name.

## Licenses

|Scope|Link|Included Copy|
|:---|:---:|:---:|
|Source code files, and source code embedded in documentation files|[GNU General Public License (GPL) 3.0](http://www.gnu.org/licenses/gpl-3.0.html)|[LICENSE-CODE.md](/LICENSE-CODE.md)|
|Documentation files (including this ReadMe file)|[GNU Free Documentation License (FDL) 1.3](http://www.gnu.org/licenses/fdl-1.3.html)|[LICENSE-DOC.md](/LICENSE-DOC.md)|

Copyright Paul Marcelin

Contact: `marcelin` at `cmu.edu` (replace "at" with `@`)
