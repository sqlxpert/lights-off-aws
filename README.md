# Lights Off AWS

For AWS users who forget to turn off the lights: Tag instances, volumes,
databases, and database clusters with days and times when you want them
stopped, started, and backed up. Now, you can also tag stacks to delete
expensive AWS infrastructure when it's not needed!

## Benefits

* **Save money** by stopping EC2 instances and RDS databases during off-hours
* Take back ups **more often**
* Put schedules in **tags**, right on your resources
* Install easily in multiple regions and accounts

Jump to:
[Installation](#quick-start) &bull;
[Schedule Tags](#scheduling-operations) &bull;
[Logging](#output) &bull;
[Security](#security-model) &bull;
[Multi-region/multi-account](#advanced-installation)

## Comparison with AWS Services

Lights Off has a few advantages over AWS Backup, Amazon Data Lifecycle Manager,
and AWS Systems Manager:

* Cron-style tags on the instance, volume, database, or database cluster show
  when it will be backed up. You don't have to look up a backup schedule in
  AWS Backup.

* Tag keys on the instance, volume, database, or database cluster show what
  operation will be done. You don't have to look up a "document" in AWS
  Systems Manager.

* One tool handles instance, database and database cluster starts, stops,
  reboots and backups.

## Quick Start

1. Log in to the [AWS Web Console](https://signin.aws.amazon.com/console).

2. Go to the [list of EC2 instances](https://console.aws.amazon.com/ec2/v2/home#Instances).
   Add the following tags to an instance:

  |Key|Value|Note|
  |--|--|--|
  |<kbd>sched-backup</kbd>|<kbd>d=\_&nbsp;H:M=11:30</kbd>|Replace 11:30 with [current UTC time](https://www.timeanddate.com/worldclock/timezone/utc) + 20 minutes|

3. Go to the
   [S3 Console](https://console.aws.amazon.com/s3/home).
   Create a bucket for AWS Lambda function source code. It must be in the region
   where you want to install Lights Off and you must put a hyphen and the region
   at the end of the bucket name (for example,
   <kbd>my-bucket-us-east-1</kbd>). Upload
   [<samp>aws-lambda/lights_off_aws.py.zip</samp>](https://github.com/sqlxpert/lights-off-aws/raw/main/aws-lambda/lights_off_aws.py.zip)

  _Security Tip:_ [Block public access](https://docs.aws.amazon.com/AmazonS3/latest/dev/access-control-block-public-access.html#console-block-public-access-options)
  to the bucket, and limit write access

  _Security Tip:_ For the Lambda ZIP file, compare the <samp>Etag</samp>
  reported by S3 with the checksum in
  [<samp>aws-lambda/lights_off_aws.py.zip.md5.txt</samp>](aws-lambda/lights_off_aws.py.zip.md5.txt)

4. Go to the
   [CloudFormation Console](https://console.aws.amazon.com/cloudformation/home).
   Click <samp>Create Stack</samp>. Click <samp>Choose File</samp>,
   immediately below <samp>Upload a template to Amazon S3</samp>, and navigate
   to your local copy of
   [<samp>cloudformation/lights_off_aws.yaml</samp>](https://github.com/sqlxpert/lights-off-aws/raw/main/cloudformation/lights_off_aws.yaml).
   On the next page, set:

  |Section|Item|Value|
  |--|--|--|
  ||Stack name|<kbd>LightsOff</kbd>|
  |Basics|Lambda code S3 bucket|Name of your S3 bucket|

  For all other parameters, keep the default values.

5. After 20 minutes, check the [list of images](https://console.aws.amazon.com/ec2/v2/home#Images:sort=desc:creationDate).

6. Before deregistering (deleting) the sample image, note its ID, so that
   you can delete the associated
   [EBS snapshots](https://console.aws.amazon.com/ec2/v2/home#Snapshots:sort=desc:startTime).
   Also remove the tag from the instance.

## Warnings

* Test your backups! Can they be restored successfully?

* Rebooting EC2 instances is necessary for a coherent backup, but rebooting
  has drawbacks. Weigh the benefits against the risks.

* Be aware of AWS charges for running the AWS Lambda functions, queueing
  operations in SQS, logging to CloudWatch Logs, and storing images and
  snapshots; of the whole-hour cost when you stop an RDS, EC2 Windows, or EC2
  commercial Linux instance (but [other EC2 instances have a 1-minute minimum
  charge](https://aws.amazon.com/blogs/aws/new-per-second-billing-for-ec2-instances-and-ebs-volumes/));
  of the ongoing cost of storage for stopped instances; and costs that resume
  when AWS automatically starts an RDS instance that has been stopped for too
  many days. There could be other AWS charges as well!

* Test the AWS Lambda functions and IAM policies in your own AWS environment.
  To help improve Lights Off, please submit
  [bug reports and feature requests](https://github.com/sqlxpert/lights-off-aws/issues),
  as well as [proposed changes](https://github.com/sqlxpert/lights-off-aws/pulls).

## Enabling Operations

| |Start|Create Image|Reboot then Create Image|Reboot then Fail Over|Reboot|Create Snapshot|Stop|
|--|--|--|--|--|--|--|--|--|
|_Enabling&nbsp;Tag_&nbsp;&rarr;|<kbd>sched-start</kbd>|<kbd>sched-backup</kbd>|<kbd>sched-reboot-backup</kbd>|<kbd>sched-reboot-failover</kbd>|<kbd>sched-reboot</kbd>|<kbd>sched-backup</kbd>|<kbd>sched-stop</kbd>|
|[EC2&nbsp;instance](https://console.aws.amazon.com/ec2/v2/home#Instances)|&check;|&check;|&check;||&check;|&check;|
|[EBS&nbsp;volume](https://console.aws.amazon.com/ec2/v2/home#Volumes)||||||&check;|||
|[RDS&nbsp;database](https://console.aws.amazon.com/rds/home#dbinstances:)|&check;|||&check;|&check;|&check;|&check;|
|[RDS&nbsp;database&nbsp;cluster](https://console.aws.amazon.com/rds/home#dbinstances:)|&check;|||&check;|&check;|&check;|&check;|

## Scheduling

* All times are UTC, on a 24-hour clock.
* The "Find" AWS Lambda function runs once every 10 minutes. The last digit of
  the minute must be zero. For example, <kbd>M=40</kbd> means _one time,
  between 40 and 50 minutes after the hour_.
* Month and minute values must have two digits. Use a leading zero if
  necessary. (Weekday numbers have only one digit, of course.)
* Separate schedule components with a space (<kbd>&nbsp;</kbd>), which was
  chosen because RDS does not allow commas in tag values.
* Order matters: weekday or day of month must be specified before time, and
  hour must be specified before minute.
* <kbd>T</kbd> separates a weekday or day of month from time.

* Values: one or more components:

  |Name|Minimum|Maximum|Wildcard|
  |--|--|--|--|
  |Day of month|<kbd>d=01</kbd>|<kbd>d=31</kbd>|<kbd>d=\_</kbd>|
  |Weekday|<kbd>u=1</kbd> (Monday)|<kbd>u=7</kbd> (Sunday)||
  |Hour|<kbd>H=00</kbd>|<kbd>H=23</kbd>|<kbd>H=\_</kbd>|
  |Minute|<kbd>M=00</kbd>|<kbd>M=59</kbd>||
  |Hour and minute|<kbd>H:M=00:00</kbd>|<kbd>H:M=23:59</kbd>||
  |Day of month, hour and minute|<kbd>dTH:M=01T00:00</kbd>|<kbd>dTH:M=31T23:59</kbd>||
  |Weekday, hour and minute|<kbd>uTH:M=1T00:00</kbd>|<kbd>uTH:M=7T23:59</kbd>||

  * Day, hour and minute must _all_ be specified in the tag value.
  * To specify multiple values, repeat a component. For example, <kbd>d=01&nbsp;d=11&nbsp;d=21</kbd> means _the 1st, 11th and 21st days of the month_.
  * Wildcards: <kbd>d=\_</kbd> means _every day of the month_ and <kbd>H=\_</kbd>, _every hour of the day_.
  * For consistent one-day-a-month scheduling, avoid <kbd>d=29</kbd> through <kbd>d=31</kbd>.
  * The letters match [<code>strftime</code>](http://manpages.ubuntu.com/manpages/xenial/man3/strftime.3.html) and the weekday numbers are [ISO 8601-standard](https://en.wikipedia.org/wiki/ISO_8601#Week_dates) (differs from cron).

* Examples:

  |Schedule Tag Value|Demonstrates|Timing|
  |--|--|--|
  |<samp>d=\_&nbsp;H:M=14:25</samp>|Once-a-day event|Between 14:20 and 14:30, every day|
  |<samp>uTH:M=1T14:25</samp>|Once-a-week event|Between 14:20 and 14:30, every Monday.|
  |<samp>dTH:M=28T14:25</samp>|Once-a-month event|Between 14:20 and 14:30 on the 28th day of every month|
  |<samp>d=1&nbsp;d=8&nbsp;d=15&nbsp;d=22&nbsp;H=03&nbsp;H=19&nbsp;M=01</samp>|cron schedule|Between 03:00 and 03:10 and again between 19:00 and 19:10, on the 1st, 8th, 15th, and 22nd days of every month|
  |<samp>d=\_&nbsp;H=\_&nbsp;M=15&nbsp;M=45&nbsp;H:M=08:50</samp>|Extra daily event|Between 10 and 20 minutes after the hour and 40 to 50 minutes after the hour, every hour of every day, _and also_ every day between 08:50 and 09:00|
  |<samp>d=\_&nbsp;H=11&nbsp;M=00&nbsp;uTH:M=2T03:30&nbsp;uTH:M=5T07:20</samp>|Two extra weekly events|Between 11:00 and 11:10 every day, _and also_ every Tuesday between 03:30 and 03:40 and every Friday between 07:20 and 7:30|
  |<samp>u=3&nbsp;H=22&nbsp;M=15&nbsp;dTH:M=01T05:20</samp>|Extra monthly event|Between 22:10 and 22:20 every Wednesday, _and also_ on the first day of every month between 05:20 and 05:30|

## Output

* After logging in to the [AWS Web Console](https://signin.aws.amazon.com/console),
* check the
  [LightsOff CloudWatch log groups](https://console.aws.amazon.com/cloudwatch/home#logs:prefix=/aws/lambda/LightsOff-).
* Log messages (except for uncaught exceptions) are JSON objects, with a Type
  key to summarize the message and indicate which other keys will be present.
* You can change the LogLevel parameter in CloudFormation.

## On/Off Switch

* You can change the Enable parameter in CloudFormation.
* This switch is per-region and per-AWS-account.
* While Enable is false, scheduled operations do not occur; they are skipped
  permanently.

## Child Resources

Some operations create a child resource (image or snapshot) from a parent
resource (instance, volume, database, or cluster).

### Naming

* The name of the child consists of these parts, separated by hyphens (<samp>-</samp>):

  |#|Part|Example|Purpose|
  |--|--|--|--|
  |1|Prefix|<samp>zsched</samp>|Identifies and groups resources created by LightsOff<samp>z</samp> will sort after most manually-created images and snapshots.|
  |2|Parent name or identifier|<samp>webserver</samp>|Conveniently indicates the parent. Derived from the <samp>Name</samp> tag, the logical name, or the physical identifier. Multiple children of the same parent will sort together, by creation date.|
  |3|Date/time|<samp>20171231T1400Z</samp>|Indicates when the child was created. The time zone is always UTC (<samp>Z</samp>). The last digit of the minute is always 0.|
  |4|Random string|<samp>g3a8a</samp>|Guarantees unique names. Five characters are chosen from a small set of unambiguous letters and numbers.|

* If parsing is ever necessary, keep in mind that the parent name or identifiere
  may contain additional, internal hyphens.
* Characters forbidden by AWS are replaced with <samp>X</samp>.
* For some resource types, the description is also set to the name, in case the
  Console shows only one or the other.

### Special Tags

* Special tags are added to the child:

  |Tag(s)|Purpose|
  |--|--|
  |<samp>Name</samp>|Supplements EC2 resource identifier. The tag key is renamed <samp>sched-parent-name</samp> when the value is passed from parent to child, because the child has a <samp>Name</samp> tag of its own. In the EC2 Console, the Name column is determined from Name tags.|
  |<samp>sched-parent-name</samp>|The <samp>Name</samp> tag value from the parent. May be blank.|
  |<samp>sched-parent-id</samp>|The identifier of the parent instance, volume, database or database cluster.|
  |<samp>sched-op</samp>|The operation (for example, <samp>sched-backup</samp>) that created the child. Distinguishes special cases, such as whether an EC2 instance was rebooted before an image was created (<samp>sched-reboot-backup</samp>).|
  |<a name="tag-sched-date-time"><samp>sched-cycle-start</samp></a>|Groups resources created during the same 10-minute cycle. The last digit of the minute is always zero, and the time zone is always UTC (<samp>Z</samp>.|

* Although AWS stores most of this information as resource properties/metadata, the field names/keys vary from service to service. Searching by tag works in both EC2 and RDS.

* User-created tags whose keys don't begin with <samp>sched</samp> are copied from parent to child. You can change the CopyTags parameter in CloudFormation if you do not want this behavior.

## One Scheduled Operation at a Time

* If two or more operations on the same resource are scheduled for the same
  10-minute cycle, none of operations is performed. An error is logged.

## Security Model

* Allow only a few trusted users to tag EC2 and RDS resources. You can
  restrict access to <samp>sched-</samp> tags, specifically.

* Do not allow a role that can create backups to delete backups.

* Choose from sample IAM policies:

  * LightsOffTag
  * LightsOffNoTag

* Sometimes, you must add, change or delete one tag at a time.

* Although the LightsOffTag policy is sufficient for tagging via the AWS API,
  users who are not AWS administrators will need additional privileges to use
  the Console. Examples:

  * [AmazonEC2ReadOnlyAccess](https://console.aws.amazon.com/iam/home#policies/arn:aws:iam::aws:policy/AmazonEC2ReadOnlyAccess)
  * [AmazonRDSReadOnlyAccess](https://console.aws.amazon.com/iam/home#policies/arn:aws:iam::aws:policy/AmazonRDSReadOnlyAccess)
  * [AWSCloudFormationReadOnlyAccess](https://us-east-1.console.aws.amazon.com/iam/home#/policies/arn:aws:iam::aws:policy/AWSCloudFormationReadOnlyAccess)

* You may have to [decode authorization errors](http://docs.aws.amazon.com/cli/latest/reference/sts/decode-authorization-message.html).
  The LightsOffTag grants the necessary privilege.

* Note these AWS security limitations:

  * Authority to create an EC2 instance image includes authority to reboot
    (Explicitly denying the reboot privilege does not help.) A harmless
    privilege, taking a backup, is married with a risky one, rebooting.

  * In RDS, an IAM user or role that can add specific tags can add _any other_
    tags at the same time. The provided policies prevent this with
    <code>Deny</code> statements, which unfortunately block legitimate RDS
    database and/or snapshot tagging privileges, if you have granted any.

## Advanced Installation

Before starting a multi-region and/or multi-account installation, delete the
ordinary LightsOff CloudFormation stack in all regions, in all AWS accounts.

### Multi-Region Configuration

If you intend to install LightsOff in multiple regions,

1. Create S3 buckets in all [regions](http://docs.aws.amazon.com/general/latest/gr/rande.html#s3_region) where you intend to install LightsOff. The bucket names must all share the same prefix, which will be followed by a region suffix (e.g. <kbd>-us-east-1</kbd>). The region in which each bucket is created _must_ match the suffix at the end of the bucket's name.

2. Upload [<samp>aws-lambda/lights_off_aws_perform.py.zip</samp>](https://github.com/sqlxpert/lights-off-aws/raw/main/aws-lambda/lights_off_aws_perform.py.zip) to each bucket. The need for copies in multiple regions is an AWS Lambda limitation.

3. Keep the following rules in mind when setting parameters, later:

   |Section|Parameter|Value|
   |--|--|--|
   |Basics|Lambda code S3 bucket|_Use the shared prefix; for example, if you created_ <samp>my-bucket-us-east-1</samp> _and_ <samp>my-bucket-us-west-2</samp> _, use_ <kbd>my-bucket</kbd>|

### Multi-Account Configuration

If you intend to install LightsOff in multiple AWS accounts,

1. In every target AWS account, create the [pre-requisite stack](https://github.com/sqlxpert/lights-off-aws/raw/main/cloudformation/lights_off_aws-prereq.yaml). Set:

   |Item|Value|
   |--|--|
   |Stack name|<kbd>LightsOffPrereq</kbd>|
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
and drilling down to <samp>Resources</samp>. S3 bucket policy template:

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

5. Click <samp>Create StackSet</samp>, then select <samp>Upload a template to Amazon S3</samp>, then click <samp>Browse</samp> and select your local copy of [<samp>cloudformation/lights_off_aws.yaml</samp>](https://github.com/sqlxpert/lights-off-aws/raw/main/cloudformation/lights_off_aws.yaml) . On the next page, set:

   |Section|Item|Value|
   |--|--|--|
   ||StackSet name|<kbd>LightsOff</kbd>|
   |Basics|Lambda code S3 bucket|_Use the shared prefix; for example, if you created_ <samp>my-bucket-us-east-1</samp> _, use use_ <kbd>my-bucket</kbd>|

6. On the next page, specify the target AWS accounts, typically by entering account numbers below <samp>Deploy stacks in accounts</samp>. Then, move the target region(s) from <samp>Available regions</samp> to <samp>Deployment order</samp>. It is a good idea to put the main region first.

## Software Updates

New versions of AWS Lambda function source code and CloudFormation templates
will be released from time to time. Because CloudFormation does not detect
changes in AWS Lambda function source code stored in ZIP files in S3, the
easiest way to update is to create a new stack such as <kbd>LightsOff02</kbd>,
set Enable to false initially, delete the old stack, and the enable the new one.

### CloudFormation Stack*Set* Update

(Under review)

Differences when updating a StackSet instead of an ordinary stack:

 * Click the radio button to the left of LightsOff, in the [list of StackSets](https://console.aws.amazon.com/cloudformation/stacksets/home#/stacksets). From the <samp>Actions</samp> pop-up menu next to the blue <samp>Create StackSet</samp> button, select <samp>Manage stacks in StackSet</samp>. Then, select <samp>Edit stacks</samp>. On the next page, select <samp>Upload a template to Amazon S3</samp> and upload the latest version of [<samp>cloudformation/lights_off_aws.yaml</samp>](https://github.com/sqlxpert/lights-off-aws/raw/main/cloudformation/lights_off_aws.yaml).

 * A single update covers all target regions and/or AWS target accounts.

 * The S3 Version ID parameters must remain blank. So that CloudFormation will recognize new source code for the AWS Lambda functions, rename each ZIP file. (For example, change <samp>aws_tag_sched_ops_perform.py.zip</samp> to <samp>aws_tag_sched_ops_perform_20170924.py.zip</samp>.) Change the <samp>S3 object name</samp> parameters accordingly.

 * Change Sets are not supported. StackSets provides no preliminary feedback about the scope of changes.

## Future Work

* Automated testing, consisting of a CloudFormation template to create sample
  AWS resources, and a program (perhaps another AWS Lambda function!) to check
  whether the intended operations were performed.

* Makefile

## Dedication

This work is dedicated to [ej Salazar], Marianne and R&eacute;gis Marcelin,
and the wonderful people I've worked with over the years.

## Licensing

|Scope|License|Copy Included|
|--|--|--|
|Source code files|[GNU General Public License (GPL) 3.0](http://www.gnu.org/licenses/gpl-3.0.html)|[LICENSE-CODE.md](https://github.com/sqlxpert/lights-off-aws/raw/main/LICENSE-CODE.md)|
|Source code within documentation files|[GNU General Public License (GPL) 3.0](http://www.gnu.org/licenses/gpl-3.0.html)[LICENSE-CODE.md](https://github.com/sqlxpert/lights-off-aws/raw/main/LICENSE-CODE.md)|
|Documentation files (including this readme file)|[GNU Free Documentation License (FDL) 1.3](http://www.gnu.org/licenses/fdl-1.3.html)|[LICENSE-DOC.md](https://github.com/sqlxpert/lights-off-aws/raw/main/LICENSE-DOC.md)|

Copyright 2022, Paul Marcelin

Contact: <kbd>marcelin</kbd> at <kbd>cmu.edu</kbd> (replace at with <kbd>@</kbd>)
