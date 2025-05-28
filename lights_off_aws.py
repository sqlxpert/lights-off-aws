#!/usr/bin/env python3
"""Start, stop and back up AWS resources tagged with cron schedules

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
  """String of JSON-encoded SQS queue message exceeds QUEUE_MSG_BYTES_MAX
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
  # Alternative considered:
  # https://docs.powertools.aws.dev/lambda/python/latest/core/logger/

  logger.log(
    log_level, "", extra={"type": entry_type, "value": entry_value_out}
  )


def sqs_send_log(
  cycle_start_str,
  send_kwargs,
  entry_type,
  entry_value,
  log_level=logging.ERROR
):
  """Log scheduled start time (on error), SQS send_message content, outcome
  """
  if log_level == logging.ERROR:
    log("START", cycle_start_str, log_level)
  log("SQS_SEND", send_kwargs, log_level)
  log(entry_type, entry_value, log_level)


def op_log(event, entry_type, result, log_level):
  """Log Lambda event, entry type and result of operation, at log_level
  """
  log("LAMBDA_EVENT", event, log_level)
  log(entry_type, result, log_level)


def assess_op_except(svc, op_method_name, misc_except):
  """Take an operation and an exception, return log level and recoverability

  botocore.exceptions.ClientError is general but statically-defined, making
  comparison easier, in a multi-service context, than for service-specific but
  dynamically-defined exceptions like
  boto3.Client("rds").exceptions.InvalidDBClusterStateFault and
  boto3.Client("rds").exceptions.InvalidDBInstanceStateFault

  https://boto3.amazonaws.com/v1/documentation/api/latest/guide/error-handling.html#parsing-error-responses-and-catching-exceptions-from-aws-services
  """
  log_level = logging.ERROR
  recoverable = False

  if isinstance(misc_except, botocore.exceptions.ClientError):
    verb = op_method_name.split("_")[0]
    err_dict = getattr(misc_except, "response", {}).get("Error", {})
    err_msg = err_dict.get("Message")

    match (svc, err_dict.get("Code")):

      case ("cloudformation", "ValidationError") if (
        "No updates are to be performed." == err_msg
      ):
        log_level = logging.INFO
        recoverable = True
        # Recent, identical external update_stack

      case ("rds", "InvalidDBClusterStateFault") if (
        ((verb == "start") and "is in available" in err_msg)
        or f"is in {verb}" in err_msg
      ):
        log_level = logging.INFO
        recoverable = True
        # start_db_cluster when "in available[ state]" or "in start[ing state]"
        # stop__db_cluster when "in stop[ped state]"   or "in stop[ping state]"

      case ("rds", "InvalidDBInstanceState"):  # Fault suffix is missing here!
        recoverable = True
        # Can't decide between idempotent start_db_instance / stop_db_instance
        # or error, because message does not reveal the current, invalid state.

  return (log_level, recoverable)


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
    log("QUEUE_MSG", msg_out, logging.ERROR)
    raise SQSMessageTooLong()
  return msg_out


svc_clients = {}


def svc_client_get(svc):
  """Take an AWS service, return a boto3 client, creating it if needed

  boto3 method references can only be resolved at run-time, against an
  instance of an AWS service's Client class.
  http://boto3.readthedocs.io/en/latest/guide/events.html#extensibility-guide

  Alternatives considered:
  https://github.com/boto/boto3/issues/3197#issue-1175578228
  https://github.com/aws-samples/boto-session-manager-project
  """
  if svc not in svc_clients:
    svc_clients[svc] = boto3.client(
      svc, config=botocore.config.Config(retries={"mode": "standard"})
    )
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
    status_filter_pair=()
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

  def get_describe_pages(self):
    """Return an iterator over pages of boto3 describe_ responses
    """
    return svc_client_get(self.svc).get_paginator(
      f"describe_{self.name_in_methods}s"
    ).paginate(**self.describe_kwargs)

  def get_rsrcs(self):
    """Return an iterator over individual boto3 describe_ items
    """
    return (
      rsrc
      for page in self.get_describe_pages()
      for rsrc in page.get(f"{self.name_in_keys}s", [])
    )

  def rsrc_tags_list(self, rsrc):
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
    for rsrc in self.get_rsrcs():
      op_tags_matched = self.op_tags_match(rsrc, sched_regexp)
      op_tags_matched_count = len(op_tags_matched)

      if op_tags_matched_count == 1:
        op = self.ops[op_tags_matched[0]]
        op.queue(rsrc, cycle_start_str, cycle_cutoff_epoch_str)
      elif op_tags_matched_count > 1:
        log("START", cycle_start_str, logging.ERROR)
        log(
          "MULTIPLE_OPS",
          {"arn": self.arn(rsrc), "tag_keys": op_tags_matched},
          logging.ERROR
        )


class AWSRsrcTypeEc2Inst(AWSRsrcType):
  """EC2 instance
  """
  def get_rsrcs(self):
    return (
      instance
      for page in self.get_describe_pages()
      for reservation in page.get("Reservations", [])
      for instance in reservation.get("Instances", [])
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
    if "class" in kwargs:
      op_class = kwargs["class"]
    elif tag_key_words == ("backup", ):
      op_class = AWSOpBackUp
    else:
      op_class = AWSOp
    return op_class(rsrc_type, tag_key_words, **kwargs)

  def kwarg_rsrc_id(self, rsrc):
    """Transfer resource ID from a describe_ result to another method's kwarg
    """
    return {self.kwarg_rsrc_id_key: self.rsrc_id(rsrc)}

  def op_kwargs(self, rsrc, cycle_start_str):  # pylint: disable=unused-argument
    """Take a describe_ result, return another method's kwargs
    """
    op_kwargs_out = self.kwarg_rsrc_id(rsrc)
    op_kwargs_out.update(self.kwargs_add)
    return op_kwargs_out

  def queue(self, rsrc, cycle_start_str, cycle_cutoff_epoch_str):
    """Send 1 operation message to the SQS queue
    """
    op_kwargs = self.op_kwargs(rsrc, cycle_start_str)
    if op_kwargs:
      send_kwargs = {
        "QueueUrl": QUEUE_URL,
        "MessageAttributes": msg_attrs_str_encode((
          ("version", QUEUE_MSG_FMT_VERSION),
          ("expires", cycle_cutoff_epoch_str),
          ("svc", self.svc),
          ("op_method_name", self.method_name),
        )),
      }
      try:
        send_kwargs.update({"MessageBody": msg_body_encode(op_kwargs)})
        sqs_resp = svc_client_get("sqs").send_message(**send_kwargs)
      except SQSMessageTooLong:
        sqs_send_log(
          cycle_start_str,
          send_kwargs,
          "QUEUE_MSG_TOO_LONG",
          "Increase QueueMessageBytesMax in CloudFormation",
        )
      except Exception as misc_except:
        sqs_send_log(cycle_start_str, send_kwargs, "EXCEPTION", misc_except)
        raise  # In error cases other than this, log 1 failed send but move on
      else:
        sqs_send_log(
          cycle_start_str,
          send_kwargs,
          "AWS_RESPONSE",
          sqs_resp,
          log_level=logging.INFO
        )

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
    self.kwargs_add.update({
      "UsePreviousTemplate": True,
      "RetainExceptOnCreate": True,
    })

    # Use previous parameter values, except for:
    #                          Param  Value
    #                          Key    Out
    # tag_key        sched-set-Enable-true
    # tag_key        sched-set-Enable-false
    # tag_key_words            [-2]   [-1]
    self.changing_param_key = tag_key_words[-2]
    self.changing_param_value_out = tag_key_words[-1]

  def op_kwargs(self, rsrc, cycle_start_str):
    """Take 1 describe_stacks result, return update_stack kwargs

    An empty dict indicates that no stack update is needed.
    """
    op_kwargs_out = {}
    params_out = []

    if rsrc.get("StackStatus") in (
      "UPDATE_COMPLETE",
      "CREATE_COMPLETE",
    ):
      for param in rsrc.get("Parameters", []):
        param_key = param["ParameterKey"]
        param_out = {
          "ParameterKey": param_key,
          "UsePreviousValue": True,
        }

        if param_key == self.changing_param_key:
          if param.get("ParameterValue") == self.changing_param_value_out:
            break

          # One time, if changing_param is present and not already up-to-date
          param_out.update({
            "UsePreviousValue": False,
            "ParameterValue": self.changing_param_value_out,
          })
          op_kwargs_out = super().op_kwargs(rsrc, cycle_start_str)
          op_kwargs_out.update({
            "ClientRequestToken": f"{self.tag_key}-{cycle_start_str}",
            "Parameters": params_out,  # Continue updating dict in-place
          })
          capabilities = rsrc.get("Capabilities")
          if capabilities:
            op_kwargs_out["Capabilities"] = capabilities

        params_out.append(param_out)

    else:
      log("ERROR", "STACK_STATUS_IRREGULAR", logging.ERROR)
      log("AWS_RESPONSE_PART", rsrc, logging.ERROR)

    return op_kwargs_out


class AWSOpBackUp(AWSOp):
  """On-demand AWS Backup operation
  """
  backup_kwargs_add = None
  lifecycle_base = None

  @classmethod
  def backup_kwargs_add_init(cls):
    """Populate start_backup_job kwargs and base lifecycle, if not yet done
    """
    if not cls.backup_kwargs_add:
      cls.backup_kwargs_add = {
        "IamRoleArn": BACKUP_ROLE_ARN,
        "BackupVaultName": os.environ["BACKUP_VAULT_NAME"],
        "StartWindowMinutes": environ_int("BACKUP_START_WINDOW_MINUTES"),
        "CompleteWindowMinutes": environ_int(
          "BACKUP_COMPLETE_WINDOW_MINUTES"
        ),
      }

      cls.lifecycle_base = {}
      cold_storage_after_days = environ_int("BACKUP_COLD_STORAGE_AFTER_DAYS")
      if cold_storage_after_days > 0:
        cls.lifecycle_base.update({
          "OptInToArchiveForSupportedResources": True,
          "MoveToColdStorageAfterDays": cold_storage_after_days,
        })
      delete_after_days = environ_int("BACKUP_DELETE_AFTER_DAYS")
      if delete_after_days > 0:
        cls.lifecycle_base["DeleteAfterDays"] = delete_after_days  # pylint: disable=unsupported-assignment-operation

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
    lifecycle = dict(self.lifecycle_base)  # Updatable copy (future need)
    if lifecycle:
      op_kwargs_out["Lifecycle"] = lifecycle
    return op_kwargs_out


# 4. Data-Driven Specifications ##############################################


def rsrc_types_init():
  """Create AWS resource type objects when needed, if not already done
  """

  if not AWSRsrcType.members:
    AWSRsrcTypeEc2Inst(
      "ec2",
      ("Instance", ),
      {
        ("start", ): {"class": AWSOpMultipleRsrcs},
        ("stop", ): {"class": AWSOpMultipleRsrcs},
        ("hibernate", ): {
          "class": AWSOpMultipleRsrcs,
          "verb": "stop",
          "kwargs_add": {"Hibernate": True},
        },
        ("backup", ): {},
      },
      arn_key_suffix=None,
      status_filter_pair=(
        "instance-state-name", ("running", "stopping", "stopped")
      )
    )

    AWSRsrcType(
      "ec2",
      ("Volume", ),
      {("backup", ): {}},
      arn_key_suffix=None,
      status_filter_pair=("status", ("available", "in-use")),
    )

    AWSRsrcType(
      "rds",
      ("DB", "Instance"),
      {
        ("start", ): {},
        ("stop", ): {},
        ("backup", ): {},
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
        ("backup", ): {},
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

  # ISO 8601 basic, no puctuation (downstream requirement)
  cycle_start_str = cycle_start.strftime("%Y%m%dT%H%MZ")

  cycle_cutoff_epoch_str = str(int(cycle_cutoff.timestamp()))
  sched_regexp = re.compile(
    cycle_start.strftime(SCHED_REGEXP_STRFTIME_FMT), re.VERBOSE
  )
  log("START", cycle_start_str)
  log("SCHED_REGEXP_VERBOSE", sched_regexp.pattern, logging.DEBUG)
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
    log_level = logging.ERROR

    result = None
    log_entry_type = None
    raise_except = None

    try:
      if msg_attr_str_decode(msg, "version") != QUEUE_MSG_FMT_VERSION:
        result = "Unrecognized operation queue message format"
        log_entry_type = "WRONG_QUEUE_MSG_FMT"
        raise_except = RuntimeError()

      elif (
        int(msg_attr_str_decode(msg, "expires"))
        < int(datetime.datetime.now(datetime.timezone.utc).timestamp())
      ):
        result = (
          "Schedule fewer operations per 10-minute cycle or "
          "increase DoLambdaFnMaximumConcurrency in CloudFormation"
        )
        log_entry_type = "EXPIRED_OP"
        raise_except = RuntimeError()

      else:
        svc = msg_attr_str_decode(msg, "svc")
        op_method_name = msg_attr_str_decode(msg, "op_method_name")
        op_kwargs = json.loads(msg["body"])
        op_method = getattr(svc_client_get(svc), op_method_name)
        result = op_method(**op_kwargs)
        log_entry_type = "AWS_RESPONSE"
        log_level = logging.INFO

    except Exception as misc_except:  # pylint: disable=broad-exception-caught
      result = misc_except
      log_entry_type = "EXCEPTION"
      (log_level, recoverable) = assess_op_except(
        svc, op_method_name, misc_except
      )
      if not recoverable:
        raise_except = misc_except

    op_log(event, log_entry_type, result, log_level)
    if raise_except:
      raise raise_except
