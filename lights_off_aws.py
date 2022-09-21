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
import random
import collections
import botocore
import boto3

logging.getLogger().setLevel(os.environ.get("LOG_LEVEL", logging.ERROR))

SCHED_DELIMS = r"\ +"  # Exposed space must be escaped for re.VERBOSE
SCHED_TERMS = rf"([^ ]+=[^ ]+{SCHED_DELIMS})*"  # Unescaped space inside class
SCHED_REGEXP_STRFTIME_FMT = (rf"""
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
""")

QUEUE_URL = os.environ.get("QUEUE_URL", "")
QUEUE_MSG_BYTES_MAX = int(os.environ.get("QUEUE_MSG_BYTES_MAX", "-1"))
QUEUE_MSG_FMT_VERSION = "01"

TAG_KEY_PREFIX = "sched"
TAG_KEY_DELIM = "-"
TAG_KEYS_NO_COPY_REGEXP = (
  rf"^((aws|ec2|rds):|{TAG_KEY_PREFIX}{TAG_KEY_DELIM})"
)
COPY_TAGS = (os.environ.get("COPY_TAGS", "").lower() == "true")


# 1. Custom Exceptions #######################################################

class SQSMessageTooLong(ValueError):
  """JSON-encoded SQS queue message exceeds QUEUE_MSG_BYTES_MAX
  """


# 2. Custom Classes ##########################################################

# See rsrc_types_init() for usage examples.

# For least-privilege permissions and low overhead (in potentially large AWS
# accounts with hundreds or thousands of resources to scan), custom classes
# were defined, to support use of low-level boto3 "clients". Whether boto3's
# own high-level classes, "resources", involve only essential AWS API calls
# and are economical at scale is not known.

# pylint: disable=too-few-public-methods

class AWSRsrcType():
  """Basic AWS resource type, with identification properties
  """

  def __init__(self, svc, rsrc_type_words, rsrc_id_key_suffix):
    self.svc = svc
    self.rsrc_type_in_methods = "_".join(rsrc_type_words).lower()
    self.rsrc_type_in_keys = "".join(rsrc_type_words)
    self.rsrc_key = self.rsrc_type_in_keys  # Friendlier, general-use synonym
    self.rsrcs_key = f"{self.rsrc_type_in_keys}s"
    self.rsrc_id_key = f"{self.rsrc_type_in_keys}{rsrc_id_key_suffix}"
    self.rsrc_ids_key = f"{self.rsrc_id_key}s"

  def __str__(self):
    return f"AWSRsrcType {self.svc} {self.rsrc_key}"


class AWSChildRsrcType(AWSRsrcType):
  """AWS child resource type, supporting creation operation
  """
  members = collections.defaultdict(dict)

  def __init__(self, svc, rsrc_type_words, rsrc_id_key_suffix, **kwargs):
    super().__init__(svc, rsrc_type_words, rsrc_id_key_suffix)
    self.name_chars_max = kwargs["name_chars_max"]
    self.name_chars_unsafe_regexp = kwargs.get("name_chars_unsafe_regexp", "")
    self.op_kwargs_update_child_fn = kwargs["op_kwargs_update_child_fn"]
    self.__class__.members[svc][self.rsrc_key] = self


class AWSParentRsrcType(AWSRsrcType):
  """AWS parent resource type, supporting various operations
  """
  members = collections.defaultdict(dict)

  def __init__(self, svc, rsrc_type_words, rsrc_id_key_suffix, **kwargs):
    super().__init__(svc, rsrc_type_words, rsrc_id_key_suffix)
    self.status_filter_pair = kwargs.get("status_filter_pair", ())
    self.flatten_fn = kwargs.get("flatten_fn", None)
    self.ops = {}
    for (op_tag_key_words, op_properties) in kwargs["ops"].items():
      op_tag_key = tag_key_join(op_tag_key_words)
      op_properties_add = {"op_tag_key": op_tag_key}
      # Default verbs (specification shorthands):
      if "verb" not in op_properties:
        op_properties_add["verb"] = (
          "create"
          if "child_rsrc_type" in op_properties else
          op_tag_key_words[0]  # Same as (first) tag key word
        )
      self.ops[op_tag_key] = AWSOp(self, **(op_properties | op_properties_add))
    self.__class__.members[svc][self.rsrc_key] = self

  # pylint: disable=missing-function-docstring

  @property
  def describe_method_name(self):
    return f"describe_{self.rsrc_type_in_methods}s"

  @property
  def ops_tag_keys(self):
    return self.ops.keys()

  @property
  def describe_filters(self):
    describe_filters_out = []
    if self.status_filter_pair:
      describe_filters_out.append(self.status_filter_pair)
      if self.ops:
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


class AWSOp():
  """
  Operation on an AWS resource type, possibly creating a child resource
  """
  def __init__(self, rsrc_type, verb, multiple_rsrcs=False, **kwargs):
    self.rsrc_type = rsrc_type
    if "child_rsrc_type" in kwargs:
      self.child_rsrc_type = kwargs["child_rsrc_type"]
      noun_source = self.child_rsrc_type
    else:
      self.child_rsrc_type = None
      noun_source = self.rsrc_type
    self.multiple_rsrcs = multiple_rsrcs
    noun_suffix_plural = "s" if self.multiple_rsrcs else ""
    self.op_method_name = (
      f"{verb}_{noun_source.rsrc_type_in_methods}{noun_suffix_plural}"
    )
    self.op_tag_key = kwargs["op_tag_key"]
    self.op_kwargs_static = kwargs.get("op_kwargs_static", {})
    self.op_kwargs_update_fn = kwargs.get("op_kwargs_update_fn", None)

  def __str__(self):
    return (
      f"AWSOp {self.op_tag_key} {self.rsrc_type.svc}.{self.op_method_name}"
    )

# 3. Specification Helpers ###################################################


def tag_key_join(tag_key_words):
  """Take a tuple of strings, add a prefix, join, and return a tag key
  """
  return TAG_KEY_DELIM.join((TAG_KEY_PREFIX, ) + tag_key_words)


def update_stack_kwargs(stack_rsrc, update_stack_op):
  """Take a describe_stack item and an operation, return update_stack kwargs

  Preserves previous parameter values except for designated parameter(s):
            Param  value
  .split()  [-2]   [-1]
  sched-set-Enable-true
  sched-set-Enable-false
  """
  change_parameter_key = update_stack_op.op_tag_key.split(TAG_KEY_DELIM)[-2]
  stack_params_out = [{
    "ParameterKey": change_parameter_key,
    "ParameterValue": update_stack_op.op_tag_key.split(TAG_KEY_DELIM)[-1],
  }]
  for stack_param_in in stack_rsrc.get("Parameters", []):
    if stack_param_in["ParameterKey"] != change_parameter_key:
      stack_params_out.append({
        "ParameterKey": stack_param_in["ParameterKey"],
        "UsePreviousValue": True,
      })
  kwargs_out = {
    "UsePreviousTemplate": True,
    "Parameters": stack_params_out,
  }
  stack_capabilities_in = stack_rsrc.get("Capabilities", "")
  if stack_capabilities_in:
    kwargs_out["Capabilities"] = stack_capabilities_in
  return kwargs_out

# 4. Data-Driven Specifications ##############################################


def rsrc_types_init():
  """Create AWS resource type objects when needed, if not already done
  """
  if not AWSChildRsrcType.members:
    AWSChildRsrcType(
      "ec2",
      ("Image", ),
      "Id",
      name_chars_max=128,
      name_chars_unsafe_regexp=r"[^a-zA-Z0-9()[\] ./'@_-]",
      op_kwargs_update_child_fn=lambda child_name, child_tags_list: {
        "Name": child_name,
        "Description": child_name,
        # Set Name and Description, because some Console pages show only one!
        "TagSpecifications": [
          {"Tags": child_tags_list, "ResourceType": "image"},
          {"Tags": child_tags_list, "ResourceType": "snapshot"},
        ],
      },
    )

    AWSChildRsrcType(
      "ec2",
      ("Snapshot", ),
      "Id",
      name_chars_max=255,
      # http://boto3.readthedocs.io/en/latest/reference/services/ec2.html#EC2.Client.create_snapshot
      # No unsafe characters documented for snapshot description
      op_kwargs_update_child_fn=lambda child_name, child_tags_list: {
        "Description": child_name,
        "TagSpecifications": [
          {"Tags": child_tags_list, "ResourceType": "snapshot"},
        ],
      },
    )

    AWSChildRsrcType(
      "rds",
      ("DB", "Snapshot"),
      "Identifier",
      name_chars_max=255,
      name_chars_unsafe_regexp=r"[^a-zA-Z0-9-]|--",
      op_kwargs_update_child_fn=lambda child_name, child_tags_list: {
        "DBSnapshotIdentifier": child_name,
        "Tags": child_tags_list,
      },
    )

    AWSChildRsrcType(
      "rds",
      ("DB", "Cluster", "Snapshot"),
      "Identifier",
      name_chars_max=63,
      name_chars_unsafe_regexp=r"[^a-zA-Z0-9-]|--",
      op_kwargs_update_child_fn=lambda child_name, child_tags_list: {
        "DBClusterSnapshotIdentifier": child_name,
        "Tags": child_tags_list,
      },
    )

  if not AWSParentRsrcType.members:
    AWSParentRsrcType(
      "ec2",
      ("Instance", ),
      "Id",
      status_filter_pair=(
        "instance-state-name", ("running", "stopping", "stopped")
      ),
      flatten_fn=lambda resp: (
        instance
        for reservation in resp["Reservations"]
        for instance in reservation["Instances"]
      ),
      ops={
        ("start", ): {"multiple_rsrcs": True},
        ("reboot", ): {"multiple_rsrcs": True},
        ("stop", ): {"multiple_rsrcs": True},
        ("hibernate", ): {
          "verb": "stop",
          "multiple_rsrcs": True,
          "op_kwargs_static": {"Hibernate": True},
        },
        ("backup", ): {
          "child_rsrc_type": AWSChildRsrcType.members["ec2"]["Image"],
        },
        ("reboot", "backup"): {
          "op_kwargs_static": {"NoReboot": False},
          "child_rsrc_type": AWSChildRsrcType.members["ec2"]["Image"],
        },
      },
    )

    AWSParentRsrcType(
      "ec2",
      ("Volume", ),
      "Id",
      status_filter_pair=("status", ("available", "in-use")),
      ops={
        ("backup", ): {
          "child_rsrc_type": AWSChildRsrcType.members["ec2"]["Snapshot"],
        },
      },
    )

    AWSParentRsrcType(
      "rds",
      ("DB", "Instance"),
      "Identifier",
      ops={
        ("start", ): {},
        ("stop", ): {},
        ("reboot", ): {},
        ("reboot", "failover"): {"op_kwargs_static": {"ForceFailover": True}},
        ("backup", ): {
          "child_rsrc_type": AWSChildRsrcType.members["rds"]["DBSnapshot"],
        },
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
            AWSChildRsrcType.members["rds"]["DBClusterSnapshot"],  # noqa
        },
      },
    )

    AWSParentRsrcType(
      "cloudformation",
      ("Stack", ),
      "Name",
      ops={
        ("set", "Enable", "true"): {
          "verb": "update",
          "op_kwargs_update_fn": update_stack_kwargs,
        },
        ("set", "Enable", "false"): {
          "verb": "update",
          "op_kwargs_update_fn": update_stack_kwargs,
        },
      },
    )


# 5. Shared Lambda Function Handler Code #####################################

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

  Success means that an AWS operation has started, not necessarily that it is
  complete; it may take hours for an image or snapshot to become available.
  Checking completion is left to other tools.
  """
  return all([
    isinstance(resp, dict),
    isinstance(resp.get("ResponseMetadata", None), dict),
    resp["ResponseMetadata"].get("HTTPStatusCode", 0) == 200
  ])

# 6. Find Resources Lambda Function Handler Code #############################


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


def op_tags_match(ops_tag_keys, sched_regexp, rsrc_tags_list):
  """Scan a resource's tags to find operations scheduled for current cycle
  """
  op_tags_matched = []
  for tag_dict in rsrc_tags_list:
    tag_key = tag_dict["Key"]
    if tag_key in ops_tag_keys and sched_regexp.search(tag_dict["Value"]):
      op_tags_matched.append(tag_key)
  return op_tags_matched


def msg_attrs_str_encode(attrs_dict_in):
  """Take an attr_name: attr_value dict, return an SQS messageAttributes dict

  String attributes only!
  """
  return {
    attr_name: {"DataType": "String", "StringValue": attr_value}
    for (attr_name, attr_value) in attrs_dict_in.items()
  }


def msg_body_encode(msg_in):
  """Take an SQS queue message body dict, convert to JSON and check length
  """
  msg_out = json.dumps(msg_in)
  msg_out_len = len(bytes(msg_out, "utf-8"))
  if msg_out_len > QUEUE_MSG_BYTES_MAX:
    raise SQSMessageTooLong(
      f"JSON string too long: {msg_out_len} bytes exceeds "
      f"{QUEUE_MSG_BYTES_MAX} bytes; increase QueueMessageBytesMax "
      "CloudFormation parameter"
    )
  return msg_out


def sqs_send_log(msg_attrs, msg_body, resp=None, exception=None):
  """Log SQS send_message attempt at appropriate level
  """
  log_level = logging.INFO
  if exception is not None:
    log_level = logging.ERROR
    logging.log(
      log_level,
      json.dumps({"type": "EXCEPTION", "exception": exception}, default=str)
    )
  if resp is not None:
    if not boto3_success(resp):
      log_level = logging.ERROR
    logging.log(
      log_level,
      json.dumps({"type": "AWS_RESPONSE", "aws_response": resp}, default=str)
    )
  logging.log(
    log_level,
    json.dumps(
      {"type": "SQS_MSG", "msg_attrs": msg_attrs, "msg_body": msg_body},
      default=str
  ))


def op_queue(svc, op_method_name, op_kwargs, cycle_cutoff_epoch_str):
  """Send an operation message to the SQS queue
  """
  op_msg_attrs = msg_attrs_str_encode({
    "version": QUEUE_MSG_FMT_VERSION,
    "expires": cycle_cutoff_epoch_str,
    "svc": svc,
    "op_method_name": op_method_name,
  })
  try:
    sqs_resp = svc_client_get("sqs").send_message(
      QueueUrl=QUEUE_URL,
      MessageAttributes=op_msg_attrs,
      MessageBody=msg_body_encode(op_kwargs),
    )
  except (
    botocore.exceptions.ClientError,
    SQSMessageTooLong,
  ) as sqs_exception:
    sqs_send_log(op_msg_attrs, op_kwargs, exception=sqs_exception)
    # Usually recoverable, try to queue next operation
  except Exception:
    sqs_send_log(op_msg_attrs, op_kwargs)
    raise  # Unrecoverable, stop queueing operations
  else:
    sqs_send_log(op_msg_attrs, op_kwargs, resp=sqs_resp)


def unique_suffix(
  char_count=5,
  chars_allowed="acefgrtxy3478"  # Small but unambiguous; more varied:
  # chars_allowed=string.ascii_lowercase + string.digits
  # http://pwgen.cvs.sourceforge.net/viewvc/pwgen/src/pw_rand.c
  # https://ux.stackexchange.com/questions/21076
):
  """Return a string of random characters
  """
  return "".join(random.choice(chars_allowed) for dummy in range(char_count))


def op_kwargs_child(
  parent_id,
  parent_tags_list,
  op,
  cycle_start_str,
  child_name_prefix=f"z{TAG_KEY_PREFIX}",
  name_delim=TAG_KEY_DELIM,
  base_name_chars=23,
  fill_char="X"
):  # pylint: disable=too-many-arguments
  """Return boto3 _create method kwargs (name, tags) for an image or snapshot

  Child resource name example: zsched-ParentNameOrID-20221101T1450Z-acefg
  - Prefix, for sorting and grouping in Console ("z..." will sort last)
  - Use ISO 8601 date and time, for sorting, grouping, and search
  - Identify parent resource by its Name tag value (an EC2 convention) or ID
  - Add random suffix to make name collisions nearly impossible
  - Truncate parent portion to spare other parts of child name
  """
  child_tags_list = []
  parent_name_from_tag = ""
  for parent_tag_dict in parent_tags_list:
    parent_tag_key = parent_tag_dict["Key"]
    if parent_tag_key == "Name":
      parent_name_from_tag = parent_tag_dict["Value"]
      if not COPY_TAGS:
        break  # Stop as soon as Name tag has been found
    elif not re.match(TAG_KEYS_NO_COPY_REGEXP, parent_tag_key):
      child_tags_list.append(parent_tag_dict)

  parent_name = parent_name_from_tag if parent_name_from_tag else parent_id
  parent_name = parent_name[
    :op.child_rsrc_type.name_chars_max - base_name_chars
  ]

  # base_name_chars should be the length of this string join, but with "" for
  # parent_name (to leave space for prefix, timestamp, and random suffix):
  child_name = name_delim.join([
    child_name_prefix, parent_name, cycle_start_str, unique_suffix()
  ])
  if op.child_rsrc_type.name_chars_unsafe_regexp:
    child_name = re.sub(
      op.child_rsrc_type.name_chars_unsafe_regexp, fill_char, child_name
    )

  for (child_tag_key, child_tag_value) in (
    ("Name", child_name),  # Shown in EC2 Console / searchable in any service
    (tag_key_join(("cycle", "start")), cycle_start_str),
    (tag_key_join(("parent", "id")), parent_id),
    (tag_key_join(("parent", "name")), parent_name_from_tag),
    (tag_key_join(("op", )), op.op_tag_key),
  ):
    child_tags_list.append({"Key": child_tag_key, "Value": child_tag_value})

  return op.child_rsrc_type.op_kwargs_update_child_fn(
    child_name, child_tags_list
  )


def rsrcs_find(
  rsrc_type, sched_regexp, cycle_start_str, cycle_cutoff_epoch_str
):  # pylint: disable=too-many-arguments
  """Find parent resources to operate on, and send details to queue.
  """

  paginator = svc_client_get(rsrc_type.svc).get_paginator(
    rsrc_type.describe_method_name
  )
  for resp in paginator.paginate(**rsrc_type.describe_kwargs):
    if rsrc_type.flatten_fn:
      rsrcs = rsrc_type.flatten_fn(resp)
    else:
      rsrcs = resp[rsrc_type.rsrcs_key]
    for rsrc in rsrcs:

      rsrc_id = rsrc[rsrc_type.rsrc_id_key]
      rsrc_tags_list = rsrc.get("Tags", rsrc.get("TagList", []))
      # EC2, CloudFormation: "Tags"; RDS: "TagList"; key omitted if no tags!
      op_tags_matched = op_tags_match(
        rsrc_type.ops_tag_keys, sched_regexp, rsrc_tags_list
      )
      op_tags_matched_count = len(op_tags_matched)

      if op_tags_matched_count == 1:
        op = rsrc_type.ops[op_tags_matched[0]]
        if op.multiple_rsrcs:
          # One resource at a time, to avoid partial completion risk
          op_kwargs = {rsrc_type.rsrc_ids_key: [rsrc_id]}
        else:
          op_kwargs = {rsrc_type.rsrc_id_key: rsrc_id}
        op_kwargs.update(op.op_kwargs_static)
        if op.op_kwargs_update_fn:
          op_kwargs.update(op.op_kwargs_update_fn(rsrc, op))
        if op.child_rsrc_type:
          op_kwargs.update(op_kwargs_child(
            rsrc_id, rsrc_tags_list, op, cycle_start_str
          ))
        op_queue(
          rsrc_type.svc, op.op_method_name, op_kwargs, cycle_cutoff_epoch_str
        )

      elif op_tags_matched_count > 1:
        logging.error(json.dumps({
          "type": "MULTIPLE_OPS",
          "svc": rsrc_type.svc,
          "rsrc_type": rsrc_type.rsrc_key,
          "rsrc_id": rsrc_id,
          "op_tags_matched": op_tags_matched,
          "cycle_start_str": cycle_start_str,
        }))


def lambda_handler_find(event, context):  # pylint: disable=unused-argument
  """Find and queue AWS resources for scheduled operations, based on tags
  """
  logging.info(
    json.dumps({"type": "LAMBDA_EVENT", "lambda_event": event}, default=str)
  )
  (cycle_start, cycle_cutoff) = cycle_start_end(
    datetime.datetime.now(datetime.timezone.utc)
  )
  cycle_start_str = cycle_start.strftime("%Y%m%dT%H%MZ")
  cycle_cutoff_epoch_str = str(int(cycle_cutoff.timestamp()))
  sched_regexp = re.compile(
    cycle_start.strftime(SCHED_REGEXP_STRFTIME_FMT), re.VERBOSE
  )
  logging.info(json.dumps({"type": "START", "cycle_start": cycle_start_str}))
  logging.info(json.dumps(
    {"type": "SCHED_REGEXP_VERBOSE", "sched_regexp": sched_regexp.pattern}
  ))
  rsrc_types_init()
  for rsrc_types in AWSParentRsrcType.members.values():
    for rsrc_type in rsrc_types.values():
      rsrcs_find(
        rsrc_type, sched_regexp, cycle_start_str, cycle_cutoff_epoch_str
      )

# 7. "Do" Operations Lambda Function Handler Code ############################


def msg_attr_str_decode(msg, attr_name):
  """Take an SQS message, return value of a string attribute (must be present)
  """
  return msg["messageAttributes"][attr_name]["stringValue"]


def op_log(event, resp=None, log_level=logging.ERROR):
  """Log Lambda function event and AWS SDK method call response
  """
  logging.log(
    log_level,
    json.dumps({"type": "LAMBDA_EVENT", "lambda_event": event}, default=str)
  )
  if resp is not None:
    logging.log(
      log_level,
      json.dumps({"type": "AWS_RESPONSE", "aws_response": resp}, default=str)
    )


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
    else:
      if boto3_success(resp):
        op_log(event, resp=resp, log_level=logging.INFO)
      else:
        op_log(event, resp=resp)
        raise RuntimeError("Miscellaneous AWS erorr")
