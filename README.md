# Lights Off!

For AWS users who forget to turn off the lights:

* **Cut AWS costs up to ⅔ in your sleep**, by tagging EC2 instances and RDS
  databases with `cron`-style stop/start schedules! Lights Out is ideal for
  development and test systems, which are idle at night and on weekends.

* You can also tag EC2 instances, EBS volumes, and RDS databases to schedule
  backups.

* If you tag your own custom CloudFormation stacks, Lights Off can even
  delete/recreate their expensive resources on schedule!

Jump to:
[Installation](#quick-start) &bull;
[Operations](#tag-keys-operations) &bull;
[Schedules](#tag-values-schedules) &bull;
[Security](#security-model) &bull;
[Multi-region/multi-account](#advanced-installation) &bull;
[CloudFormation Operations](#lights-off-cloudformation-operations)

## Comparison with AWS Services

AWS introduced AWS Backup, Data Lifecycle Manager, and Systems Manager after
mid-2017, when I started this project, formerly called TagSchedOps. The 3
relevant AWS services have become more capable over the years, but Lights Off
still has advantages:

* Schedules and operations are immediately visible, in tags on the EC2 instance,
  EBS volume, RDS database, or CloudFormation stack. You don't need to look up
  schedules and rules in other AWS services.

* Schedules and operations are easy to update. Just edit an AWS resource's
  tags!

* One tool handles a variety of scheduled operations in EC2, RDS, and
  CloudFormation. Why should you have to use one service to schedule a backup,
  and a different service to schedule a reboot?

## Quick Start

1. Log in to the [AWS Web Console](https://signin.aws.amazon.com/console).

2. Go to [EC2 instances](https://console.aws.amazon.com/ec2/v2/home#Instances).
   Add the following tag to a sample instance:

   * `sched-backup` : `d=_ H:M=11:30` , replacing 11:30 with the
     [current UTC time](https://www.timeanddate.com/worldclock/timezone/utc)
     plus 20 minutes. Round the time to the nearest 10 minutes.

3. Go to the
   [S3 Console](https://console.aws.amazon.com/s3/home).
   Create a bucket for AWS Lambda function source code:

   * Bucket name: `my-bucket-us-east-1` , replacing my-bucket with the name of your choice,
     and us-east-1 with the region in which your EC2 instance is located. Be
     sure to create the bucket in that region.

   _Security Tip:_ Block public access to the bucket, and limit write access

4. Upload
   [lights_off_aws.py.zip](/lights_off_aws.py.zip)
   to the S3 bucket.

   _Security Tip:_ Compare the Entity tag (Etag) reported by S3 with the
   file's checksum in
   [lights_off_aws.py.zip.md5.txt](/lights_off_aws.py.zip.md5.txt)

5. Go to the
   [CloudFormation Console](https://console.aws.amazon.com/cloudformation/home).
   Click Create Stack. Click Choose File, immediately below Upload a template
   to Amazon S3, and navigate to your local copy of
   [cloudformation/lights_off_aws.yaml](/cloudformation/lights_off_aws.yaml)
   . On the next page, set:

   * Stack name: `LightsOff`
   * Lambda code S3 bucket: Name of your bucket, not including the region. For
     example, if your bucket is my-bucket-us-east-1 , set this to `my-bucket` .

6. After 20 minutes, check
   [images](https://console.aws.amazon.com/ec2/v2/home#Images:sort=desc:creationDate).

7. Before deregistering (deleting) the sample image that was created, note its
   ID, so that you delete the underlying
   [EBS volume snapshots](https://console.aws.amazon.com/ec2/v2/home#Snapshots:visibility=owned-by-me;v=3;tag:Name=:zsched-;sort=desc:startTime).
   Also remember to delete the `sched-backup` tag from your EC2 instance.

## Tag Keys (Operations)

||`sched-start` or `‑stop`|`sched-hibernate`|`sched-backup`|`sched-reboot-backup`|`sched-reboot`|`sched-reboot-failover`|`sched-set-Enable-true` or `‑false`|
|--|--|--|--|--|--|--|--|
|[EC2 instance](https://console.aws.amazon.com/ec2/v2/home#Instances)|&check;|&check;|image (AMI)|image (AMI)|&check;|||
|[EBS volume](https://console.aws.amazon.com/ec2/v2/home#Volumes)|||volume snapshot|||||
|[RDS database instance](https://console.aws.amazon.com/rds/home#databases:)|&check;||database snapshot||&check;|&check;||
|[RDS database cluster](https://console.aws.amazon.com/rds/home#databases:)|&check;||database cluster snapshot||&check;||
|[CloudFormation stack](https://console.aws.amazon.com/cloudformation/home#/stacks)|||||||&check;|

* Not all EC2 instances support hibernation.
* Not all RDS database clusters support cluster-level reboot.

## Tag Values (Schedules)

* Terms:

  |Name|Minimum|Maximum|Wildcard|
  |--|--|--|--|
  |Day of month|`d=01`|`d=31`|`d=_`|
  |Weekday|`u=1` (Monday)|`u=7` (Sunday)||
  |Hour|`H=00`|`H=23`|`H=_`|
  |Minute (multiples of 10)|`M=00`|`M=50`||
  |Once a day|`H:M=00:00`|`H:M=23:50`||
  |Once a week|`uTH:M=1T00:00`|`uTH:M=7T23:50`||
  |Once a month|`dTH:M=01T00:00`|`dTH:M=31T23:50`||

* Examples:

  |Tag Value|Scenario|Meaning|
  |--|--|--|
  |`d=01 d=15 H=03 H=19 M=00`|`cron`-style|03:00 and 19:00 the 1st and 15th days of every month|
  |`d=_ H:M=14:20`|Once a day|14:20 every day|
  |`uTH:M=1T14:20`|Once a week|14:20 every Monday|
  |`dTH:M=28T14:20`|Once a month|14:20 the 28th day of every month|
  |`d=_ H:M=08:50 H=_ M=10 M=40`|Extra daily operation|10 and 40 minutes after the hour, every hour of every day, _plus_ 08:50 every day|
  |`uTH:M=2T03:30 uTH:M=5T07:20 d=_ H=11 M=00`|2 extra weekly operations|11:00 every day, _plus_  03:30 every Tuesday and 07:20 every Friday|
  |`dTH:M=00T05:20 u=3 H=22 M=10`|Extra monthly operation|22:10 every Wednesday, _plus_ 05:20 the 1st day of every month|

* Time zone: always UTC
* Clock: 24-hour
* Last digit of minute: always 0
* Approximate time: 10-minute cycle (14:20 means _after 14:20 but before
  14:30_, for example.)
* 2 digits: required for hour, minute, and numeric day of month values (Use a
  leading zero if necessary.)
* Wildcard: 1 underscore `_` (RDS does not allow asterisks in tags.)
* Term separator: space (RDS does not allow commas in tags.)
* Order: days before times, and hours before minutes (For fast
  matching, any "once a month" and "once a week" terms should go first.)
* Completeness: the day, the hour and the minute must all be specified in some
  way, or no operation will happen
* Multiple values: use multiple terms of the same type (For example,
  `d=01 d=15` means _the 1st and 15th days of the month_.)
* End-of-month: consider `dTH:M=01T00:00` because some months lack `d=29`
  through `d=31`
* Multiple operations on the same resource, at the same time: none will
  happen, and an error will be logged
* Standards: letters match
  [`strftime()`](http://manpages.ubuntu.com/manpages/xenial/man3/strftime.3.html#description)
  and weekday numbers match
  [ISO 8601](https://en.wikipedia.org/wiki/ISO_8601#Week_dates)
  (`cron` uses different weekday numbers.)

## Child Resources

Backup operations create a "child" resource (image or snapshot) from a
"parent" AWS resource (instance, volume or database).

### Name

|#|Part|Example|Purpose|
|--|--|--|--|
|1|Prefix|`zsched`|Identify and group resources created by Lights Off. `z` sorts after most manually-created images and snapshots.|
|2|Parent name or identifier|`webserver`|Conveniently identify the parent by `Name` tag value or physical identifier. Multiple children of the same parent sort together, by creation date and time.|
|3|Date and time|`20171231T1400Z`|Group children created at the same time. Minute is always a multiple of 10. Time zone is always UTC (Z).|
|4|Random suffix|`g3a8a`|Guarantee a unique name. 5 characters are chosen from a small set of unambiguous letters and numbers.|

* Parts are separated with hyphens (`-`).
* Parent name or identifier may contain additional, internal hyphens.
* Characters forbidden by AWS are replaced with `X` .
* For some resource types, the description is also set to the name, in case the
  Console shows only one or the other.

### Tags

|Tag|Description|
|--|--|
|`Name`|Friendly name of the child. The EC2 Console derives the Name column from `Name` tag values.|
|`sched-parent-name`|`Name` tag value from the parent. May be blank.|
|`sched-parent-id`|Physical identifier of the parent.|
|`sched-op`|Operation tag key that prompted creation of the child. Distinguishes special cases, such as whether an EC2 instance was rebooted before an image was created (`sched-reboot-backup`).|
|`sched-cycle-start`|Date and time when the child was created. Minute is always a multiple of 10. Time zone is always UTC (Z).|

* Although AWS stores most of this information as resource properties/metadata,
  the field names/keys vary by AWS service, as do the search capabilities --
  and some stored values, such as exact creation time, are too precise to
  allow for grouping. Searching tags, on the other hand, works in both EC2 and
  RDS.

* User-created tags whose keys don't begin with `sched-` are copied from parent
  to child. You can change the `CopyTags` parameter of your Lights Off
  CloudFormation stack to prevent this, for example, if your organization has
  different tagging rules for EC2 instances and images.

## Logging

* Check the
  [`LightsOff` CloudWatch log groups](https://console.aws.amazon.com/cloudwatch/home#logsV2:log-groups$3FlogGroupNameFilter$3D$252Faws$252Flambda$252FLightsOff-).
* Log messages (except for uncaught exceptions) are JSON objects, with a
  `Type` key to classify the message and indicate which other keys will be
  present.
* You can change the `LogLevel` parameter of your Lights Off CloudFormation
  stack to see more messages.

## On/Off Switch

* You can change the `Enable` parameter of your Lights Off CloudFormation
  stack.
* This applies per-region and per-AWS-account.
* While Enable is `false`, scheduled operations do not happen; they are
  skipped permanently and cannot be reprised.

## Security Model

* Allow only a few trusted people to tag AWS resources. You can restrict the
  right to add, change and delete `sched-` tags by including the
  [`aws:TagKeys` condition key](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_tags.html#access_tags_control-tag-keys)
  in IAM policies, permission boundaries, and service control policies.

* Sometimes, such restrictive policies have the effect of requiring users to
  change or delete only one tag at a time.

* Do not allow a role that can create backups (or, in this case, set tags to
  prompt backup creation) to delete backups as well.

* Note these AWS security gaps:

  * Authority to create an EC2 instance image includes authority to reboot.
    (Explicitly denying the reboot privilege does not help.) A harmless
    privilege, taking a backup, is married with a risky one, rebooting.

  * In RDS, permission to add a specific tag also includes permission to add
    _any other_ tags in the same API call!

## Advanced Installation

### Multi-Region

If you intend to deploy Lights Off in multiple regions, whether by creating a
CloudFormation stack in each region or by creating a CloudFormation StackSet
covering multiple regions (and possibly multiple AWS accounts),

1. Create S3 buckets for AWS Lambda function source code in all
   [regions](http://docs.aws.amazon.com/general/latest/gr/rande.html#regional-endpoints)
   of interest. Use the same bucket name prefix and append the region code for
   the region in which you are creating the bucket. For example, create
   `my-bucket-us-east-1` in US East (N. Virginia) and `my-bucket-us-west-2` in
   US West (Oregon).

2. Upload
   [lights_off_aws_perform.py.zip](/lights_off_aws_perform.py.zip)
   to each bucket. AWS Lambda requires a copy in every region.

### Multi-Account (CloudFormation StackSets)

To centrally deploy Lights Off to multiple accounts (and multiple regions),

1. Delete any standalone Lights Off CloudFormation stacks in the accounts and
   regions of interest.

2. Follow the [multi-region instructions](#multi-region), above.

3. Edit the bucket policy of each S3 bucket, allowing access from all AWS
   accounts under the parent organization unit (OU) of interest. Look up your
   Organization ID (`o-`), Root ID (`r-`), and Organization Unit IDs (`ou-`)
   in
   [AWS Organizations](https://console.aws.amazon.com/organizations/v2/home/accounts).

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Sid": "FromParentOrganizationUnit",
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
         "Action": [
           "s3:GetObject",
           "s3:GetObjectVersion"
         ],
         "Resource": "arn:aws:s3:::BUCKET_NAME/*"
       }
     ]
   }
   ```

4. Complete the prerequisites for creating a StackSet with
   [service-managed permissions](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-orgs-enable-trusted-access.html)
   (_not_ self-managed permissions).

5. In the management AWS account (or a delegated administrator account), go to
   [CloudFormation StackSets](https://console.aws.amazon.com/cloudformation/home#/stacksets).

6. Click Create StackSet, then select Upload a template file, then click
   Choose file and navigate to your local copy of
   [cloudformation/lights_off_aws.yaml](/cloudformation/lights_off_aws.yaml)
   . On the next page, set:

   * StackSet name: `LightsOff`
   * Lambda code S3 bucket: Name of your buckets, not including any region.
     For example, if one of your buckets is my-bucket-us-east-1 , set this to
     `my-bucket` .

7. Two pages later, under Deployment targets, select Deploy to organizational
   units (OUs). Enter the AWS OU ID of the parent organization unit. Lights
   Off will be deployed to all AWS accounts under this organization unit.
   Below, specify the regions of interest.

### Least-Privilege

If you are an advanced AWS user and your organization follows least-privilege
principles, you can use a
[CloudFormation service role](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-iam-servicerole.html)
to give CloudFormation only the privileges it needs to create a Lights Off
CloudFormation stack. First, create a CloudFormation stack named
`LightsOffPrereqs` , from
[cloudformation/lights_off_aws_prereqs.yaml](/cloudformation/lights_off_aws_prereqs.yaml)
Later, when you create a stack named `LightsOff` from
[cloudformation/lights_off_aws.yaml](/cloudformation/lights_off_aws.yaml),
scroll up to the Permissions section and set IAM role -
optional to `LightsOffPrereqs-DeploymentRole` .

The deployment role is intended for a single AWS account, but you can copy its
in-line IAM policy to the `AWSCloudFormationStackSetExecutionRole` in multiple
target accounts, if you want to deploy a CloudFormation StackSet with
[self-managed permissions](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-prereqs-self-managed.html).

## Software Updates

* When CloudFormation template changes are published, Lights Off-related
  stacks and StackSets can be updated in-place.

* When AWS Lambda function source code changes are published, it is easier to
  create a new stack or StackSet such as `LightsOff02`, set its Enable
  parameter to `false` initially, delete the old stack or StackSet, and then
  enable the new one. (CloudFormation otherwise has to be coaxed to recognize
  that the source source code, which is stored in S3, had changed.)

## Lights Off CloudFormation Operations

Using tags on your own custom CloudFormation stack to change a stack
parameter on schedule is an advanced Lights Off feature.

A sample use case is toggling the deletion of an
`AWS::EC2::ClientVpnTargetNetworkAssociation` at the end of the work day
(while leaving other AWS Client VPN resources intact). At 10¢ per hour, this
can save up to $650 per year. Temporarily restoring VPN access during
off-hours is as simple as performing a manual stack update, or temporarily
adding the next multiple of 10 minutes to the `sched-set-Enable-true` tag!

To make your custom CloudFormation template compatible with Lights Off, follow
the instructions in the sample template,
[cloudformation/lights_off_aws_cloudformation_ops_example.yaml](/cloudformation/lights_off_aws_cloudformation_ops_example.yaml)

Once all resource definitions and permissions are correct, Lights Off will
update your stack according to the schedules in your stack's
`sched-set-Enable-true` and `sched-set-Enable-false` tags, preserving the
previous template and the previous parameter values but setting the value of
the `Enable` parameter to `true` or `false` each time. Note the capitalization
of the parameter name in the tag key.

## Parting Advice

* Test your backups! Can they be restored successfully?

* Rebooting EC2 instances is necessary for coherent file system backups, but
  it takes time and carries risks. Use `sched-reboot-backup` less frequently
  than `sched-backup` (no reboot).

* Be aware: of charges for running the AWS Lambda functions, queueing
  scheduled operations in SQS, logging to CloudWatch Logs, and storing images
  and snapshots; of the whole-hour cost when you stop an RDS database or an
  EC2 Windows or commercial Linux instance (but [other EC2 instances have a
  1-minute minimum](https://aws.amazon.com/blogs/aws/new-per-second-billing-for-ec2-instances-and-ebs-volumes/);
  of ongoing storage charges for stopped EC2 instances and RDS databases; and
  of charges that resume when RDS automatically restarts a database that has
  been stopped for 7 days. Other AWS charges may apply!

* Test the AWS Lambda functions, SQS queue and IAM policies in your own AWS
  environment. To help improve Lights Off, please submit
  [bug reports and feature requests](https://github.com/sqlxpert/lights-off-aws/issues),
  as well as [proposed changes](https://github.com/sqlxpert/lights-off-aws/pulls).

## Future Work

* Automated testing
* Makefile for AWS Lambda .zip bundle
* Set arbitrary CloudFormation stack parameters to arbitrary values
  (variable sched-set-_Parameter_-_value_ tag key)

## Dedication

This work is dedicated to ej Salazar, Marianne and R&eacute;gis Marcelin,
and also to the wonderful colleagues I've worked with over the years.

## Licenses

|Scope|Link|Included Copy|
|--|--|--|
|Source code files, and source code embedded in documentation files|[GNU General Public License (GPL) 3.0](http://www.gnu.org/licenses/gpl-3.0.html)|[LICENSE-CODE.md](/LICENSE-CODE.md)|
|Documentation files (including this readme file)|[GNU Free Documentation License (FDL) 1.3](http://www.gnu.org/licenses/fdl-1.3.html)|[LICENSE-DOC.md](/LICENSE-DOC.md)|

Copyright Paul Marcelin

Contact: `marcelin` at `cmu.edu` (replace at with `@`)
