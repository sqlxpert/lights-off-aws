# Lights Off!

For AWS users who forget to turn off the lights:

* **Cut AWS costs up to ⅔ in your sleep**, by tagging your EC2 instances and
  RDS databases with cron-style schedules. Lights Off stops or hibernates
  the instances, and stops the databases, while you are not using them, then
  restarts them before you need them again. It's perfect for development and
  test systems, which are idle at night and on weekends.

* You can also tag EC2 instances, EBS volumes, and RDS databases to schedule
  backups.

* Tag your custom CloudFormation stacks, and Lights Out can delete and
  recreate expensive resources on a schedule. It takes only a few minutes to
  make your custom template compatible.

Jump to:
[Installation](#quick-start) &bull;
[Operations](#tag-keys-operations) &bull;
[Schedules](#tag-values-schedules) &bull;
[Security](#security-model) &bull;
[Multi-region/multi-account](#advanced-installation) &bull;
[CloudFormation Operations](#lightsout-cloudformation-operations)

## Comparison with AWS Services

AWS introduced AWS Backup, Data Lifecycle Manager, and Systems Manager after
mid-2017, when I started this project, originally called TagSchedOps. The
three relevant AWS services have become more capable over the years, but
Lights Out still has advantages:

* Schedules and operations are immediately visible, in tags on the EC2 instance,
  EBS volume, RDS datase, or CloudFormation stack. You don't need to look up
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
   Create a bucket for AWS Lambda function source code.

   * `my-bucket-us-east-1` , replacing my-bucket with the name of your choice,
     and us-east-1 with the region in which your EC2 instance is located. Be
     sure to create the bucket in that region.

   _Security Tip:_ Block public access to the bucket, and limit write access

4. Upload
   [lights_off_aws.py.zip](https://github.com/sqlxpert/lights-off-aws/raw/main/lights_off_aws.py.zip)
   to the S3 bucket.

   _Security Tip:_ Compare the Etag reported by S3 with the file's checksum in
   [lights_off_aws.py.zip.md5.txt](lights_off_aws.py.zip.md5.txt)

5. Go to the
   [CloudFormation Console](https://console.aws.amazon.com/cloudformation/home).
   Click Create Stack. Click Choose File, immediately below Upload a template
   to Amazon S3, and navigate to your local copy of
   [cloudformation/lights_off_aws.yaml](https://github.com/sqlxpert/lights-off-aws/raw/main/cloudformation/lights_off_aws.yaml)
   . On the next page, set:

   * Stack name: `LightsOff`
   * Lambda code S3 bucket: Name of your bucket, not including the region. For
     example, if your bucket is my-bucket-us-east-1 , set this to `my-bucket` .

6. After 20 minutes, check
   [images](https://console.aws.amazon.com/ec2/v2/home#Images:sort=desc:creationDate).

7. Before deregistering (deleting) the sample image that was created, note its
   ID, so that you delete the underlying
   [EBS volume snapshots](https://console.aws.amazon.com/ec2/v2/home#Snapshots:sort=desc:startTime).
   Also remember to delete the `sched-backup` tag from your EC2 instance.

## Tag Keys (Operations)

||Start or Stop|Hibernate|Back Up|Reboot then Back Up|Reboot|Reboot then Fail Over|Update Stack Parameter|
|--|--|--|--|--|--|--|--|
||`sched-start`|`sched-hibernate`|`sched-backup`|`sched-reboot-backup`|`sched-reboot`|`sched-reboot-failover`|`sched-set-Enable-true`|
||`sched-stop`||||||`sched-set-Enable-false`|
|[EC2 instance](https://console.aws.amazon.com/ec2/v2/home#Instances)|&check;|&check;|image (AMI)|image (AMI)|&check;|||
|[EBS volume](https://console.aws.amazon.com/ec2/v2/home#Volumes)|||volume snapshot|||||
|[RDS database instance](https://console.aws.amazon.com/rds/home#databases:)|&check;||database snapshot||&check;|&check;||
|[RDS database cluster](https://console.aws.amazon.com/rds/home#databases:)|&check;||database cluster snapshot||&check;||
|[CloudFormation stack](https://console.aws.amazon.com/cloudformation/home#/stacks)|||||||&check;|

* Not all EC2 instances support hibernation.
* Not all RDS database clusters support reboot.

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
  |`d=_ H:M=14:20`|Once a day|14:20 every day|
  |`uTH:M=1T14:20`|Once a week|14:20 every Monday|
  |`dTH:M=28T14:20`|Once a month|14:20 the 28th day of every month|
  |`d=01 d=15 H=03 H=19 M=00`|cron-style|03:00 and 19:00 the 1st and 15th days of every month|
  |`d=_ H:M=08:50 H=_ M=10 M=40`|Extra daily operation|10 and 40 minutes after the hour, every hour of every day, _plus_ 08:50 every day|
  |`uTH:M=2T03:30 uTH:M=5T07:20 d=_ H=11 M=00`|2 extra weekly operations|11:00 every day, _plus_  03:30 every Tuesday and 07:20 every Friday|
  |`dTH:M=00T05:20 u=3 H=22 M=10`|Extra monthly operation|22:10 every Wednesday, _plus_ 05:20 the 1st day of every month|

* Time zone: always UTC
* Clock: 24-hour
* Last digit of minute: always 0
* Approximate time: Operations happen during a 10-minute cycle. 14:20 means
  _after 14:20 but before 14:30_, for example.)
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
  [`strftime()`](http://manpages.ubuntu.com/manpages/xenial/man3/strftime.3.html)
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
  to child. You can change the `CopyTags` parameter of your LightsOut
  CloudFormation stack to prevent this, for example, if your organization has
  different tagging rules for EC2 instances and images.

## Logging

* After logging in to the [AWS Web Console](https://signin.aws.amazon.com/console),
  check the
  [LightsOff CloudWatch log groups](https://console.aws.amazon.com/cloudwatch/home#logs:prefix=/aws/lambda/LightsOff-).
* Log messages (except for uncaught exceptions) are JSON objects, with a
  `Type` key to classify the message and indicate which other keys will be
  present.
* You can change the `LogLevel` parameter of your LightsOut CloudFormation
  stack to see more messages.

## On/Off Switch

* You can change the `Enable` parameter of your LightsOut CloudFormation
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
  prompt backup creation) to delete backups.

* Note these AWS security gaps:

  * Authority to create an EC2 instance image includes authority to reboot.
    (Explicitly denying the reboot privilege does not help.) A harmless
    privilege, taking a backup, is married with a risky one, rebooting.

  * In RDS, permission to add a specific tag also includes permission to add
    _any other_ tags in the same API call!

## Advanced Installation

Before starting a multi-region and/or multi-account installation, delete the
ordinary LightsOff CloudFormation stack in all regions, in all AWS accounts.

### Multi-Region Configuration

(Under review)

If you intend to install LightsOff in multiple regions,

1. Create S3 buckets in all [regions](http://docs.aws.amazon.com/general/latest/gr/rande.html#s3_region) where you intend to install LightsOff. The bucket names must all share the same prefix, which will be followed by a region suffix (e.g. `-us-east-1`). The region in which each bucket is created _must_ match the suffix at the end of the bucket's name.

2. Upload [lights_off_aws_perform.py.zip](https://github.com/sqlxpert/lights-off-aws/raw/main/lights_off_aws_perform.py.zip) to each bucket. The need for copies in multiple regions is an AWS Lambda limitation.

3. Keep the following rules in mind when setting parameters, later:

   |Section|Parameter|Value|
   |--|--|--|
   |Basics|Lambda code S3 bucket|_Use the shared prefix; for example, if you created_ my-bucket-us-east-1 _and_ my-bucket-us-west-2 _, use_ `my-bucket`|

### Multi-Account Configuration

(Under review)

If you intend to install LightsOff in multiple AWS accounts,

1. In every target AWS account, create the [pre-requisite stack](https://github.com/sqlxpert/lights-off-aws/raw/main/cloudformation/lights_off_aws-prereq.yaml). Set:

   |Item|Value|
   |--|--|
   |Stack name|`LightsOffPrereq`|
   |AWSCloudFormationStackSet*Exec*utionRoleStatus|_Choose carefully!_|
   |AdministratorAccountId|AWS account number of main (or only) account; leave blank if AWSCloudFormationStackSet*Exec*utionRole existed before this stack was created|
   |LambdaCodeS3Bucket|Name of AWS Lambda function source code bucket (shared prefix, in a multi-region scenario)|

2. For the AWS Lambda function source code S3 bucket in *each region*, create a
bucket policy allowing access by *every target AWS account*'s
AWSCloudFormationStackSetExecutionRole (StackSet installation) or
LightsOffCloudFormation role (manual installation with ordinary CloudFormation).
The full name of the LightsOffCloudFormation role will vary; for every target
AWS account, look up the random suffix in [IAM roles](https://console.aws.amazon.com/iam/home#/roles),
or by selecting the LightsOffInstall stack in
[CloudFormation stacks](https://us-east-2.console.aws.amazon.com/cloudformation/home#/stacks)
and drilling down to Resources. S3 bucket policy template:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Principal": {
           "AWS": [
             "arn:aws:iam::TARGET_AWS_ACCOUNT_NUMBER_1:role/AWSCloudFormationStackSetExecutionRole",
             "arn:aws:iam::TARGET_AWS_ACCOUNT_NUMBER_1:role/LightsOffInstall-LightsOffCloudFormation-RANDOM_SUFFIX_1",

             "arn:aws:iam::TARGET_AWS_ACCOUNT_NUMBER_2:role/AWSCloudFormationStackSetExecutionRole",
             "arn:aws:iam::TARGET_AWS_ACCOUNT_NUMBER_2:role/LightsOffInstall-LightsOffCloudFormation-RANDOM_SUFFIX_2"
           ]
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

### CloudFormation Stack*Set* Installation

(Under review)

1. Follow the [multi-region steps](#multi-region-configuration), even for a multi-account, single-region scenario.

2. Follow the [multi-account steps](#multi-account-configuration). In a single-account, multi-region scenario, no S3 bucket policy is needed.

3. If [StackSets](http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-concepts.html) has never been used, create [AWSCloudFormationStackSet*Admin*istrationRole](https://s3.amazonaws.com/cloudformation-stackset-sample-templates-us-east-1/AWSCloudFormationStackSetAdministrationRole.yml). Do this one time, in your main (multi-account scenario) or only (single-account scenario) AWS account. There is no need to create AWSCloudFormationStackSet*Exec*utionRole using Amazon's template; the LightsOff*Install* stack provides it, when necessary.

4. In the AWS account with the AWSCloudFormationStackSet*Admin*istrationRole, go to the [StackSets Console](https://console.aws.amazon.com/cloudformation/stacksets/home#/stacksets).

5. Click Create StackSet, then select Upload a template to Amazon S3, then click Browse and select your local copy of [cloudformation/lights_off_aws.yaml](https://github.com/sqlxpert/lights-off-aws/raw/main/cloudformation/lights_off_aws.yaml) . On the next page, set:

   |Section|Item|Value|
   |--|--|--|
   ||StackSet name|`LightsOff`|
   |Basics|Lambda code S3 bucket|_Use the shared prefix; for example, if you created_ my-bucket-us-east-1 _, use use_ `my-bucket`|

6. On the next page, specify the target AWS accounts, typically by entering account numbers below Deploy stacks in accounts. Then, move the target region(s) from Available regions to Deployment order. It is a good idea to put the main region first.

## Software Updates

* When CloudFormation template changes are published, LightsOut-related stacks
  and stack sets can be updated in-place.

* When AWS Lambda function source code changes are published, it is easier to
  create a new stack such as `LightsOff02`, set the Enable parameter to
  `false` initially, delete the old stack, and then enable the new one.
  (CloudFormation otherwise has to be coaxed to recognize that the source
  source code, which is stored in S3, had changed.)

## LightsOut CloudFormation Operations

Using tags on custom CloudFormation stacks to schedule changes to a stack
parameter value is an advanced Lights Out feature.

A sample use case is toggling the deletion of an
`AWS::EC2::ClientVpnTargetNetworkAssociation` at the end of the work day
while leaving other AWS Client VPN resources intact. At 10¢ per association
per hour, this can save up to $650 per year. Temporarily restoring VPN access
during off-hours is as simple as performing a stack update, or adding the
next multiple of 10 minutes to the `sched-set-Enable-true` tag!

To make your custom CloudFormation template compatible with Lights Off,

1. Add the following to the `Parameters` section:

   ```yaml
     Enable:
       Type: String
       Description: >-
         Lights Off will automatically update this paramater to true or false on
         schedules in tags on this CloudFormation stack. See
         https://github.com/sqlxpert/lights-off-aws
       AllowedValues:
         - "false"
         - "true"
       Default: "false"  # Start with expensive resources off
   ```

2. Add the following to the `Conditions` section:

   ```yaml
     EnableTrue:
       !Equals [!Ref Enable, "true"]
   ```

3. Add the following below, and indented at the same level as, the `Type`
   attribute of the resource definition for any expensive resource that you
   would like Lights Off to create and delete on schedule:

   ```yaml
       Condition: EnableTrue
   ```

   You can also use the
   [`DependsOn` attribute](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-attribute-dependson.html)
   to toggle the creation and deletion of resources that are not formally
   related.

4. If necessary, make references to affected resources conditional, by
   replacing a property such as `SomeProperty: !Ref MyResourceName` with:

   ```yaml
         SomeProperty:
           Fn::If:
             - EnableTrue
             - !Ref MyResourceName
             - !Ref AWS::NoValue
   ```

5. Define a CloudFormation execution role that covers creating, updating and
   deleting all of the resources in your CloudFormation template. Specify the
   role when creating a stack from your template. (_Test_ the role by using it
   to update the stack manually.) Lights Out operates on a least-privilege
   principle. Unless CloudFormation can assume an execution role, and unless
   the role covers all of the AWS API actions needed to update the stack,
   Lights Out will not be able to update the stack.

6. Once all resource definitions and permissions are correct, Lights Out will
   update the stack according to schedules in the stack's
   `sched-set-Enable-true` and `sched-set-Enable-false` tags, preserving the
   previous template and the previous parameter values but setting the value of
   the `Enable` parameter to `true` or `false` each time.

## Parting Advice

* Test your backups! Can they be restored successfully?

* Rebooting EC2 instances is necessary for coherent file system backups, but
  it takes time and carries risks. Use `sched-reboot-backup` less frequently
  than `sched-backup` (no reboot).

* Be aware: of charges for running the AWS Lambda functions, queueing
  scheduled operations in SQS, logging to CloudWatch Logs, and storing images
  and snapshots; of the whole-hour cost when you stop an RDS database or an
  EC2 Windows or commercial Linux instance (but [other EC2 instances have a
  1-minute minimum](https://aws.amazon.com/blogs/aws/new-per-second-billing-for-ec2-instances-and-ebs-volumes/));
  of ongoing storage charges for stopped EC2 instances and RDS databases; and
  of charges that resume when AWS automatically starts an RDS database that
  has been stopped for 7 days. Other AWS charges may apply!

* Test the AWS Lambda functions, SQS queue and IAM policies in your own AWS
  environment. To help improve Lights Off, please submit
  [bug reports and feature requests](https://github.com/sqlxpert/lights-off-aws/issues),
  as well as [proposed changes](https://github.com/sqlxpert/lights-off-aws/pulls).

## Future Work

* Automated testing
* Makefile

## Dedication

This work is dedicated to ej Salazar, Marianne and R&eacute;gis Marcelin,
and also to the wonderful colleagues I've worked with over the years.

## Licensing

|Scope|Link|Included Copy|
|--|--|--|
|Source code files, and source code embedded in documentation files|[GNU General Public License (GPL) 3.0](http://www.gnu.org/licenses/gpl-3.0.html)|[LICENSE-CODE.md](https://github.com/sqlxpert/lights-off-aws/raw/main/LICENSE-CODE.md)|
|Documentation files (including this readme file)|[GNU Free Documentation License (FDL) 1.3](http://www.gnu.org/licenses/fdl-1.3.html)|[LICENSE-DOC.md](https://github.com/sqlxpert/lights-off-aws/raw/main/LICENSE-DOC.md)|

Copyright Paul Marcelin

Contact: `marcelin` at `cmu.edu` (replace at with `@`)
