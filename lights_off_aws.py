#!/usr/bin/env python3
"""Start, reboot, stop and back up AWS resources using schedules in tags

github.com/sqlxpert/lights-off-aws  GPLv3  Copyright Paul Marcelin

Bundle for AWS Lambda:
  zip -9 lights_off_aws.py.zip lights_off_aws.py
  md5sum lights_off_aws.py.zip > lights_off_aws.py.zip.md5.txt
"""

import os
import logging
import datetime
import re
import json
import collections
import botocore
import boto3

logging.getLogger().setLevel(os.environ.get("LOG_LEVEL", logging.ERROR))

SCHED_DELIMS = r"\ +"  # Exposed space must be escaped for re.VERBOSE
SCHED_TERMS = rf"([^ ]+{SCHED_DELIMS})*"  # Unescaped space inside char class
SCHED_REGEXP_STRFTIME_FMT = rf"""
  (^|{SCHED_DELIMS})
  (
    # Specific monthly or weekly day and time, or...
    (dTH:M=%d|uTH:M=%u)T%H:%M
  |
    # Day wildcard, specific day, or specific weekday, any other terms, and...
    (d=(_|%d)|u=%u){SCHED_DELIMS}{SCHED_TERMS}
    (
      # Specific daily time, or...
      H:M=%H:%M
    |
      # Hour wildcard or specific hour, any other terms, and specific minute.
      H=(_|%H){SCHED_DELIMS}{SCHED_TERMS}M=%M
    )
  )
  ({SCHED_DELIMS}|$)
"""

QUEUE_URL = os.environ["QUEUE_URL"]
QUEUE_MSG_BYTES_MAX = int(os.environ["QUEUE_MSG_BYTES_MAX"])
QUEUE_MSG_FMT_VERSION = "01"

BACKUP_ROLE_ARN = os.environ["BACKUP_ROLE_ARN"]
BACKUP_VAULT_NAME = os.environ["BACKUP_VAULT_NAME"]

ARN_DELIM = ":"
ARN_PARTS = BACKUP_ROLE_ARN.split(ARN_DELIM)
# arn:partition:service:region:account-id:resource-type/resource-id
# [0] [1]       [2]     [3]    [4]        [5]
AWS_PARTITION = ARN_PARTS[1]
# https://docs.aws.amazon.com/lambda/latest/dg/configuration-envvars.html#configuration-envvars-runtime
AWS_REGION = os.environ.get("AWS_REGION", os.environ["AWS_DEFAULT_REGION"])
AWS_ACCOUNT = ARN_PARTS[4]

# 1. Custom Exceptions #######################################################


class SQSMessageTooLong(ValueError):
  """JSON-encoded SQS queue message exceeds QUEUE_MSG_BYTES_MAX
  """

# 2. Helpers #################################################################


def log(entry_type, entry_value, log_level=logging.INFO):
  """Emit a JSON-format log entry
  """
  logging.log(
    log_level,
    json.dumps({"type": entry_type, "value": entry_value}, default=str)
  )


def cycle_start_end(datetime_in, cycle_minutes=10, cutoff_minutes=9):
  """Take a datetime, return 10-minute floor and ceiling less 1 minute
  """
  cycle_minutes_int = int(cycle_minutes)
  cycle_start = datetime_in.replace(
    minute=(datetime_in.minute // cycle_minutes_int) * cycle_minutes_int,
    second=0,
    microsecond=0,
  )
  cycle_cutoff = cycle_start + datetime.timedelta(minutes=cutoff_minutes)
  return (cycle_start, cycle_cutoff)


def tag_key_join(tag_key_words):
  """Take a tuple of strings, add a prefix, join, and return a tag key
  """
  return "-".join(("sched", ) + tag_key_words)


def msg_attrs_str_encode(attr_pairs):
  """Take list of string name, value pairs, return SQS MessageAttributes dict
  """
  return {
    attr_name: {"DataType": "String", "StringValue": attr_value}
    for (attr_name, attr_value) in attr_pairs
  }


def msg_attr_str_decode(msg, attr_name):
  """Take an SQS message, return value of a string attribute (must be present)
  """
  return msg["messageAttributes"][attr_name]["stringValue"]


def msg_body_encode(msg_in):
  """Take an SQS queue message body dict, convert to JSON and check length
  """
  msg_out = json.dumps(msg_in)
  msg_out_len = len(bytes(msg_out, "utf-8"))
  if msg_out_len > QUEUE_MSG_BYTES_MAX:
    raise SQSMessageTooLong(
      f"JSON string too long: {msg_out_len} > {QUEUE_MSG_BYTES_MAX} bytes; "
      "increase QueueMessageBytesMax in CloudFormation"
    )
  return msg_out


def sqs_send_log(send_kwargs, entry_type, entry_value):
  """Log SQS send_message content and outcome
  """
  if (entry_type == "AWS_RESPONSE") and boto3_success(entry_value):
    log_level=logging.INFO
  else:
    log_level=logging.ERROR
  log("SQS_SEND", send_kwargs, log_level=log_level)
  log(entry_type, entry_value, log_level=log_level)


def op_log(event, resp=None, log_level=logging.ERROR):
  """Log Lambda function event and AWS SDK method call response
  """
  log("LAMBDA_EVENT", event, log_level=log_level)
  if resp is not None:
    log("AWS_RESPONSE", resp, log_level=log_level)


svc_clients = {}


def svc_client_get(svc):
  """Take an AWS service, return a boto3 client, creating it if needed
  """
  if svc_clients.get(svc, None) is None:
    svc_clients[svc] = boto3.client(svc)
    # boto3 method references can only be resolved at run-time,
    # against an instance of an AWS service's Client class.
    # http://boto3.readthedocs.io/en/latest/guide/events.html#extensibility-guide
  return svc_clients[svc]


def boto3_success(resp):
  """Take a boto3 response, return True if result was success

  Success means an AWS operation has started, not necessarily that it has
  completed. For example, it may take hours for a backup to become available.
  Checking completion is left to other tools.
  """
  return all([
    isinstance(resp, dict),
    isinstance(resp.get("ResponseMetadata", None), dict),
    resp["ResponseMetadata"].get("HTTPStatusCode", 0) == 200
  ])

# 3. Custom Classes ##########################################################

# See rsrc_types_init() for usage examples.


# pylint: disable=too-many-instance-attributes
class AWSRsrcType():
  """AWS resource type, with identification properties and various operations
  """
  members = collections.defaultdict(dict)

  # pylint: disable=too-many-arguments,too-many-positional-arguments
  def __init__(
    self,
    svc,
    rsrc_type_words,
    rsrc_id_key_suffix="Id",
    arn_key_suffix="Arn",
    tags_key="Tags",
    status_filter_pair=(),
    describe_flatten=None,
    ops=None
  ):
    self.svc = svc
    self.name_in_methods = "_".join(rsrc_type_words).lower()

    self.name_in_keys = "".join(rsrc_type_words)
    self.rsrc_id_key = f"{self.name_in_keys}{rsrc_id_key_suffix}"
    if arn_key_suffix:
      self.arn_prefix = ""
      self.arn_key = f"{self.name_in_keys}{arn_key_suffix}"
    else:
      self.arn_prefix = ARN_DELIM.join([
        "arn",
         AWS_PARTITION,
         svc,
         AWS_REGION,
         AWS_ACCOUNT,
         f"{self.name_in_methods}/",
      ])
      self.arn_key = self.rsrc_id_key
    self.tags_key = tags_key

    self.status_filter_pair = status_filter_pair
    if describe_flatten:
      self.describe_flatten = describe_flatten
    else:
      self.describe_flatten = lambda resp: resp.get(
        f"{self.name_in_keys}s", []
      )

    self.ops = {}
    for (op_tag_key_words, op_properties) in ops.items():
      AWSOp.new(self, op_tag_key_words, **op_properties)

    self.__class__.members[svc][self.name_in_keys] = self  # Register self

  def __str__(self):
    return f"AWSRsrcType {self.svc} {self.name_in_keys}"

  # pylint: disable=missing-function-docstring

  @property
  def ops_tag_keys(self):
    return self.ops.keys()

  @property
  def describe_filters(self):
    describe_filters_out = []
    if self.status_filter_pair:
      describe_filters_out.append(self.status_filter_pair)
      describe_filters_out.append(("tag-key", self.ops_tag_keys))
    return describe_filters_out

  @property
  def describe_kwargs(self):
    describe_kwargs_out = {}
    if self.describe_filters:
      describe_kwargs_out["Filters"] = [
        {"Name": filter_name, "Values": list(filter_values)}
        for (filter_name, filter_values) in self.describe_filters
      ]
    return describe_kwargs_out

  def rsrc_id(self, rsrc):
    """Take 1 describe_ result, return the resource ID
    """
    return rsrc[self.rsrc_id_key]

  def arn(self, rsrc):
    """Take 1 describe_ result, return the ARN
    """
    return f"{self.arn_prefix}{rsrc[self.arn_key]}"

  def rsrc_tags_list(self, rsrc):  # pylint: disable=no-self-use
    """Take 1 describe_ result, return raw resource tags
    """
    return rsrc.get(self.tags_key, [])  # Key may be missing if no tags

  def op_tags_match(self, rsrc, sched_regexp):
    """Scan 1 resource's tags to find operations scheduled for current cycle
    """
    ops_tag_keys = self.ops_tag_keys
    op_tags_matched = []
    for tag_dict in self.rsrc_tags_list(rsrc):
      tag_key = tag_dict["Key"]
      if tag_key in ops_tag_keys and sched_regexp.search(tag_dict["Value"]):
        op_tags_matched.append(tag_key)
    return op_tags_matched

  def rsrcs_find(self, sched_regexp, cycle_start_str, cycle_cutoff_epoch_str):
    """Find resources to operate on, and send details to queue
    """
    paginator = svc_client_get(self.svc).get_paginator(
      f"describe_{self.name_in_methods}s"
    )
    for resp in paginator.paginate(**self.describe_kwargs):
      for rsrc in self.describe_flatten(resp):
        op_tags_matched = self.op_tags_match(rsrc, sched_regexp)
        op_tags_matched_count = len(op_tags_matched)

        if op_tags_matched_count == 1:
          op = self.ops[op_tags_matched[0]]
          op.queue(rsrc, cycle_start_str, cycle_cutoff_epoch_str)
        elif op_tags_matched_count > 1:
          log(
            "MULTIPLE_OPS",
            {
              "svc": self.svc,
              "rsrc_type": self.name_in_keys,
              "rsrc_id": self.rsrc_id(rsrc),
              "op_tags_matched": op_tags_matched,
              "cycle_start_str": cycle_start_str,
            },
            log_level=logging.ERROR
          )


class AWSOp():
  """Operation on 1 AWS resource
  """
  def __init__(self, rsrc_type, tag_key_words, **kwargs):
    self.rsrc_type = rsrc_type
    self.tag_key_words = tag_key_words
    self.tag_key = tag_key_join(tag_key_words)
    self.svc = rsrc_type.svc
    verb = kwargs.get("verb", tag_key_words[0])  # Default: 1st word
    self.method_name = f"{verb}_{self.rsrc_type.name_in_methods}"
    self.kwargs_add = kwargs.get("kwargs_add", {})
    self.rsrc_type.ops[self.tag_key] = self  # Register under AWSRsrcType

  @staticmethod
  def new(rsrc_type, tag_key_words, **kwargs):
    """Create an op of the requested, appropriate, or default (sub)class
    """
    op_class = kwargs.get("class", AWSOp)
    return op_class(rsrc_type, tag_key_words, **kwargs)

  def kwarg_rsrc_id(self, rsrc):
    """Transfer resource ID from a describe_ result to another method's kwarg
    """
    return {self.rsrc_type.rsrc_id_key: self.rsrc_type.rsrc_id(rsrc)}

  # pylint: disable=unused-argument
  def op_kwargs(self, rsrc, cycle_start_str):
    """Take a describe_ result, return another method's kwargs
    """
    op_kwargs_out = self.kwarg_rsrc_id(rsrc)
    op_kwargs_out.update(self.kwargs_add)
    return op_kwargs_out

  def queue(self, rsrc, cycle_start_str, cycle_cutoff_epoch_str):
    """Send an operation message to the SQS queue
    """
    op_msg_attrs = msg_attrs_str_encode((
      ("version", QUEUE_MSG_FMT_VERSION),
      ("expires", cycle_cutoff_epoch_str),
      ("svc", self.svc),
      ("op_method_name", self.method_name),
    ))
    send_kwargs = {
      "QueueUrl": QUEUE_URL,
      "MessageAttributes": op_msg_attrs,
      "MessageBody": msg_body_encode(self.op_kwargs(rsrc, cycle_start_str)),
    }
    try:
      sqs_resp = svc_client_get("sqs").send_message(**send_kwargs)
    except (
      botocore.exceptions.ClientError,
      SQSMessageTooLong,
    ) as sqs_exception:
      sqs_send_log(send_kwargs, "EXCEPTION", sqs_exception)
      # Usually recoverable, try to queue next operation
    except Exception as misc_exception:
      sqs_send_log(send_kwargs, "EXCEPTION", misc_exception)
      raise  # Unrecoverable, stop queueing operations
    else:
      sqs_send_log(send_kwargs, "AWS_RESPONSE", sqs_resp)

  def __str__(self):
    return f"AWSOp {self.tag_key} {self.rsrc_type.svc}.{self.method_name}"


class AWSOpMultipleRsrcs(AWSOp):
  """Operation on multiple AWS resources of the same type
  """
  def __init__(self, rsrc_type, tag_key_words, **kwargs):
    super().__init__(rsrc_type, tag_key_words, **kwargs)
    self.method_name = self.method_name + "s"

  def kwarg_rsrc_id(self, rsrc):
    """Transfer resource ID from a describe_ result to a singleton list kwarg

    One at a time for consistency and to avoid partial completion risk
    """
    return {f"{self.rsrc_type.rsrc_id_key}s": [self.rsrc_type.rsrc_id(rsrc)]}


class AWSOpUpdateStack(AWSOp):
  """CloudFormation stack update operation
  """
  def __init__(self, rsrc_type, tag_key_words, **kwargs):
    super().__init__(rsrc_type, tag_key_words, verb="update", **kwargs)

  def op_kwargs(self, rsrc, cycle_start_str):
    """Take 1 describe_stacks result, return update_stack kwargs

    Preserves previous parameter values except for designated parameter(s):
                             Param  New
                             Key    Value
    tag_key        sched-set-Enable-true
    tag_key        sched-set-Enable-false
    tag_key_words            [-2]   [-1]
    """
    op_kwargs_out = super().op_kwargs(rsrc, cycle_start_str)
    changing_parameter_key = self.tag_key_words[-2]
    stack_parameters_out = [{
      "ParameterKey": changing_parameter_key,
      "ParameterValue": self.tag_key_words[-1],
    }]
    for stack_parameter_in in rsrc.get("Parameters", []):
      if stack_parameter_in["ParameterKey"] != changing_parameter_key:
        stack_parameters_out.append({
          "ParameterKey": stack_parameter_in["ParameterKey"],
          "UsePreviousValue": True,
        })
    op_kwargs_out.update({
      # WARNING: Use of the final, transformed template instead of the initial
      # one makes this incompatible with AWS::LanguageExtensions , which adds
      # Fn::ForEach , Fn::Length and Fn::ToJsonString to CloudFormation.
      # https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/transform-aws-languageextensions.html
      # A slow, individual get_template(TemplateStage="Original", ...) call
      # would be needed, because describe_stacks does not return templates.
      "UsePreviousTemplate": True,
      "Parameters": stack_parameters_out,
    })
    stack_capabilities_in = rsrc.get("Capabilities", [])
    if stack_capabilities_in:
      op_kwargs_out["Capabilities"] = stack_capabilities_in
    return op_kwargs_out


class AWSOpBackUp(AWSOp):
  """On-demand AWS Backup operation
  """
  def __init__(self, rsrc_type, tag_key_words, **kwargs):
    super().__init__(rsrc_type, tag_key_words, **kwargs)
    self.svc = "backup"
    self.method_name = "start_backup_job"

  def kwarg_rsrc_id(self, rsrc):
    """Transfer ARN from a describe_ result to a start_backup_job kwarg
    """
    return {"ResourceArn": self.rsrc_type.arn(rsrc)}

  def op_kwargs(self, rsrc, cycle_start_str):
    """Take a describe_ result, return start_backup_job kwargs
    """
    op_kwargs_out = super().op_kwargs(rsrc, cycle_start_str)
    op_kwargs_out.update({
      "IamRoleArn": BACKUP_ROLE_ARN,
      "BackupVaultName": BACKUP_VAULT_NAME,
      "StartWindowMinutes": 60,
      "RecoveryPointTags": {tag_key_join(("time")): cycle_start_str},
    })
    return op_kwargs_out


# 4. Data-Driven Specifications ##############################################


def rsrc_types_init():
  """Create AWS resource type objects when needed, if not already done
  """

  if not AWSRsrcType.members:
    AWSRsrcType(
      "ec2",
      ("Instance", ),
      arn_key_suffix=None,
      status_filter_pair=(
        "instance-state-name", ("running", "stopping", "stopped")
      ),
      describe_flatten=lambda resp: (
        instance
        for reservation in resp.get("Reservations", [])
        for instance in reservation.get("Instances", [])
      ),
      ops={
        ("start", ): {"class": AWSOpMultipleRsrcs},
        ("reboot", ): {"class": AWSOpMultipleRsrcs},
        ("stop", ): {"class": AWSOpMultipleRsrcs},
        ("hibernate", ): {
          "class": AWSOpMultipleRsrcs,
          "verb": "stop",
          "kwargs_add": {"Hibernate": True},
        },
        ("backup", ): {"class": AWSOpBackUp},
      },
    )

    AWSRsrcType(
      "ec2",
      ("Volume", ),
      arn_key_suffix=None,
      status_filter_pair=("status", ("available", "in-use")),
      ops={
        ("backup", ): {"class": AWSOpBackUp},
      },
    )

    AWSRsrcType(
      "rds",
      ("DB", "Instance"),
      rsrc_id_key_suffix="Identifier",
      tags_key="TagList",
      ops={
        ("start", ): {},
        ("stop", ): {},
        ("reboot", ): {},
        ("reboot", "failover"): {"kwargs_add": {"ForceFailover": True}},
        ("backup", ): {"class": AWSOpBackUp},
      },
    )

    AWSRsrcType(
      "rds",
      ("DB", "Cluster"),
      rsrc_id_key_suffix="Identifier",
      tags_key="TagList",
      ops={
        ("start", ): {},
        ("stop", ): {},
        ("reboot", ): {},
        ("backup", ): {"class": AWSOpBackUp},
      },
    )

    AWSRsrcType(
      "cloudformation",
      ("Stack", ),
      rsrc_id_key_suffix="Name",
      arn_key_suffix="Id",
      ops={
        ("set", "Enable", "true"): {"class": AWSOpUpdateStack},
        ("set", "Enable", "false"): {"class": AWSOpUpdateStack},
        ("backup", ): {"class": AWSOpBackUp},
      },
    )


# 5. Find Resources Lambda Function Handler ##################################


def lambda_handler_find(event, context):  # pylint: disable=unused-argument
  """Find and queue AWS resources for scheduled operations, based on tags
  """
  log("LAMBDA_EVENT", event)
  (cycle_start, cycle_cutoff) = cycle_start_end(
    datetime.datetime.now(datetime.timezone.utc)
  )
  cycle_start_str = cycle_start.strftime("%Y-%m-%dT%H:%M")
  cycle_cutoff_epoch_str = str(int(cycle_cutoff.timestamp()))
  sched_regexp = re.compile(
    cycle_start.strftime(SCHED_REGEXP_STRFTIME_FMT), re.VERBOSE
  )
  log("START", cycle_start_str)
  log("SCHED_REGEXP_VERBOSE", sched_regexp.pattern)
  rsrc_types_init()
  for rsrc_types in AWSRsrcType.members.values():
    for rsrc_type in rsrc_types.values():
      rsrc_type.rsrcs_find(
        sched_regexp, cycle_start_str, cycle_cutoff_epoch_str
      )

# 6. "Do" Operations Lambda Function Handler #################################


def lambda_handler_do(event, context):  # pylint: disable=unused-argument
  """Perform a queued operation on an AWS resource
  """
  for msg in event.get("Records", []):  # 0 or 1 messages expected
    if msg_attr_str_decode(msg, "version") != QUEUE_MSG_FMT_VERSION:
      op_log(event)
      raise RuntimeError("Unrecognized queue message format")
    if (
      int(msg_attr_str_decode(msg, "expires"))
      < int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    ):
      op_log(event)
      raise RuntimeError(
        "Late; schedule fewer operations per 10-minute cycle, or increase "
        "DoLambdaFnReservedConcurrentExecutions CloudFormation parameter"
      )

    svc = msg_attr_str_decode(msg, "svc")
    op_method_name = msg_attr_str_decode(msg, "op_method_name")
    op_kwargs = json.loads(msg["body"])
    try:
      op_method = getattr(svc_client_get(svc), op_method_name)
      resp = op_method(**op_kwargs)
    except Exception:
      op_log(event)
      raise
    if boto3_success(resp):
      op_log(event, resp=resp, log_level=logging.INFO)
    else:
      op_log(event, resp=resp)
      raise RuntimeError("Miscellaneous AWS erorr")
