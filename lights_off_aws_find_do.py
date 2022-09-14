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

# 1. Specification Helpers ###################################################


def tag_key_join(*args):
  """Take any number of strings, add a prefix, join, and return a tag key
  """
  return TAG_KEY_DELIM.join([TAG_KEY_PREFIX] + list(args))


def describe_kwargs_make(filters_dict_in):
  """Take a filter: vals dict, return boto3 _describe method kwargs
  """
  return {
    "Filters": [
      {"Name": filter_name, "Values": filter_values}
      for (filter_name, filter_values) in filters_dict_in.items()
    ]
  }


def stack_update_kwargs_make(stack_rsrc, stack_op):
  """Take a describe_stack item and an operation, return update_stack kwargs

  Preserves previous parameter values except for Toggle, whose value is set to
  "true" or "false" (strings, because CloudFormation does lacks a Boolean
  parameter type) depending on the operation.

  op MUST be PREFIX-toggle-param-true or -false!
  """
  stack_params_out = [{
    "ParameterKey": "Toggle",
    "ParameterValue": stack_op.split(TAG_KEY_DELIM)[-1],  # "true" or "false"
  }]
  for stack_param_in in stack_rsrc.get("Parameters", []):
    if stack_param_in["ParameterKey"] != "Toggle":
      stack_params_out.append({
        "ParameterKey": stack_param_in["ParameterKey"],
        "UsePreviousValue": True,
      })
  return {
    "UsePreviousTemplate": True,
    "Parameters": stack_params_out,
  }

# 2. Data-Driven Specifications ##############################################

#  - search conditions for AWS resources (instances, volumes, stacks)
#  - supported operations
#  - rules for naming and tagging child resources (images, snapshots)
# Optional keys hide AWS API inconsistencies:
#  - levels between response object and individual resource
#  - resource identifier names
#  - method names


SPECS_CHILD = {
  "ec2": {

    "Image": {
      "op_kwargs_update_child_fn": lambda child_name, child_tags_encoded: {
        "Name": child_name,
        "Description": child_name,
        # Set Name and Description, because some Console pages show only one!
        "TagSpecifications": [
          {"ResourceType": "image", "Tags": child_tags_encoded},
          {"ResourceType": "snapshot", "Tags": child_tags_encoded},
        ],
      },
      "name_chars_unsafe_regexp": (
        re.compile(r"[^a-zA-Z0-9\(\)\[\] \./\-'@_]")
      ),
      "name_chars_max": 128,
    },

    "Snapshot": {
      "op_kwargs_update_child_fn": lambda child_name, child_tags_encoded: {
        "Description": child_name,
        "TagSpecifications": [
          {"ResourceType": "snapshot", "Tags": child_tags_encoded},
        ],
      },
      # http://boto3.readthedocs.io/en/latest/reference/services/ec2.html#EC2.Client.create_snapshot
      # No unsafe characters documented for snapshot description
      "name_chars_max": 255,
    },

  },
  "rds": {

    "DBSnapshot": {
      "op_kwargs_update_child_fn": lambda child_name, child_tags_encoded: {
        "DBSnapshotIdentifier": child_name,
        "Tags": child_tags_encoded,
      },
      # http://boto3.readthedocs.io/en/latest/reference/services/rds.html#RDS.Client.create_db_snapshot
      # Standard re module seems not to support Unicode character categories:
      # "name_chars_unsafe_regexp": re.compile(r"[^\p{L}\p{Z}\p{N}_.:/=+\-]"),
      # Simplification (may give unexpected results with Unicode characters):
      "name_chars_unsafe_regexp": re.compile(r"[^\w.:/=+\-]"),
      "name_chars_max": 255,
    },

    "DBClusterSnapshot": {
      "op_kwargs_update_child_fn": lambda child_name, child_tags_encoded: {
        "DBClusterSnapshotIdentifier": child_name,
        "Tags": child_tags_encoded,
      },
      # http://boto3.readthedocs.io/en/latest/reference/services/rds.html#RDS.Client.create_db_cluster_snapshot
      "name_chars_unsafe_regexp": re.compile(r"[^a-zA-Z0-9-]"),
      "name_chars_max": 63,
    },
  },

}
SPECS = {
  "ec2": {

    "Instance": {
      "describe_filters": {
        "instance-state-name": ["running", "stopping", "stopped"],
      },
      "flatten_fn": lambda resp: (
        instance
        for reservation in resp["Reservations"]
        for instance in reservation["Instances"]
      ),
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
          "specs_child_rsrc_type": SPECS_CHILD["ec2"]["Image"],
        },
        tag_key_join("reboot", "backup"): {
          "op_method_name": "create_image",
          "op_kwargs_static": {"NoReboot": False},
          "specs_child_rsrc_type": SPECS_CHILD["ec2"]["Image"],
        },
      },
    },

    "Volume": {
      "describe_filters": {
        "status": ["available", "in-use"],
      },
      "ops": {
        tag_key_join("backup"): {
          "op_method_name": "create_snapshot",
          "specs_child_rsrc_type": SPECS_CHILD["ec2"]["Snapshot"],
        },
      },
    },

  },
  "rds": {

    "DBInstance": {
      "paginator_name_irregular": "describe_db_instances",
      "rsrc_id_key_irregular": "DBInstanceIdentifier",
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
          "specs_child_rsrc_type": SPECS_CHILD["rds"]["DBSnapshot"],
        },
      },
    },

    "DBCluster": {
      "paginator_name_irregular": "describe_db_clusters",
      "rsrc_id_key_irregular": "DBClusterIdentifier",
      "ops": {
        tag_key_join("start"): {"op_method_name": "start_db_cluster"},
        tag_key_join("stop"): {"op_method_name": "stop_db_cluster"},
        tag_key_join("reboot"): {"op_method_name": "reboot_db_cluster"},
        tag_key_join("backup"): {
          "op_method_name": "create_db_cluster_snapshot",
          "specs_child_rsrc_type": SPECS_CHILD["rds"]["DBClusterSnapshot"],
        },
      },
    },

  },
  "cloudformation": {

    "Stack": {
      "rsrc_id_key_irregular": "StackName",
      "ops": {
        tag_key_join("toggle", "param", "true"): {
          "op_method_name": "update_stack",
          "op_kwargs_update_fn": stack_update_kwargs_make,
        },
        tag_key_join("toggle", "param", "false"): {
          "op_method_name": "update_stack",
          "op_kwargs_update_fn": stack_update_kwargs_make,
        },
      },
    },

  },
}

# 3. Shared Lambda Function Handler Code #####################################

svc_clients = {}


def svc_client_get(svc):
  """Take an AWS service, return a boto3 client, creating it if needed
  """
  if svc_clients.get(svc, None) is None:
    svc_clients[svc] = boto3.client(svc)
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

# 4. Find Resources Lambda Function Handler Code #############################


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


def rsrc_tags_check(ops_tag_keys, sched_regexp, rsrc):
  """Determine which operations are scheduled for the current cycle
  """
  result = {
    "name_from_tag": "",
    "op_tags_matched": [],
  }
  # EC2, CloudFormation: "Tags"; RDS: "TagList"; key omitted if no tags!
  for tag_pair in rsrc.get("Tags", rsrc.get("TagList", [])):
    tag_key = tag_pair["Key"]
    tag_value = tag_pair["Value"]
    if tag_key == "Name":  # EC2 resource name shown in Console
      result["name_from_tag"] = tag_value
    elif tag_key in ops_tag_keys and sched_regexp.search(tag_value):
      result["op_tags_matched"].append(tag_key)
  return result


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
    raise RuntimeError(
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
  sqs_client = svc_client_get("sqs")
  try:
    sqs_resp = sqs_client.send_message(
      QueueUrl=QUEUE_URL,
      MessageAttributes=op_msg_attrs,
      MessageBody=msg_body_encode(op_kwargs),
    )
  except botocore.exceptions.ClientError as sqs_exception:
    sqs_send_log(op_msg_attrs, op_kwargs, exception=sqs_exception)
    # Try to queue next operation
  except Exception:
    sqs_send_log(op_msg_attrs, op_kwargs)
    raise  # Stop queueing operations
  else:
    sqs_send_log(op_msg_attrs, op_kwargs, resp=sqs_resp)


def unique_suffix(
  char_count=5,
  chars_allowed="acefgrtxy3478"  # Small but unambiguous; more varied:
  # chars=string.ascii_lowercase + string.digits
  # http://pwgen.cvs.sourceforge.net/viewvc/pwgen/src/pw_rand.c
  # https://ux.stackexchange.com/questions/21076
):
  """Return a string of random characters
  """
  return "".join(random.choice(chars_allowed) for dummy in range(char_count))


def op_kwargs_child(
  parent_id,
  parent_name_from_tag,
  op,
  specs_child_rsrc_type,
  cycle_start_str,
  # Prefix image and snapshot names, because some Console pages don't show
  # tags ("z..." will sort after most manually-created resources):
  child_name_prefix=f"z{TAG_KEY_PREFIX}",
  name_delim="-",
  unsafe_char_fill="X"
):  # pylint: disable=too-many-arguments
  """Construct, return child-related kwargs
  """
  child_name = name_delim.join([
    child_name_prefix,
    parent_name_from_tag if parent_name_from_tag else parent_id,
    cycle_start_str,
    unique_suffix()
  ])
  if "name_chars_unsafe_regexp" in specs_child_rsrc_type:
    child_name = specs_child_rsrc_type["name_chars_unsafe_regexp"].sub(
      unsafe_char_fill,
      child_name
    )
  child_tags = [
    {"Key": tag_key, "Value": tag_value}
    for tag_key, tag_value in {
      tag_key_join("cycle", "start"): cycle_start_str,
      tag_key_join("parent", "id"): parent_id,
      tag_key_join("parent", "name"): parent_name_from_tag,
      tag_key_join("op"): op,
      "Name": child_name,
    }.items()
  ]
  return specs_child_rsrc_type["op_kwargs_update_child_fn"](
    child_name,
    child_tags
  )


def rsrcs_find(
  svc,
  rsrc_type,
  specs_rsrc_type,
  sched_regexp,
  cycle_start_str,
  cycle_cutoff_epoch_str
):  # pylint: disable=too-many-arguments
  """Find parent resources to operate on, and send details to queue.
  """

  ops_tag_keys = list(specs_rsrc_type["ops"].keys())
  if "describe_filters" in specs_rsrc_type:
    describe_kwargs = describe_kwargs_make(
      specs_rsrc_type["describe_filters"] | {"tag-key": ops_tag_keys}
    )
  else:
    describe_kwargs = {}

  svc_client = svc_client_get(svc)
  paginator = svc_client.get_paginator(
    specs_rsrc_type.get(
      "paginator_name_irregular",
      "describe_" + rsrc_type.lower() + "s"
  ))
  for resp in paginator.paginate(**describe_kwargs):

    if "flatten_fn" in specs_rsrc_type:
      rsrcs = specs_rsrc_type["flatten_fn"](resp)
    else:
      rsrcs = resp[rsrc_type + "s"]
    for rsrc in rsrcs:

      rsrc_id_key = specs_rsrc_type.get(
        "rsrc_id_key_irregular",
        rsrc_type + "Id"
      )
      rsrc_id = rsrc[rsrc_id_key]
      rsrc_tags_checked = rsrc_tags_check(ops_tag_keys, sched_regexp, rsrc)
      op_tags_matched_count = len(rsrc_tags_checked["op_tags_matched"])

      if op_tags_matched_count == 1:
        op = rsrc_tags_checked["op_tags_matched"][0]
        specs_op = specs_rsrc_type["ops"][op]
        op_method_name = specs_op["op_method_name"]
        if op_method_name[-1] == "s":
          # One resource at a time, to avoid partial completion risk
          op_kwargs = {rsrc_id_key + "s": [rsrc_id]}
        else:
          op_kwargs = {rsrc_id_key: rsrc_id}
        op_kwargs.update(specs_op.get("op_kwargs_static", {}))
        if "op_kwargs_update_fn" in specs_op:
          op_kwargs.update(specs_op["op_kwargs_update_fn"](rsrc, op))
        if "specs_child_rsrc_type" in specs_op:
          op_kwargs.update(op_kwargs_child(
            rsrc_id,
            rsrc_tags_checked["name_from_tag"],
            op,
            specs_op["specs_child_rsrc_type"],
            cycle_start_str
          ))
        op_queue(
          svc,
          op_method_name,
          op_kwargs,
          cycle_cutoff_epoch_str
        )

      elif op_tags_matched_count > 1:
        logging.error(json.dumps({
          "type": "MULTIPLE_OPS",
          "svc": svc,
          "rsrc_type": rsrc_type,
          "rsrc_id": rsrc_id,
          "op_tags_matched": rsrc_tags_checked["op_tags_matched"],
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
  print(cycle_cutoff.timestamp())
  cycle_cutoff_epoch_str = str(int(cycle_cutoff.timestamp()))
  sched_regexp = re.compile(cycle_start.strftime(SCHED_REGEXP_STRFTIME_FMT))
  logging.info(json.dumps({"type": "START", "cycle_start": cycle_start_str}))
  logging.info(json.dumps(
    {"type": "SCHED_REGEXP", "sched_regexp": sched_regexp},
    default=str
  ))

  for (svc, specs_svc) in SPECS.items():
    # boto3 method references can only be resolved at run-time,
    # against an instance of an AWS service's Client class.
    # http://boto3.readthedocs.io/en/latest/guide/events.html#extensibility-guide
    for (rsrc_type, specs_rsrc_type) in specs_svc.items():
      rsrcs_find(
        svc,
        rsrc_type,
        specs_rsrc_type,
        sched_regexp,
        cycle_start_str,
        cycle_cutoff_epoch_str
      )

# 5. "Do" Operations Lambda Function Handler Code ############################


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

  msg = event["Records"][0]

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
