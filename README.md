# Lights Off!

For people who forget to turn the lights off:

* **Cut AWS costs up to 66%** by tagging EC2 instances and RDS databases with
  cron-style stop/start schedules &mdash; perfect for development and test
  systems that sit idle overnight.

* Tag EC2 instances, EBS volumes, and RDS databases to schedule backups.

* Tag your own CloudFormation stacks, and Lights Off can delete/recreate the
  expensive components on schedule.

Jump to:
[Quick Install](#quick-start) &bull;
[Tags](#tag-keys-operations) &bull;
[Schedules](#tag-values-schedules) &bull;
[Security](#security) &bull;
[Multi-Region/Multi-Account](#advanced-installation) &bull;
[Advice](#parting-advice)

## Unique Advantages

This project, originally TagSchedOps, began before AWS Backup, Data
Lifecycle Manager, or Systems Manager existed. It still has advantages:

* Straightforward: Schedules and operations are directly visible in tags on
  the EC2 instance, EBS volume, RDS database, or CloudFormation stack. You
  don't have to look up schedules and rules in other AWS services.

* Flexible: Need to change a schedule? Just edit a tag!

* Uniform: The same system handles various EC2, RDS and CloudFormation
  operations. Why should you have to use one AWS service to schedule a backup,
  and another to schedule a reboot?

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
     my-bucket-us-east-1, enter `my-bucket`.

6. After about 20 minutes, check
   [images (AMIs)](https://console.aws.amazon.com/ec2/v2/home#Images:sort=desc:creationDate).

7. Before deregistering (deleting) the image that was created, note its ID
   (`ami-`) so that you delete the underlying
   [EBS snapshots](https://console.aws.amazon.com/ec2/v2/home#Snapshots:visibility=owned-by-me;v=3;tag:Name=:zsched-;sort=desc:startTime).
   Remember to delete the `sched-backup` tag from your EC2 instance.

## Tag Keys (Operations)

||`sched‑stop` `sched‑start`|`sched‑hibernate` `sched‑start`|`sched‑backup`|`sched‑reboot‑backup`|`sched‑reboot`|`sched‑reboot‑failover`|`sched‑set‑Enable‑false` `sched‑set‑Enable‑true`|
|--|--|--|--|--|--|--|--|
|[EC2 instance](https://console.aws.amazon.com/ec2/v2/home#Instances)|&check;|&check;|image (AMI)|image (AMI)|&check;|||
|[EBS volume](https://console.aws.amazon.com/ec2/v2/home#Volumes)|||snapshot|||||
|[RDS database instance](https://console.aws.amazon.com/rds/home#databases:)|&check;||database snapshot||&check;|&check;||
|[RDS database cluster](https://console.aws.amazon.com/rds/home#databases:)|&check;||cluster snapshot||&check;||
|[CloudFormation stack](https://console.aws.amazon.com/cloudformation/home#/stacks)|||||||&check;|

* Do not copy and paste tag keys from the table to AWS; the table uses
  non-breaking (non-ASCII) hyphens for formatting purposes.
* Not all EC2 instances support hibernation.
* Not all RDS database clusters support cluster-level reboot.
* If an AWS resource is tagged for multiple operations at the same time, an
  error will be logged.

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

* UTC time zone on a 24-hour clock
* Days before times, and hours before minutes (For fast matching, compound
  weekly and monthly terms should go first.)
* The day, the hour and the minute must all be specified in some way
* Consider `dTH:M=01T00:00` for end-of-month, because some months lack `d=29`
  through `d=31`

### Rationale

* Separator and wildcard: [RDS does not allow , or \*](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_Tagging.html#Overview.Tagging)
* Letters:
  [`strftime()`](http://manpages.ubuntu.com/manpages/xenial/man3/strftime.3.html#description)

## Child Resources

Backup operations create a "child" resource (image or snapshot) from a
"parent" AWS resource (instance, volume or database).

### Name

|Part|Example|Purpose|
|--|--|--|
|Prefix|`zsched`|Distinguishes backups created by Lights Off. `z` sorts after most manually-created images and snapshots.|
|Parent name or identifier|`webserver`|Meaningfully identifies the parent by `Name` tag value; otherwise, indicates the physical identifier. Groups backups of the same parent.|
|Date and time|`20171231T1400Z`|Groups backups scheduled for the same date and time. `Z` stands for UTC time.|
|Random suffix|`g3a8a`|Guarantees a unique name.|

* Parts are separated by hyphens (`-`).
* Parent name or identifier may contain additional, internal hyphens.
* Characters forbidden by AWS are replaced with `X` .

### Tags

|Tag|Description|
|--|--|
|`Name`|Name (as above)|
|`sched‑parent‑name`|Name of the parent (may be blank)|
|`sched‑parent‑id`|Physical identifier of the parent|
|`sched‑op`|Tag key that prompted the backup (`sched-reboot-backup` versus `sched-backup`, for example)|
|`sched‑cycle‑start`|Scheduled date and time of the backup|

* Although AWS stores most of this information as resource properties/metadata,
  the field names/keys vary by AWS service, as do the search capabilities
  &mdash; and some stored values, such as exact creation time, are too precise
  for grouping. Searching tags, on the other hand, works in both EC2 and RDS.

* User-created tags whose keys do not begin with `sched-` are copied from
  parent to child. You can change the `CopyTags` parameter of your Lights Off
  CloudFormation stack to prevent this.

## On/Off Switch

* You can change the `Enable` parameter of your Lights Off CloudFormation
  stack.
* While Enable is `false`, scheduled operations do not happen; they are
  skipped permanently and cannot be reprised.

## Logging

* Check the
  [`LightsOff` CloudWatch log groups](https://console.aws.amazon.com/cloudwatch/home#logsV2:log-groups$3FlogGroupNameFilter$3D$252Faws$252Flambda$252FLightsOff-).
* Log messages from Lights Off (except for uncaught exceptions) are JSON
  objects, with a `"type"` key to classify the message.
* You can change the `LogLevel` parameter of your Lights Off CloudFormation
  stack to see more messages.

## Security

_In accordance with the software license, nothing in this section creates a
warranty, an indemnification, an assumption of liability, etc. Use this
software entirely at your own risk. Lights Off is open-source, so you are
encouraged to read the code yourself and to evaluate its security._

### Lights Off Security Goals

* Distinct, least-privilege roles for the AWS Lambda function that finds
  matching AWS resources and the function that performs scheduled operations
  on them. The "Do" function is only authorized to perform a small set of
  operations, and at that, only when a resource has a `sched-` tag key that
  names the specific operation.

* A least-privilege queue policy for the queue linking the two functions. The
  operation queue can only consume messages from the "Find" function and
  produce messages for the "Do" function (or for a dead-letter queue, in the
  case of failed operations). Encryption in transit is required.

* Readable IAM policies, formatted as CloudFormation YAML rather than as JSON,
  and broken down into discrete statements by service, resource or principal.

* Optional encryption at rest with custom AWS Key Management System (KMS)
  keys, for queue message bodies (which contain the identifiers and tags of
  AWS resources) and for log entries.

* No data storage other than in queues and logs. Retention periods for
  the failed operation queue and the logs are configurable, and the fixed
  retention period for the operation queue is short.

* Basic safeguards against clock drift in distributed systems. The "Find"
  function starts 1 minute into the cycle and, beginning 9 minutes into the
  10-minute cycle, the "Do" function treats any further scheduled operation
  messages as expired.

* A checksum for the AWS Lambda function source code bundle. (The bundle is
  included for the benefit of new AWS Lambda users.)

* An optional, least-privilege CloudFormation service role for deployment.

### Security Steps You Can Take

* Only allow trusted people and trusted services to tag AWS resources. You
  can restrict the right to add, change and delete `sched-` tags by including
  the
  [`aws:TagKeys` condition key](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_tags.html#access_tags_control-tag-keys)
  in IAM policies and permission boundaries.

* Never let a role that can create backups (or, in this case, set tags to
  prompt backup creation) delete backups as well.

* Prevent people from modifying components of Lights Off, most of which can be
  identified by `LightsOff` in ARNs and in the automatic
  `aws:cloudformation:stack-name` tag. Limiting people's permissions so that
  the deployment role is _necessary_ for modifying Lights Off is ideal. Short
  of that, you could copy the deployment role's in-line IAM policy, delete the
  statements with `"Resource": "*"`, change the `"Effect"` of the remaining,
  resource-specific statements to `"Deny"`, and add the new, inverted policy
  to people's day-to-day roles.

* Add similar policies to prevent people from directly invoking the Lights Off
  AWS Lambda functions and from passing the roles defined for those functions
  to other, arbitrary functions.

* Log infrastructure changes using AWS CloudTrail, and set up alerts.

* Separate production workloads. You might decide not to deploy Lights Off to
  AWS accounts used for production, or you might customize the "Do" function's
  role, removing the authority to reboot and stop production resources (set
  the `AttachLocalPolicy` parameter of your Lights Off CloudFormation stack).

* Note these AWS limitations:

  * Permission to create an image includes permission to reboot the EC2
    instance at the same time. (Explicitly denying the reboot privilege does
    not help.)

  * Permission to add a specific RDS tag includes permission to add _any
    other_ tags at the same time.

## Advanced Installation

### Multi-Region

If you plan to deploy Lights Off to multiple regions, regardless of the
deployment method,

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
   Select Upload a template file, then click Choose file and navigate to your
   local copy of
   [lights_off_aws.yaml](/cloudformation/lights_off_aws.yaml)
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
to give CloudFormation only the privileges it needs to create a Lights Off
CloudFormation stack. First, create a CloudFormation stack named
`LightsOffPrereq` , from
[lights_off_aws_prereq.yaml](/cloudformation/lights_off_aws_prereq.yaml)
. Later, when you create a stack named `LightsOff` from
[lights_off_aws.yaml](/cloudformation/lights_off_aws.yaml) ,
scroll up to the Permissions section and set IAM role -
optional to `LightsOffPrereq-DeploymentRole` . If your own privileges are
limited, you might need explicit permission to pass the deployment role to
CloudFormation. See the `LightsOffPrereq-SampleDeploymentRolePassRolePol` IAM
policy for an example of the necessary statement.

The deployment role covers a single AWS account, but you can copy its in-line
IAM policy to the `AWSCloudFormationStackSetExecutionRole` in multiple target
accounts if you want to deploy a CloudFormation StackSet with
[self-managed permissions](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-prereqs-self-managed.html).

## Software Updates

* Update your Lights Off CloudFormation stack or StackSet in-place when the
  CloudFormation template changes.

* Create a new Lights Off CloudFormation stack or StackSet when the AWS Lambda
  function source code changes. Name it `LightsOff2` (for example), and set
  its `Enable` parameter to `false` at first. After you've deleted the
  original `LightsOff` stack or StackSet, update the new one, setting `Enable`
  to `true`. This simple blue/green deployment approach avoids the problem of
  getting CloudFormation to recognize that you have uploaded a new
  [lights_off_aws.py.zip](/lights_off_aws.py.zip)
  AWS Lambda function source code file to S3.

## Changing a CloudFormation Stack Parameter on Schedule

<details>
  <summary>View CloudFormation stack operation setup details</summary>

Using tags on your own CloudFormation stack to change a stack parameter on
schedule is an advanced Lights Off feature.

A sample use case is turning off an AWS Client VPN at the end of the day, when
no one else will be connecting. See
[10-minute AWS Client VPN](https://github.com/sqlxpert/10-minute-aws-client-vpn)
for potential savings of $600 per year.

To make your own CloudFormation template compatible with Lights Off, follow
the instructions in the sample template,
[lights_off_aws_cloudformation_ops_example.yaml](/cloudformation/lights_off_aws_cloudformation_ops_example.yaml)

Lights Off will update your own CloudFormation stack according to the schedules
in your own stack's `sched-set-Enable-true` and `sched-set-Enable-false` tags,
preserving the template and the parameter values but changing the value of
your own stack's `Enable` parameter to `true` or `false` each time. **E**nable
must be capitalized in the tag keys, just as it is in the parameter name.

</details>

## Extensibility

<details>
  <summary>View extensibility details</summary>

Lights Off takes advantage of patterns in boto3, the AWS software development
kit (SDK) for Python, and in the underlying AWS API. Adding more AWS services,
resource types, and operations is remarkably easy. For example, supporting RDS
_database clusters_ (individual RDS _database instances_ were already
supported) required the following additions:

```python
    AWSChildRsrcType(
      "rds",
      ("DB", "Cluster", "Snapshot"),
      "Identifier",
      name_chars_max=63,
      name_chars_unsafe_regexp=r"[^a-zA-Z0-9-]|--+",
      create_kwargs=lambda child_name, child_tags_list: {
        "DBClusterSnapshotIdentifier": child_name,
        "Tags": child_tags_list,
      },
    )

    AWSParentRsrcType(
      "rds",
      ("DB", "Cluster"),
      "Identifier",
      ops={
        ("start", ): {},
        ("stop", ): {},
        ("reboot", ): {},
        ("backup", ): {
          "child_rsrc_type":
            AWSChildRsrcType.members["rds"]["DBClusterSnapshot"],
        },
      },
    )
```

Most method names can be determined automatically, if you adopt the verb in
the method name as the verb in the tag key and break the resource type name
into words. For example, `start_db_cluster` as a method name follows from
`start` as the verb in the `sched-start` tag key and `DB` and `Cluster` as the
words in the resource type name.

When you include a "child" resource type in an operation definition, the verb
in the method name defaults to `create`, regardless of the verb that you
choose for the tag key, and the noun in the method name comes from the _child_
resource type. Accordingly, a `sched-backup` tag on an RDS database cluster
translates to a `create_db_cluster_snapshot` method call.

A Python dictionary for static parameters, and a reference to a Python
function for dynamic parameters, are optional. These were not needed in the
simple operation definitions shown above.

```yaml
          - Effect: Allow
            Action: rds:StartDBCluster
            Resource: !Sub "arn:${AWS::Partition}:rds:${AWS::Region}:${AWS::AccountId}:cluster:*"
            Condition:
              StringLike: { "aws:ResourceTag/sched-start": "*" }
```

Statements like the one shown above were added to the `RdsWrite` policy for
the Identity and Access Management (IAM) role used by the "Do" AWS Lambda
function, to authorize operations on RDS database clusters. The role used by
the "Find" function was also updated to authorize describing (listing) RDS
database clusters.

What capabilities would _you_ like to add to Lights Off?
</details>

## Parting Advice

* Routinely test your backups! Are backups happening as scheduled? Can you
  restore your backups successfully?

* Rebooting EC2 instances is necessary for coherent file system backups, but
  it takes time and carries risks. Use `sched-reboot-backup` less frequently
  than `sched-backup` .

* Be aware: of charges for running the Lights Off AWS Lambda functions,
  queueing scheduled operations in SQS, logging to CloudWatch Logs, and
  storing images and snapshots; of minimum billing increments when you stop an
  RDS database, or an EC2 instance with a commercial operating system license;
  of ongoing storage charges for stopped EC2 instances and RDS databases; and
  of charges that resume when RDS automatically restarts a database that has
  been stopped for 7 days. Other AWS charges may apply!

* Test the AWS Lambda functions, SQS queues, and IAM policies in your own AWS
  environment. To help improve Lights Off, please submit
  [bug reports and feature requests](https://github.com/sqlxpert/lights-off-aws/issues),
  as well as [proposed changes](https://github.com/sqlxpert/lights-off-aws/pulls).

## Future Work

* Automated testing
* Makefile for AWS Lambda .zip bundle
* Variable sched-set-_Parameter_-_value_ tag key to set an arbitrary
  CloudFormation stack parameter to an arbitrary value

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
