#!/usr/bin/env python3
"""Start, reboot, stop and back up AWS resources using schedules in tags

github.com/sqlxpert/lights-off-aws  GPLv3  Copyright Paul Marcelin
"""

import os
import logging
import datetime
import re
import json
import botocore
import boto3

logger = logging.getLogger()
# Skip "credentials in environment" INFO message, unavoidable in AWS Lambda:
logging.getLogger("botocore").setLevel(logging.WARNING)


def environ_int(environ_var_name):
  """Take name of an environment variable, return its integer value
  """
  return int(os.environ[environ_var_name])


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
QUEUE_MSG_BYTES_MAX = environ_int("QUEUE_MSG_BYTES_MAX")
QUEUE_MSG_FMT_VERSION = "01"

ARN_DELIM = ":"
BACKUP_ROLE_ARN = os.environ["BACKUP_ROLE_ARN"]
ARN_PARTS = BACKUP_ROLE_ARN.split(ARN_DELIM)
# arn:partition:service:region:account-id:resource-type/resource-id
# [0] [1]       [2]     [3]    [4]        [5]
# https://docs.aws.amazon.com/lambda/latest/dg/configuration-envvars.html#configuration-envvars-runtime
ARN_PARTS[3] = os.environ.get("AWS_REGION", os.environ["AWS_DEFAULT_REGION"])

# 1. Custom Exceptions #######################################################


class SQSMessageTooLong(ValueError):
  """JSON-encoded SQS queue message exceeds QUEUE_MSG_BYTES_MAX
  """

# 2. Helpers #################################################################


def log(entry_type, entry_value, log_level=logging.INFO):
  """Emit a JSON-format log entry
  """
  entry_value_out = json.loads(json.dumps(entry_value, default=str))
  # Avoids "Object of type datetime is not JSON serializable" in
  # https://github.com/aws/aws-lambda-python-runtime-interface-client/blob/9efb462/awslambdaric/lambda_runtime_log_utils.py#L109-L135
  #
  # The JSON encoder in the AWS Lambda Python runtime isn't configured to
  # serialize datatime values in responses returned by AWS's own Python SDK!
  #
  # Powertools for Lambda is too heavy for a simple deployment.
  # https://docs.powertools.aws.dev/lambda/python/latest/core/logger/

  logger.log(
    log_level, "", extra={"type": entry_type, "value": entry_value_out}
  )


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


def sqs_send_log(send_kwargs, entry_type, entry_value):
  """Log SQS send_message content and outcome
  """
  if (entry_type == "AWS_RESPONSE") and boto3_success(entry_value):
    log_level = logging.INFO
  else:
    log_level = logging.ERROR
  log("SQS_SEND", send_kwargs, log_level=log_level)
  log(entry_type, entry_value, log_level=log_level)


def op_log(event, resp=None, log_level=logging.ERROR):
  """Log Lambda function event and AWS SDK method call response
  """
  log("LAMBDA_EVENT", event, log_level=log_level)
  if resp is not None:
    log("AWS_RESPONSE", resp, log_level=log_level)


def tag_key_join(tag_key_words):
  """Take a tuple of strings, add a prefix, join, and return a tag key
  """
  return "-".join(("sched", ) + tag_key_words)


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


# 3. Custom Classes ##########################################################

# See rsrc_types_init() for usage examples.


# pylint: disable=too-many-instance-attributes
class AWSRsrcType():
  """AWS resource type, with identification properties and various operations
  """
  members = {}

  # pylint: disable=too-many-arguments,too-many-positional-arguments
  def __init__(
    self,
    svc,
    rsrc_type_words,
    ops_dict,
    rsrc_id_key_suffix="Id",
    arn_key_suffix="Arn",
    tags_key="Tags",
    status_filter_pair=(),
    describe_flatten=None,
  ):
    self.svc = svc
    self.name_in_methods = "_".join(rsrc_type_words).lower()

    self.name_in_keys = "".join(rsrc_type_words)
    self.rsrc_id_key = f"{self.name_in_keys}{rsrc_id_key_suffix}"
    if arn_key_suffix:
      self.arn_prefix = ""
      self.arn_key = f"{self.name_in_keys}{arn_key_suffix}"
    else:
      self.arn_prefix = ARN_DELIM.join(
        ARN_PARTS[0:2] + [svc] + ARN_PARTS[3:5] + [f"{self.name_in_methods}/"]
      )
      self.arn_key = self.rsrc_id_key
    self.tags_key = tags_key

    if describe_flatten:
      self.describe_flatten = describe_flatten
    else:
      self.describe_flatten = lambda resp: resp.get(
        f"{self.name_in_keys}s", []
      )

    self.ops = {}
    for (op_tag_key_words, op_properties) in ops_dict.items():
      op = AWSOp.new(self, op_tag_key_words, **op_properties)
      self.ops[op.tag_key] = op

    self.describe_kwargs = {}
    if status_filter_pair:
      self.describe_kwargs["Filters"] = [
        {"Name": filter_name, "Values": list(filter_values)}
        for (filter_name, filter_values)
        in [status_filter_pair, ("tag-key", self.ops_tag_keys)]
      ]

    self.__class__.members[(svc, self.name_in_keys)] = self  # Register me!

  def __str__(self):
    return " ".join([self.__class__.__name__, self.svc, self.name_in_keys])

  @property
  def ops_tag_keys(self):
    """Return tag keys for all operations on this resource type
    """
    return self.ops.keys()

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
    self.tag_key = tag_key_join(tag_key_words)
    self.svc = rsrc_type.svc
    self.rsrc_id = rsrc_type.rsrc_id
    verb = kwargs.get("verb", tag_key_words[0])  # Default: 1st word
    self.method_name = f"{verb}_{rsrc_type.name_in_methods}"
    self.kwarg_rsrc_id_key = rsrc_type.rsrc_id_key
    self.kwargs_add = kwargs.get("kwargs_add", {})

  @staticmethod
  def new(rsrc_type, tag_key_words, **kwargs):
    """Create an op of the requested, appropriate, or default (sub)class
    """
    op_class = kwargs.get("class", AWSOp)
    return op_class(rsrc_type, tag_key_words, **kwargs)

  def kwarg_rsrc_id(self, rsrc):
    """Transfer resource ID from a describe_ result to another method's kwarg
    """
    return {self.kwarg_rsrc_id_key: self.rsrc_id(rsrc)}

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
    return " ".join([
      self.__class__.__name__, self.tag_key, self.svc, self.method_name
    ])


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
    return {f"{self.kwarg_rsrc_id_key}s": [self.rsrc_id(rsrc)]}


class AWSOpUpdateStack(AWSOp):
  """CloudFormation stack update operation
  """
  def __init__(self, rsrc_type, tag_key_words, **kwargs):
    super().__init__(rsrc_type, tag_key_words, verb="update", **kwargs)

    # Use of final template instead of original makes this incompatible with
    # CloudFormation "transforms". describe_stacks does not return templates.
    self.kwargs_add["UsePreviousTemplate"] = True

    # Use previous parameter values, except for:
    #                          Param  Value
    #                          Key    Out
    # tag_key        sched-set-Enable-true
    # tag_key        sched-set-Enable-false
    # tag_key_words            [-2]   [-1]
    self.changing_params_out = {
      tag_key_words[-2]: tag_key_words[-1],  # Only 1 for now
    }

  def op_kwargs(self, rsrc, cycle_start_str):
    """Take 1 describe_stacks result, return update_stack kwargs
    """
    params_out = []
    for param_in in rsrc.get("Parameters", []):
      param_in_key = param_in["ParameterKey"]
      param_out = {"ParameterKey": param_in_key}
      if param_in_key in self.changing_params_out:
        param_out["ParameterValue"] = self.changing_params_out[param_in_key]
      else:
        param_out["UsePreviousValue"] = True
      params_out.append(param_out)

    op_kwargs_out = super().op_kwargs(rsrc, cycle_start_str)
    op_kwargs_out["Parameters"] = params_out
    capabilities_in = rsrc.get("Capabilities", [])
    if capabilities_in:
      op_kwargs_out["Capabilities"] = capabilities_in
    return op_kwargs_out

  def __str__(self):
    return super().__str__() + f" {self.changing_params_out}"


class AWSOpBackUp(AWSOp):
  """On-demand AWS Backup operation
  """
  backup_kwargs_add = {}

  @classmethod
  def backup_kwargs_add_init(cls):
    """Populate start_backup_job static kwargs, if not yet done
    """
    if not cls.backup_kwargs_add:
      lifecycle = {}

      cold_storage_after_days = environ_int("BACKUP_COLD_STORAGE_AFTER_DAYS")
      if cold_storage_after_days > 0:
        lifecycle.update({
          "OptInToArchiveForSupportedResources": True,
          "MoveToColdStorageAfterDays": cold_storage_after_days,
        })

      delete_after_days = environ_int("BACKUP_DELETE_AFTER_DAYS")
      if delete_after_days > 0:
        lifecycle["DeleteAfterDays"] = delete_after_days

      cls.backup_kwargs_add.update({
        "IamRoleArn": BACKUP_ROLE_ARN,
        "BackupVaultName": os.environ["BACKUP_VAULT_NAME"],
        "StartWindowMinutes": environ_int("BACKUP_START_WINDOW_MINUTES"),
        "CompleteWindowMinutes": environ_int(
          "BACKUP_COMPLETE_WINDOW_MINUTES"
        ),
      })
      if lifecycle:
        cls.backup_kwargs_add["Lifecycle"] = lifecycle

  def __init__(self, rsrc_type, tag_key_words, **kwargs):
    super().__init__(rsrc_type, tag_key_words, **kwargs)
    self.rsrc_id = rsrc_type.arn
    self.svc = "backup"
    self.method_name = "start_backup_job"
    self.kwarg_rsrc_id_key = "ResourceArn"
    self.__class__.backup_kwargs_add_init()
    self.kwargs_add.update(self.__class__.backup_kwargs_add)

  def op_kwargs(self, rsrc, cycle_start_str):
    """Take a describe_ result, return start_backup_job kwargs
    """
    op_kwargs_out = super().op_kwargs(rsrc, cycle_start_str)
    op_kwargs_out.update({
      "IdempotencyToken": cycle_start_str,
      "RecoveryPointTags": {tag_key_join(("time", )): cycle_start_str},
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
      {
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
      arn_key_suffix=None,
      status_filter_pair=(
        "instance-state-name", ("running", "stopping", "stopped")
      ),
      describe_flatten=lambda resp: (
        instance
        for reservation in resp.get("Reservations", [])
        for instance in reservation.get("Instances", [])
      ),
    )

    AWSRsrcType(
      "ec2",
      ("Volume", ),
      {("backup", ): {"class": AWSOpBackUp}},
      arn_key_suffix=None,
      status_filter_pair=("status", ("available", "in-use")),
    )

    AWSRsrcType(
      "rds",
      ("DB", "Instance"),
      {
        ("start", ): {},
        ("stop", ): {},
        ("reboot", ): {},
        ("reboot", "failover"): {"kwargs_add": {"ForceFailover": True}},
        ("backup", ): {"class": AWSOpBackUp},
      },
      rsrc_id_key_suffix="Identifier",
      tags_key="TagList",
    )

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

    AWSRsrcType(
      "cloudformation",
      ("Stack", ),
      {
        ("set", "Enable", "true"): {"class": AWSOpUpdateStack},
        ("set", "Enable", "false"): {"class": AWSOpUpdateStack},
      },
      rsrc_id_key_suffix="Name",
      arn_key_suffix="Id",
    )


# 5. Find Resources Lambda Function Handler ##################################


def lambda_handler_find(event, context):  # pylint: disable=unused-argument
  """Find and queue AWS resources for scheduled operations, based on tags
  """
  log("LAMBDA_EVENT", event)
  (cycle_start, cycle_cutoff) = cycle_start_end(
    datetime.datetime.now(datetime.timezone.utc)
  )
  cycle_start_str = cycle_start.strftime("%Y-%m-%dT%H:%MZ")
  cycle_cutoff_epoch_str = str(int(cycle_cutoff.timestamp()))
  sched_regexp = re.compile(
    cycle_start.strftime(SCHED_REGEXP_STRFTIME_FMT), re.VERBOSE
  )
  log("START", cycle_start_str)
  log("SCHED_REGEXP_VERBOSE", sched_regexp.pattern)
  rsrc_types_init()
  for rsrc_type in AWSRsrcType.members.values():
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
    except Exception as misc_exception:
      op_log(event)
      log("EXCEPTION", misc_exception, log_level=logging.ERROR)
      raise
    if boto3_success(resp):
      op_log(event, resp=resp, log_level=logging.INFO)
    else:
      op_log(event, resp=resp)
      raise RuntimeError("Miscellaneous AWS erorr")
