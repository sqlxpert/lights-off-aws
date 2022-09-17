#!/usr/bin/env python3
"""Start, reboot, stop and back up AWS resources using schedules in tags

github.com/sqlxpert/lights-off-aws  GPLv3  Copyright Paul Marcelin
"""

import os
import logging
import datetime
import re
import json
import random
import botocore
import boto3

logging.getLogger().setLevel(os.environ.get("LOG_LEVEL", logging.ERROR))

SCHED_DELIM_CHAR = r" "
SCHED_DELIMS = rf"{SCHED_DELIM_CHAR}+"
SCHED_TERMS = (
  rf"([^{SCHED_DELIM_CHAR}]+=[^{SCHED_DELIM_CHAR}]+{SCHED_DELIMS})*"
)
SCHED_REGEXP_STRFTIME_FMT = (
  rf"(^|{SCHED_DELIMS})"
  rf"((dTH:M=%d|uTH:M=%u)T%H:%M"
  rf"|"
  rf"(d=(_|%d)|u=(_|%u)){SCHED_DELIMS}"
  rf"{SCHED_TERMS}"
  rf"((H:M=%H:%M)|(H=(_|%H){SCHED_DELIMS}{SCHED_TERMS}M=%M)))"
  rf"({SCHED_DELIMS}|$)"
)

QUEUE_URL = os.environ.get("QUEUE_URL", "")
QUEUE_MSG_BYTES_MAX = int(os.environ.get("QUEUE_MSG_BYTES_MAX", "-1"))
QUEUE_MSG_FMT_VERSION = "01"

TAG_KEY_PREFIX = "sched"
TAG_KEY_DELIM = "-"
TAG_KEYS_NO_INHERIT_REGEXP = (
  rf"^((aws|ec2|rds):|{TAG_KEY_PREFIX}{TAG_KEY_DELIM})"
)


# 1. Custom Exceptions #######################################################

class SQSMessageTooLong(ValueError):
  """JSON-encoded SQS queue message exceeds QUEUE_MSG_BYTES_MAX
  """


# 2. Specification Helpers ###################################################


def tag_key_join(*args):
  """Take any number of strings, add a prefix, join, and return a tag key
  """
  return TAG_KEY_DELIM.join([TAG_KEY_PREFIX] + list(args))


def describe_kwargs_make(status_filter_pairs):
  """Take (filter, values) pairs, return boto3 _describe method kwargs
  """
  return {
    "Filters": [
      {"Name": filter_name, "Values": list(filter_values)}
      for (filter_name, filter_values) in status_filter_pairs
    ]
  }


def stack_update_kwargs_make(stack_rsrc, update_stack_op):
  """Take a describe_stack item and an operation, return update_stack kwargs

  Preserves previous parameter values except for Enabled, whose value is set
  to "true" or "false" (strings, because CloudFormation does lacks a Boolean
  parameter type) depending on the operation.
  """
  stack_params_out = [{
    "ParameterKey": "Enabled",
    "ParameterValue": update_stack_op.split(TAG_KEY_DELIM)[-1],  # -true/false
  }]
  for stack_param_in in stack_rsrc.get("Parameters", []):
    if stack_param_in["ParameterKey"] != "Enabled":
      stack_params_out.append({
        "ParameterKey": stack_param_in["ParameterKey"],
        "UsePreviousValue": True,
      })
  return {
    "UsePreviousTemplate": True,
    "Parameters": stack_params_out,
  }

# 3. Data-Driven Specifications ##############################################

# Hierarchical dicts specify:
#  - search conditions for AWS resources (instances, volumes, stacks)
#  - operations supported
#  - rules for naming and tagging child resources (images, snapshots)
# SPECS_CHILD / SPECS structure:
#   AWS service - string (svc):
#     AWS resource type - tuple of strings (rsrc_type_words):
#       specification key - string:
#         specification value - type varies


SPECS_CHILD = {
  "ec2": {

    ("Image", ): {
      "op_kwargs_update_child_fn": lambda child_name, child_tags_list: {
        "Name": child_name,
        "Description": child_name,
        # Set Name and Description, because some Console pages show only one!
        "TagSpecifications": [
          {"Tags": child_tags_list, "ResourceType": "image"},
          {"Tags": child_tags_list, "ResourceType": "snapshot", },
        ],
      },
      "name_chars_unsafe_regexp": r"[^a-zA-Z0-9()[\] ./'@_-]",
      "name_chars_max": 128,
    },

    ("Snapshot", ): {
      "op_kwargs_update_child_fn": lambda child_name, child_tags_list: {
        "Description": child_name,
        "TagSpecifications": [
          {"Tags": child_tags_list, "ResourceType": "snapshot"},
        ],
      },
      # http://boto3.readthedocs.io/en/latest/reference/services/ec2.html#EC2.Client.create_snapshot
      # No unsafe characters documented for snapshot description
      "name_chars_max": 255,
    },

  },
  "rds": {

    ("DB", "Snapshot"): {
      "op_kwargs_update_child_fn": lambda child_name, child_tags_list: {
        "DBSnapshotIdentifier": child_name,
        "Tags": child_tags_list,
      },
      "name_chars_unsafe_regexp": r"[^a-zA-Z0-9-]|--",
      "name_chars_max": 255,
    },

    ("DB", "Cluster", "Snapshot"): {
      "op_kwargs_update_child_fn": lambda child_name, child_tags_list: {
        "DBClusterSnapshotIdentifier": child_name,
        "Tags": child_tags_list,
      },
      "name_chars_unsafe_regexp": r"[^a-zA-Z0-9-]|--",
      "name_chars_max": 63,
    },
  },

}
SPECS = {
  "ec2": {

    ("Instance", ): {
      "status_filter_pair": (
        "instance-state-name", ("running", "stopping", "stopped")
      ),
      "flatten_fn": lambda resp: (
        instance
        for reservation in resp["Reservations"]
        for instance in reservation["Instances"]
      ),
      "rsrc_id_key_suffix": "Id",
      "ops": {
        tag_key_join("start"): {"op_method_name": "start_instances"},
        tag_key_join("reboot"): {"op_method_name": "reboot_instances"},
        tag_key_join("stop"): {"op_method_name": "stop_instances"},
        tag_key_join("hibernate"): {
          "op_method_name": "stop_instances",
          "op_kwargs_static": {"Hibernate": True},
        },
        tag_key_join("backup"): {
          "op_method_name": "create_image",
          "specs_child_rsrc_type": SPECS_CHILD["ec2"][("Image", )],
        },
        tag_key_join("reboot", "backup"): {
          "op_method_name": "create_image",
          "op_kwargs_static": {"NoReboot": False},
          "specs_child_rsrc_type": SPECS_CHILD["ec2"][("Image", )],
        },
      },
    },

    ("Volume", ): {
      "status_filter_pair": ("status", ("available", "in-use")),
      "rsrc_id_key_suffix": "Id",
      "ops": {
        tag_key_join("backup"): {
          "op_method_name": "create_snapshot",
          "specs_child_rsrc_type": SPECS_CHILD["ec2"][("Snapshot", )],
        },
      },
    },

  },
  "rds": {

    ("DB", "Instance"): {
      "rsrc_id_key_suffix": "Identifier",
      "ops": {
        tag_key_join("start"): {"op_method_name": "start_db_instance"},
        tag_key_join("stop"): {"op_method_name": "stop_db_instance"},
        tag_key_join("reboot"): {"op_method_name": "reboot_db_instance"},
        tag_key_join("reboot", "failover"): {
          "op_method_name": "reboot_db_instance",
          "op_kwargs_static": {"ForceFailover": True},
        },
        tag_key_join("backup"): {
          "op_method_name": "create_db_snapshot",
          "specs_child_rsrc_type": SPECS_CHILD["rds"][("DB", "Snapshot")],
        },
      },
    },

    ("DB", "Cluster"): {
      "rsrc_id_key_suffix": "Identifier",
      "ops": {
        tag_key_join("start"): {"op_method_name": "start_db_cluster"},
        tag_key_join("stop"): {"op_method_name": "stop_db_cluster"},
        tag_key_join("reboot"): {"op_method_name": "reboot_db_cluster"},
        tag_key_join("backup"): {
          "op_method_name": "create_db_cluster_snapshot",
          "specs_child_rsrc_type": SPECS_CHILD["rds"][
            ("DB", "Cluster", "Snapshot")
          ],
        },
      },
    },

  },
  "cloudformation": {

    ("Stack", ): {
      "rsrc_id_key_suffix": "Name",
      "ops": {
        tag_key_join("enabled", "true"): {
          "op_method_name": "update_stack",
          "op_kwargs_update_fn": stack_update_kwargs_make,
        },
        tag_key_join("enabled", "false"): {
          "op_method_name": "update_stack",
          "op_kwargs_update_fn": stack_update_kwargs_make,
        },
      },
    },

  },
}

# 4. Shared Lambda Function Handler Code #####################################

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
    isinstance(resp.get("ResponseMetadata"), dict),
    resp.get("ResponseMetadata", {}).get("HTTPStatusCode", 0) == 200
  ])

# 5. Find Resources Lambda Function Handler Code #############################


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


def op_tags_match(ops_tag_keys, sched_regexp, tags_list):
  """Scan tags to determine which operations are scheduled for current cycle
  """
  op_tags_matched = []
  for tag_dict in tags_list:
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
      f"JSON string too long: {msg_out_len} exceeds {QUEUE_MSG_BYTES_MAX}; "
      f"increase QUEUE_MSG_BYTES_MAX\n"
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
    # Recoverable, try to queue next operation
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
  specs_child_rsrc_type,
  cycle_start_str,
  child_name_prefix=f"z{TAG_KEY_PREFIX}",
  name_delim=TAG_KEY_DELIM,
  base_name_chars=23,
  unsafe_char_fill="X"
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
    elif not re.match(TAG_KEYS_NO_INHERIT_REGEXP, parent_tag_key):
      child_tags_list.append(parent_tag_dict)

  parent_name = parent_name_from_tag if parent_name_from_tag else parent_id
  parent_name = parent_name[
    :specs_child_rsrc_type["name_chars_max"] - base_name_chars
  ]

  # base_name_chars should be the length of this string join, but with "" for
  # parent_name (to leave space for prefix, timestamp, and random suffix):
  child_name = name_delim.join([
    child_name_prefix, parent_name, cycle_start_str, unique_suffix()
  ])
  if "name_chars_unsafe_regexp" in specs_child_rsrc_type:
    child_name = re.sub(
      specs_child_rsrc_type["name_chars_unsafe_regexp"],
      unsafe_char_fill,
      child_name
    )

  for (child_tag_key, child_tag_value) in (
    ("Name", child_name),  # Shown in EC2 Console / searchable in any service
    (tag_key_join("cycle", "start"), cycle_start_str),
    (tag_key_join("parent", "id"), parent_id),
    (tag_key_join("parent", "name"), parent_name_from_tag),
    (tag_key_join("op"), op),
  ):
    child_tags_list.append({"Key": child_tag_key, "Value": child_tag_value})

  return specs_child_rsrc_type["op_kwargs_update_child_fn"](
    child_name, child_tags_list
  )


def rsrcs_find(
  svc,
  rsrc_type_words,
  specs_rsrc_type,
  sched_regexp,
  cycle_start_str,
  cycle_cutoff_epoch_str
):  # pylint: disable=too-many-arguments,too-many-locals
  """Find parent resources to operate on, and send details to queue.
  """
  rsrc_type_in_method_name = "_".join(rsrc_type_words).lower()
  describe_method_name = f"describe_{rsrc_type_in_method_name}s"

  rsrc_type_in_keys = "".join(rsrc_type_words)
  rsrcs_key = f"{rsrc_type_in_keys}s"
  rsrc_id_key = rsrc_type_in_keys + specs_rsrc_type["rsrc_id_key_suffix"]
  rsrc_ids_key = f"{rsrc_id_key}s"

  ops_tag_keys = specs_rsrc_type["ops"].keys()

  if "status_filter_pair" in specs_rsrc_type:
    describe_kwargs = describe_kwargs_make((
      specs_rsrc_type["status_filter_pair"], ("tag-key", ops_tag_keys)
    ))
  else:
    describe_kwargs = {}

  paginator = svc_client_get(svc).get_paginator(describe_method_name)
  for resp in paginator.paginate(**describe_kwargs):
    if "flatten_fn" in specs_rsrc_type:
      rsrcs = specs_rsrc_type["flatten_fn"](resp)
    else:
      rsrcs = resp[rsrcs_key]
    for rsrc in rsrcs:

      rsrc_id = rsrc[rsrc_id_key]
      tags_list = rsrc.get("Tags", rsrc.get("TagList", []))
      # EC2, CloudFormation: "Tags"; RDS: "TagList"; key omitted if no tags!
      op_tags_matched = op_tags_match(ops_tag_keys, sched_regexp, tags_list)
      op_tags_matched_count = len(op_tags_matched)

      if op_tags_matched_count == 1:
        op = op_tags_matched[0]
        specs_op = specs_rsrc_type["ops"][op]
        op_method_name = specs_op["op_method_name"]
        if op_method_name[-1] == "s":
          # One resource at a time, to avoid partial completion risk
          op_kwargs = {rsrc_ids_key: [rsrc_id]}
        else:
          op_kwargs = {rsrc_id_key: rsrc_id}
        op_kwargs.update(specs_op.get("op_kwargs_static", {}))
        if "op_kwargs_update_fn" in specs_op:
          op_kwargs.update(specs_op["op_kwargs_update_fn"](rsrc, op))
        if "specs_child_rsrc_type" in specs_op:
          op_kwargs.update(op_kwargs_child(
            rsrc_id,
            tags_list,
            op,
            specs_op["specs_child_rsrc_type"],
            cycle_start_str
          ))
        op_queue(
          svc, op_method_name, op_kwargs, cycle_cutoff_epoch_str
        )

      elif op_tags_matched_count > 1:
        logging.error(json.dumps({
          "type": "MULTIPLE_OPS",
          "svc": svc,
          "rsrc_type": rsrc_type_in_keys,
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
  sched_regexp = re.compile(cycle_start.strftime(SCHED_REGEXP_STRFTIME_FMT))
  logging.info(json.dumps({"type": "START", "cycle_start": cycle_start_str}))
  logging.info(json.dumps(
    {"type": "SCHED_REGEXP", "sched_regexp": sched_regexp}, default=str
  ))

  for (svc, specs_svc) in SPECS.items():
    for (rsrc_type_words, specs_rsrc_type) in specs_svc.items():
      rsrcs_find(
        svc,
        rsrc_type_words,
        specs_rsrc_type,
        sched_regexp,
        cycle_start_str,
        cycle_cutoff_epoch_str
      )

# 6. "Do" Operations Lambda Function Handler Code ############################


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
      int(datetime.datetime.now(datetime.timezone.utc).timestamp())
      > int(msg_attr_str_decode(msg, "expires"))
    ):
      op_log(event)
      raise RuntimeError("Late; schedule fewer operations per 10-min cycle")

    svc_client = svc_client_get(msg_attr_str_decode(msg, "svc"))
    op_method = getattr(svc_client, msg_attr_str_decode(msg, "op_method_name"))
    op_kwargs = json.loads(msg["body"])
    try:
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


# TODO: Remove (testing only)
if __name__ == "__main__":
  lambda_handler_find(None, None)
