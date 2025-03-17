# Lights Off!

Do you forget to turn the lights off? Lights Off can:

1. Stop and restart EC2 instances and RDS databases based on cron-style
   schedules in their tags. Perfect for development and test systems that sit
   idle overnight and on weekends, this simple trick cuts AWS costs up to 66%.

2. Back up EC2 instances, EBS volumes, and RDS databases. Tags on the
   resources tell you exactly when backups will occur. You benefit from the
   AWS Backup service without having to write, and reference, backup plans.

3. Delete and recreate expensive infrastructure in your own CloudFormation
   stacks.

Jump to:
[Quick Install](#quick-start) &bull;
[Tags](#tag-keys-operations) &bull;
[Schedules](#tag-values-schedules) &bull;
[Security](#security) &bull;
[Multi-Region/Multi-Account](#advanced-installation) &bull;
[Advice](#general-advice)

## Quick Start

1. Log in to the AWS Console as an administrator.

2. Tag an
   [EC2 instance](https://console.aws.amazon.com/ec2/v2/home#Instances)
   with:

   * `sched-backup` : `d=_ H:M=11:30` , replacing 11:30 with the
     [current UTC time](https://www.timeanddate.com/worldclock/timezone/utc)
     \+ 20 minutes. Round up to :00, :10, :20, :30, :40, or :50.

3. Create an
   [S3 bucket](https://console.aws.amazon.com/s3/home)
   for AWS Lambda function source code. Name it:

   * `my-bucket-us-east-1` , replacing my-bucket with the name of your choice,
     and us-east-1 with the code for the
     [region](http://docs.aws.amazon.com/general/latest/gr/rande.html#regional-endpoints)
     of your EC2 instance. Check, near the top right of the EC2 Console and
     the S3 Console, that the region is the same.

   _Security Tip:_ Block public access to the bucket, and limit write access.

4. Upload a locally-saved copy of
   [lights_off_aws.py.zip](/lights_off_aws.py.zip?raw=true)
   to your S3 bucket.

   _Security Tip:_ Compare the Entity tag (Etag) shown by S3 with the checksum
   in
   [lights_off_aws.py.zip.md5.txt](/lights_off_aws.py.zip.md5.txt?raw=true)

5. Create a
   [CloudFormation stack](https://console.aws.amazon.com/cloudformation/home).
   Select Upload a template file, then click Choose file and navigate to a
   locally-saved copy of
   [lights_off_aws.yaml](/cloudformation/lights_off_aws.yaml?raw=true)
   . On the next page, set:

   * Stack name: `LightsOff`
   * Lambda code S3 bucket: Exclude the region. For example, if your bucket is
     my-bucket-us-east-1, enter `my-bucket` .

6. After about 20 minutes, check
   [images (AMIs)](https://console.aws.amazon.com/ec2/v2/home#Images:sort=desc:creationDate).

7. Before deregistering (deleting) the image that was created, note its ID
   (`ami-`) so that you delete the underlying
   [EBS snapshots](https://console.aws.amazon.com/ec2/v2/home#Snapshots:visibility=owned-by-me;v=3;tag:Name=:zsched-;sort=desc:startTime).
   Remember to delete the `sched-backup` tag from your EC2 instance.

## Tag Keys (Operations)

||||||||
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
|Stop|`sched-stop`|`sched-hibernate`||||`sched-set-Enable-false`|
|Start|`sched-start`|`sched-start`||||`sched-set-Enable-true`|
|Other|||`sched-backup`|`sched-reboot`|`sched-reboot-failover`||
|[EC2 instance](https://console.aws.amazon.com/ec2/v2/home#Instances)|&check;|&check;|image (AMI)|&check;|||
|[EBS volume](https://console.aws.amazon.com/ec2/v2/home#Volumes)|||snapshot||||
|[RDS database instance](https://console.aws.amazon.com/rds/home#databases:)|&check;||database snapshot|&check;|&check;||
|[RDS database cluster](https://console.aws.amazon.com/rds/home#databases:)|&check;||cluster snapshot||&check;||
|[CloudFormation stack](https://console.aws.amazon.com/cloudformation/home#/stacks)||||||&check;|

* All backups, regardless of underlying type, are managed in [AWS Backup](https://console.aws.amazon.com/backup/home#/backupvaults).
* Not all EC2 instances support hibernation.
* Not all RDS database clusters support cluster-level reboot.
* Scheduling multiple operations on the same resource at the same time
  produces an error.

## Tag Values (Schedules)

### Terms

  |Type|Literal Values|Wildcard|
  |--|--|--|
  |Day of month|`d=01` ... `d=31`|`d=_`|
  |[ISO 8601 weekday](https://en.wikipedia.org/wiki/ISO_8601#Week_dates)|`u=1` (Monday) ... `u=7` (Sunday)||
  |Hour|`H=00` ... `H=23`|`H=_`|
  |Minute (multiple of 10)|`M=00` , `M=10` , `M=20` , `M=30` , `M=40` , `M=50`||
  |Daily|`H:M=00:00` ... `H:M=23:50`||
  |Weekly|`uTH:M=1T00:00` ... `uTH:M=7T23:50`||
  |Monthly|`dTH:M=01T00:00` ... `dTH:M=31T23:50`||

### Examples

  |Tag Value|Scenario|Meaning|
  |--|--|--|
  |`d=01 d=15 H=03 H=19 M=00`|`cron`-style|03:00 and 19:00 the 1st and 15th days of the month|
  |`d=_ H:M=08:50 H=_ M=10 M=40`|Extra daily operation|10 and 40 minutes after the hour, every hour, _plus_ 08:50 every day|
  |`uTH:M=2T03:30 uTH:M=5T07:20 d=_ H=11 M=00`|2 extra weekly operations|11:00 every day, _plus_  03:30 every Tuesday and 07:20 every Friday|
  |`dTH:M=01T05:20 u=3 H=22 M=10`|Extra monthly operation|22:10 every Wednesday, _plus_ 05:20 the 1st day of the month|

### Rules

* Universal Coordinated Time
* 24-hour clock
* Days before times, and hours before minutes
* The day, the hour and the minute must all be specified in some way
* For end-of-month, use start-of-month, `dTH:M=01T00:00` , because some months
  lack `d=29` through `d=31`

### Rationale

* Separator and wildcard: [RDS does not allow , or \*](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_Tagging.html#Overview.Tagging)
* Letters:
  [`strftime()`](http://manpages.ubuntu.com/manpages/xenial/man3/strftime.3.html#description)

## Backups

### Services

* Use AWS Backup to list and delete backups.
* Use EC2 and RDS to view the underlying images and snapshots.
* Use AWS Backup, or EC2 and RDS, to restore (create new resources from)
  backups.

### Tags

AWS Backup copies resource tags to backups on a best effort basis. For
convenience, Lights Off adds an
[ISO 8601](https://en.wikipedia.org/wiki/ISO_8601#Combined_date_and_time_representations)-formatted
`sched-time` tag (example: `2024-12-31T14:00Z`) to indicate when the backup
was _scheduled_ to occur.

## On/Off Switch

* You can toggle the `Enable` parameter of your Lights Off CloudFormation
  stack.
* While Enable is `false`, scheduled operations do not happen; they are
  skipped permanently.

## Logging

* Check the
  [`LightsOff` CloudWatch log groups](https://console.aws.amazon.com/cloudwatch/home#logsV2:log-groups$3FlogGroupNameFilter$3DLightsOff-).
* Log entries are JSON objects. For application log entries, reference the
  `type` key for a consistent classification and the `value` key for the data.
  System log entries use other keys, including `message` .
* To see more or fewer log entries, change the `LogLevel` parameter in
  CloudFormation.

## Security

_In accordance with the software license, nothing in this section creates a
warranty, an indemnification, an assumption of liability, etc. Use this
software entirely at your own risk. You are encouraged to evaluate the code,
which is open-source._

### Design Goals

* Distinct, least-privilege roles for the AWS Lambda functions that find
  resources and "do" scheduled operations. The "do" function is only
  authorized to perform a small set of operations, and at that, only when a
  resource has the right tag key. (The AWS Backup service creates backups,
  using a role that you specify.)

* A least-privilege policy for the queue linking the two functions. The
  operation queue can only consume messages from the "find" function and
  produce messages for the "do" function (or a dead-letter queue, if an
  operation fails). Encryption in transit is required.

* Readable IAM policies, formatted as CloudFormation YAML rather than as JSON
  and broken down into discrete statements by service, resource or principal.

* Optional encryption at rest with custom AWS Key Management System (KMS)
  keys, for queue message bodies (which contain the identifiers and tags of
  AWS resources) and for log entries.

* No data storage other than in queues and logs. Retention periods for the
  dead letter queue and the logs are configurable. The fixed retention period
  for the operation queue is short.

* Tolerance for clock drift in a distributed system. The "find" function
  starts 1 minute into the 10-minute cycle and operation queue entries expire
  9 minutes into the cycle.

* A checksum for the AWS Lambda function source code bundle. (The bundle is
  included for the benefit of new users and those without formal pipelines.)

* An optional, least-privilege CloudFormation service role for deployment.

### Security Steps You Can Take

* Only allow trusted people and services to tag AWS resources. You can
  deny the right to add, change and delete `sched-` tags by including the
  [`aws:TagKeys` condition key](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_tags.html#access_tags_control-tag-keys)
  in a permission boundary.

* Never authorize a role that can create backups (or, in this case, set tags
  to schedule backups) delete backups as well.

* Prevent people from modifying components of Lights Off, most of which can be
  identified by `LightsOff` in ARNs and in the automatic
  `aws:cloudformation:stack-name` tag. Limiting people's permissions so that
  the deployment role is _necessary_ for stack modifications is ideal. Short
  of that, you could copy the deployment role's in-line policy, delete the
  statements with `"Resource": "*"`, change the `"Effect"` of the remaining,
  resource-specific statements to `"Deny"`, and include the inverted policy in
  a permission boundary.

* Add policies to prevent people from directly invoking Lights Off AWS Lambda
  functions and from passing the associated roles to any other functions.

* Log infrastructure changes using AWS CloudTrail, and set up alerts.

* Automatically copy backups to an AWS Backup vault in an isolated account.

* Separate production workloads. You might choose not to deploy Lights Off to
  AWS accounts used for production, or you might customize the "do" function's
  role, removing the authority to reboot and stop production resources (
  `AttachLocalPolicy` ).

## Advanced Installation

### Multi-Region

If you plan to deploy Lights Off to multiple regions, always:

1. Create S3 buckets with the same name prefix but different region codes in
   all target
   [regions](http://docs.aws.amazon.com/general/latest/gr/rande.html#regional-endpoints).
   For example, create `my-bucket-us-east-1` in US East (Northern Virginia)
   and `my-bucket-us-west-2` in US West (Oregon).

2. Upload
   [lights_off_aws.py.zip](/lights_off_aws.py.zip)
   to each bucket. AWS Lambda requires a copy in every region.

### Multi-Account (CloudFormation StackSet)

<details>
  <summary>View multi-account installation steps</summary>

To centrally deploy Lights Off to multiple AWS accounts (and multiple
regions),

1. Delete any standalone Lights Off CloudFormation stacks in the target AWS
   accounts and regions.

2. Follow the
   [multi-region instructions](#multi-region),
   above.

3. Edit the bucket policy of each S3 bucket, allowing read access from all AWS
   accounts within the target Organizational Unit (OU). Look up your
   Organization ID (`o-`), Root ID (`r-`), and Organizational Unit IDs (`ou-`)
   in
   [AWS Organizations](https://console.aws.amazon.com/organizations/v2/home/accounts).

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Sid": "FromAllAwsAccountsWithinOrganizationalUnit",
         "Effect": "Allow",
         "Principal": {
           "AWS": "*"
         },
         "Condition": {
           "ForAnyValue:StringLike": {
              "aws:PrincipalOrgPaths": [
                "o-ORG_ID/r-ROOT_ID/ou-PARENT_ORG_UNIT_ID*"
              ]
           }
         },
         "Action": "s3:GetObject*",
         "Resource": "arn:aws:s3:::BUCKET_NAME/*"
       }
     ]
   }
   ```

4. Complete the prerequisites for creating a StackSet with
   [service-managed permissions](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-orgs-enable-trusted-access.html)
   (_not_ self-managed permissions).

5. In the management AWS account (or a delegated administrator account),
   create a
   [CloudFormation StackSet](https://console.aws.amazon.com/cloudformation/home#/stacksets).
   Select Upload a template file, then click Choose file and upload a
   locally-saved copy of
   [lights_off_aws.yaml](/cloudformation/lights_off_aws.yaml?raw=true)
   . On the next page, set:

   * StackSet name: `LightsOff`
   * Lambda code S3 bucket: Exclude regions. For example, if your buckets are
     my-bucket-us-east-1 and my-bucket-us-west-2, enter `my-bucket` .

6. Two pages later, under Deployment targets, select Deploy to Organizational
   Units (OUs). Enter the AWS OU ID of the target Organizational Unit. Lights
   Off will be deployed to all AWS accounts within this Organizational Unit.
   Toward the bottom of the page, specify the target regions.

</details>

### Least-Privilege

You can use a
[CloudFormation service role](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-iam-servicerole.html)
to delegate only the privileges needed to create a Lights Off CloudFormation
stack. First, create a stack named `LightsOffPrereq` from
[lights_off_aws_prereq.yaml](/cloudformation/lights_off_aws_prereq.yaml?raw=true)
. Later, when you create a stack named `LightsOff` from
[lights_off_aws.yaml](/cloudformation/lights_off_aws.yaml?raw=true) ,
scroll up to the Permissions section and set IAM role -
optional to `LightsOffPrereq-DeploymentRole` . If your own privileges are
limited, you might need explicit permission to pass the deployment role to
CloudFormation. See the `LightsOffPrereq-SampleDeploymentRolePassRolePol` IAM
policy for an example.

The deployment role covers a stack in single AWS account, but you can copy the
in-line policies to `AWSCloudFormationStackSetExecutionRole` in multiple
target accounts if you want to deploy a StackSet with
[self-managed permissions](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-prereqs-self-managed.html).

## Software Updates

* For CloudFormation template changes, update your CloudFormation stack or
  StackSet in-place.

* For AWS Lambda function Python source code changes, upload the new
  [lights_off_aws.py.zip](/lights_off_aws.py.zip?raw=true) bundle to S3 and
  create a new `LightsOff2` CloudFormation stack or StackSet, but set `Enable`
  to `false` . After you've deleted the old `LightsOff` stack or StackSet,
  update the new one, chaning `Enable` to `true`. A simple blue/green
  deployment procedure avoids the problem of making CloudFormation notice that
  the Lambda bundle has changed.

## Updating a CloudFormation Stack on a Schedule

<details>
  <summary>View scheduled stack update setup details</summary>

You can use Lights Off to delete and recreate expensive AWS infrastructure in
your own CloudFormation stack, on a schedule.

Turning off expensive AWS Client VPN resources overnight, while developers are
asleep, is a sample use case. See
[10-minute AWS Client VPN](https://github.com/sqlxpert/10-minute-aws-client-vpn?tab=readme-ov-file#automatic-scheduling)
for potential savings of $600 per year.

To make your own CloudFormation template compatible, see
[lights_off_aws_cloudformation_ops_example.yaml](/cloudformation/lights_off_aws_cloudformation_ops_example.yaml)
. CloudFormation "transforms" are not compatible.

`sched-set-Enable-true` and `sched-set-Enable-false` tags on your own
CloudFormation stack determine when Lights Off will update the stack. At the
scheduled times, Lights Off will toggle your own stack's `Enable` parameter to
`true` or `false` , while leaving other parameters, and template itself,
unchanged. Capitalize **E**nable in the tag keys, just as in the parameter
name.

Not every resource needs to be deleted and recreated based on the `Enable`
parameter. You need only condition creation of _expensive_ resources on the
`Enable` parameter. In the AWS Client VPN stack, the server and client
certificates, endpoints and network security groups are always retained,
because they don't cost anything. The expensive VPN attachments can be deleted
and recreated with no need to reconfigure VPN clients.
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

Most method names can be derived mechanically if you use the same verb in the
method name and the tag key, and break the resource type name into words.
words. Given the tag key `sched-start` and the words `DB` and `Cluster` ,
the method name `start_db_cluster` follows.

Optionally, you can add a dictionary of static keyword arguments. You can also
sub-class the `AWSOp` class if a method requires truly complex arguments.

The AWS Backup `start_backup_job` method takes an Amazon Resource Name (ARN),
whose format is standard for all resource types. As long as AWS Backup
supports resource type in question, there is nothing special to do.

```yaml
          - Effect: Allow
            Action: rds:StartDBCluster
            Resource: !Sub "arn:${AWS::Partition}:rds:${AWS::Region}:${AWS::AccountId}:cluster:*"
            Condition:
              StringLike: { "aws:ResourceTag/sched-start": "*" }
```

Adding statements like the one above to the Identity and Access Management
(IAM) policy for the role used by the "do" AWS Lambda function authorizes
operations on the new resource type. You must also authorize the role used by
the "find" function to describe (list) resources of the new resource type.

What AWS resources and operations would _you_ like to add?
</details>

## General Advice

* Routinely test your backups! Are backups happening as scheduled? Can you
  restore your backups successfully? AWS Backup's restore testing feature
  can help.

* Be aware: of charges for running AWS Lambda functions, queueing to SQS,
  logging to CloudWatch Logs, storing backups, and deleting backups from cold
  storage too early; of minimum billing periods when you stop an RDS database
  or an EC2 instance with a commercial license; of ongoing storage charges for
  stopped EC2 instances and RDS databases; and of charges that resume when RDS
  automatically restarts a database that has been stopped for 7 days. Other AWS
  charges may apply!

* Test the AWS Lambda functions, SQS queues, and IAM policies in your own AWS
  environment. To help improve Lights Off, please submit
  [bug reports and feature requests](https://github.com/sqlxpert/lights-off-aws/issues),
  as well as [proposed changes](https://github.com/sqlxpert/lights-off-aws/pulls).

## Future Work

* Automated testing
* Makefile for AWS Lambda .zip bundle
* Variable sched-set-_Parameter_-_value_ tag key to set an arbitrary
  CloudFormation stack parameter to an arbitrary value

## History

This project was originally called TagSchedOps. I began working on it in 2017,
long before AWS Backup, Data Lifecycle Manager, or Systems Manager existed.

## Dedication

This work is dedicated to ej Salazar, Marianne and R&eacute;gis Marcelin,
and also to the wonderful colleagues I've worked with over the years.

## Licenses

|Scope|Link|Included Copy|
|--|--|--|
|Source code files, and source code embedded in documentation files|[GNU General Public License (GPL) 3.0](http://www.gnu.org/licenses/gpl-3.0.html)|[LICENSE-CODE.md](/LICENSE-CODE.md)|
|Documentation files (including this readme file)|[GNU Free Documentation License (FDL) 1.3](http://www.gnu.org/licenses/fdl-1.3.html)|[LICENSE-DOC.md](/LICENSE-DOC.md)|

Copyright Paul Marcelin

Contact: `marcelin` at `cmu.edu` (replace "at" with `@`)
