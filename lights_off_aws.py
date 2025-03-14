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
SCHED_TERMS = rf"([^ ]+{SCHED_DELIMS})*"  # Unescaped space inside class
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

QUEUE_URL = os.environ.get("QUEUE_URL", "")
QUEUE_MSG_BYTES_MAX = int(os.environ.get("QUEUE_MSG_BYTES_MAX", "-1"))
QUEUE_MSG_FMT_VERSION = "01"

TAG_KEY_PREFIX = "sched"
TAG_KEY_DELIM = "-"
TAG_KEYS_NEVER_COPY_REGEXP = (
  rf"^((aws|ec2|rds):|{TAG_KEY_PREFIX}{TAG_KEY_DELIM})"
)
# pylint: disable=superfluous-parens
COPY_TAGS = (os.environ.get("COPY_TAGS", "").lower() == "true")


# 1. Custom Exceptions #######################################################

class SQSMessageTooLong(ValueError):
  """JSON-encoded SQS queue message exceeds QUEUE_MSG_BYTES_MAX
  """

# 2. Helpers #################################################################


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
  return TAG_KEY_DELIM.join((TAG_KEY_PREFIX, ) + tag_key_words)


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


def msg_attrs_str_encode(attr_pairs):
  """Take a list of name, value pairs, return an SQS messageAttributes dict

  String attributes only!
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

# 3. Custom Classes ##########################################################

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
    self.create_kwargs = kwargs["create_kwargs"]
    self.__class__.members[svc][self.rsrc_key] = self  # Register self!


class AWSParentRsrcType(AWSRsrcType):
  """AWS parent resource type, supporting various operations
  """
  members = collections.defaultdict(dict)

  def __init__(self, svc, rsrc_type_words, rsrc_id_key_suffix, **kwargs):
    super().__init__(svc, rsrc_type_words, rsrc_id_key_suffix)
    self.describe_method_name = f"describe_{self.rsrc_type_in_methods}s"
    self.status_filter_pair = kwargs.get("status_filter_pair", ())
    self.describe_flatten = kwargs.get("describe_flatten", None)
    self.ops = {}
    for (op_tag_key_words, op_properties) in kwargs["ops"].items():
      AWSOp.new(self, op_tag_key_words, **op_properties)
    self.__class__.members[svc][self.rsrc_key] = self  # Register self!

  # pylint: disable=missing-function-docstring

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

  def rsrc_id(self, rsrc):
    """Return a resource's ID, using the key for the resource type
    """
    return rsrc[self.rsrc_id_key]

  def rsrc_tags_list(self, rsrc):  # pylint: disable=no-self-use
    """Return a resource's raw-format list of tags

    Currently generic using .get(), but could be specialized by rsrc_type

    Key        Services
    "Tags"     EC2, CloudFormation
    "TagList"  RDS

    Key may be omitted if no tags are present
    """
    return rsrc.get("Tags", rsrc.get("TagList", []))

  def op_tags_match(self, rsrc, sched_regexp):
    """Scan a resource's tags to find operations scheduled for current cycle
    """
    ops_tag_keys = self.ops_tag_keys
    op_tags_matched = []
    for tag_dict in self.rsrc_tags_list(rsrc):
      tag_key = tag_dict["Key"]
      if tag_key in ops_tag_keys and sched_regexp.search(tag_dict["Value"]):
        op_tags_matched.append(tag_key)
    return op_tags_matched

  def rsrcs_find(self, sched_regexp, cycle_start_str, cycle_cutoff_epoch_str):
    """Find parent resources to operate on, and send details to queue
    """
    paginator = svc_client_get(self.svc).get_paginator(
      self.describe_method_name
    )
    for resp in paginator.paginate(**self.describe_kwargs):
      if self.describe_flatten:
        rsrcs = self.describe_flatten(resp)
      else:
        rsrcs = resp.get(self.rsrcs_key, [])
      for rsrc in rsrcs:
        op_tags_matched = self.op_tags_match(rsrc, sched_regexp)
        op_tags_matched_count = len(op_tags_matched)

        if op_tags_matched_count == 1:
          op = self.ops[op_tags_matched[0]]
          op_kwargs = op.op_kwargs(rsrc, cycle_start_str)
          op.queue(op_kwargs, cycle_cutoff_epoch_str)

        elif op_tags_matched_count > 1:
          logging.error(json.dumps({
            "type": "MULTIPLE_OPS",
            "svc": self.svc,
            "rsrc_type": self.rsrc_key,
            "rsrc_id": self.rsrc_id(rsrc),
            "op_tags_matched": op_tags_matched,
            "cycle_start_str": cycle_start_str,
          }))


class AWSOp():
  """Operation on an AWS resource of particular type
  """
  def __init__(self, rsrc_type, tag_key_words, **kwargs):
    self.rsrc_type = rsrc_type
    self.tag_key_words = tag_key_words
    self.tag_key = tag_key_join(tag_key_words)
    verb = kwargs.get("verb", tag_key_words[0])  # Default: 1st tag key word
    self.method_name = f"{verb}_{self.rsrc_type.rsrc_type_in_methods}"
    self.kwargs_static = kwargs.get("kwargs_static", {})
    self.kwargs_dynamic = kwargs.get("kwargs_dynamic", None)
    self.rsrc_type.ops[self.tag_key] = self  # Register in parent AWSRsrcType!

  @staticmethod
  def new(rsrc_type, tag_key_words, **kwargs):
    """Create an op of the requested, appropriate, or default (sub)class
    """
    op_class = kwargs.get(
      "class",
      AWSOpChildOut if "child_rsrc_type" in kwargs else AWSOp
    )
    return op_class(rsrc_type, tag_key_words, **kwargs)

  def update_stack_kwargs(self, stack_rsrc):
    """Take an operation and a describe_stack item, return update_stack kwargs

    Preserves previous parameter values except for designated parameter(s):
                             Param  New
                             Key    Value
    tag_key        sched-set-Enable-true
    tag_key        sched-set-Enable-false
    tag_key_words            [-2]   [-1]
    """
    changing_parameter_key = self.tag_key_words[-2]
    stack_parameters_out = [{
      "ParameterKey": changing_parameter_key,
      "ParameterValue": self.tag_key_words[-1],
    }]
    for stack_parameter_in in stack_rsrc.get("Parameters", []):
      if stack_parameter_in["ParameterKey"] != changing_parameter_key:
        stack_parameters_out.append({
          "ParameterKey": stack_parameter_in["ParameterKey"],
          "UsePreviousValue": True,
        })
    update_stack_kwargs_out = {
      "UsePreviousTemplate": True,
      "Parameters": stack_parameters_out,
    }
    stack_capabilities_in = stack_rsrc.get("Capabilities", [])
    if stack_capabilities_in:
      update_stack_kwargs_out["Capabilities"] = stack_capabilities_in
    return update_stack_kwargs_out

  def kwargs_rsrc_id(self, rsrc):
    """Transfer a describe_ item's ID, to start kwargs
    """
    return {self.rsrc_type.rsrc_id_key: self.rsrc_type.rsrc_id(rsrc)}

  # pylint: disable=unused-argument
  def op_kwargs(self, rsrc, cycle_start_str):
    """Transfer a describe_ item's ID, then add static and kwargs
    """
    op_kwargs_out = self.kwargs_rsrc_id(rsrc)
    op_kwargs_out.update(self.kwargs_static)
    if self.kwargs_dynamic:
      op_kwargs_out.update((self.kwargs_dynamic)(self, rsrc))
    return op_kwargs_out

  def queue(self, op_kwargs, cycle_cutoff_epoch_str):
    """Send an operation message to the SQS queue
    """
    op_msg_attrs = msg_attrs_str_encode((
      ("version", QUEUE_MSG_FMT_VERSION),
      ("expires", cycle_cutoff_epoch_str),
      ("svc", self.rsrc_type.svc),
      ("op_method_name", self.method_name),
    ))
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

  def __str__(self):
    return f"AWSOp {self.tag_key} {self.rsrc_type.svc}.{self.method_name}"


class AWSOpMultipleIn(AWSOp):
  """Operation on multiple AWS resources of a particular type
  """
  def __init__(self, rsrc_type, tag_key_words, **kwargs):
    super().__init__(rsrc_type, tag_key_words, **kwargs)
    self.method_name = self.method_name + "s"

  def kwargs_rsrc_id(self, rsrc):
    """Transfer a describe_ item's ID, to start kwargs

    One resource at a time for uniformity and to avoid partial completion risk
    """
    return {self.rsrc_type.rsrc_ids_key: [self.rsrc_type.rsrc_id(rsrc)]}


class AWSOpChildOut(AWSOp):
  """Operation on an AWS resource of particular type, creating child resource
  """
  def __init__(self, rsrc_type, tag_key_words, **kwargs):
    verb = "create"
    super().__init__(rsrc_type, tag_key_words, **(kwargs | {"verb": verb}))
    self.child_rsrc_type = kwargs["child_rsrc_type"]
    self.method_name = f"{verb}_{self.child_rsrc_type.rsrc_type_in_methods}"

  def create_kwargs(
    self,
    parent_rsrc,
    cycle_start_str,
    child_name_prefix=f"z{TAG_KEY_PREFIX}",
    name_delim=TAG_KEY_DELIM,
    base_name_chars=23,
    fill_char="X"
  ):  # pylint: disable=too-many-positional-arguments,too-many-arguments
    """Return create_ method kwargs (name, tags) for an image or snapshot

    Calls specific create_kwargs method of child_rsrc_type being created

    Child resource name example: zsched-ParentNameOrID-20221101T1450Z-acefg
    Truncate parent portion to spare other parts of child name.
    """
    child_tags_list = []
    parent_name_from_tag = ""
    for parent_tag_dict in self.rsrc_type.rsrc_tags_list(parent_rsrc):
      parent_tag_key = parent_tag_dict["Key"]
      if parent_tag_key == "Name":
        parent_name_from_tag = parent_tag_dict["Value"]
        if not COPY_TAGS:
          break  # Stop as soon as Name tag has been found
      elif not re.match(TAG_KEYS_NEVER_COPY_REGEXP, parent_tag_key):
        child_tags_list.append(parent_tag_dict)

    parent_id = self.rsrc_type.rsrc_id(parent_rsrc)
    parent_name = parent_name_from_tag if parent_name_from_tag else parent_id
    parent_name = parent_name[
      :self.child_rsrc_type.name_chars_max - base_name_chars
    ]

    # base_name_chars should be the length of this string join, but with "" for
    # parent_name (to leave space for prefix, timestamp, and random suffix):
    child_name = name_delim.join([
      child_name_prefix, parent_name, cycle_start_str, unique_suffix()
    ])
    if self.child_rsrc_type.name_chars_unsafe_regexp:
      child_name = re.sub(
        self.child_rsrc_type.name_chars_unsafe_regexp, fill_char, child_name
      )

    for (child_tag_key, child_tag_value) in (
      ("Name", child_name),  # Shown in EC2 Console / searchable in any service
      (tag_key_join(("cycle", "start")), cycle_start_str),
      (tag_key_join(("parent", "id")), parent_id),
      (tag_key_join(("parent", "name")), parent_name_from_tag),
      (tag_key_join(("op", )), self.tag_key),
    ):
      child_tags_list.append({"Key": child_tag_key, "Value": child_tag_value})

    return self.child_rsrc_type.create_kwargs(child_name, child_tags_list)

  def op_kwargs(self, rsrc, cycle_start_str):
    """Add kwargs for child resource creation
    """
    op_kwargs_out = super().op_kwargs(rsrc, cycle_start_str)
    op_kwargs_out.update(self.create_kwargs(rsrc, cycle_start_str))
    return op_kwargs_out


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
      create_kwargs=lambda child_name, child_tags_list: {
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
      create_kwargs=lambda child_name, child_tags_list: {
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
      name_chars_unsafe_regexp=r"[^a-zA-Z0-9-]|--+",
      create_kwargs=lambda child_name, child_tags_list: {
        "DBSnapshotIdentifier": child_name,
        "Tags": child_tags_list,
      },
    )

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

  if not AWSParentRsrcType.members:
    AWSParentRsrcType(
      "ec2",
      ("Instance", ),
      "Id",
      status_filter_pair=(
        "instance-state-name", ("running", "stopping", "stopped")
      ),
      describe_flatten=lambda resp: (
        instance
        for reservation in resp.get("Reservations", [])
        for instance in reservation.get("Instances", [])
      ),
      ops={
        ("start", ): {"class": AWSOpMultipleIn},
        ("reboot", ): {"class": AWSOpMultipleIn},
        ("stop", ): {"class": AWSOpMultipleIn},
        ("hibernate", ): {
          "class": AWSOpMultipleIn,
          "verb": "stop",
          "kwargs_static": {"Hibernate": True},
        },
        ("backup", ): {
          "child_rsrc_type": AWSChildRsrcType.members["ec2"]["Image"],
        },
        ("reboot", "backup"): {
          "kwargs_static": {"NoReboot": False},
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
        ("reboot", "failover"): {"kwargs_static": {"ForceFailover": True}},
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
          "kwargs_dynamic": AWSOp.update_stack_kwargs,
        },
        ("set", "Enable", "false"): {
          "verb": "update",
          "kwargs_dynamic": AWSOp.update_stack_kwargs,
        },
      },
    )


# 5. Find Resources Lambda Function Handler ##################################


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
