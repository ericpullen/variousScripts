#!/usr/bin/env python3
"""
This is a tool to look at placement scores

*** NOT FOR PRODUCTION USE ***

Licensed under the Apache 2.0 and MITnoAttr License.

Copyright 2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.

Licensed under the Apache License, Version 2.0 (the "License").
You may not use this file except in compliance with the License.
A copy of the License is located at https://aws.amazon.com/apache2.0/
"""

import json
import datetime
import logging
import sys

import argparse
import botocore
import boto3
import jmespath
from pkg_resources import packaging


__author__    = "Eric Pullen"
__email__     = "eppullen@amazon.com"
__copyright__ = "Copyright 2021 Amazon.com, Inc. or its affiliates. All Rights Reserved."
__credits__   = ["Eric Pullen"]
__version__   = "0.1"

# Default region listed here
REGION_NAME = "us-east-1"
blankjson = {}
response = ""

# Setup Logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s.%(msecs)03d %(levelname)s %(module)s - %(funcName)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

logger = logging.getLogger()
logging.getLogger('boto3').setLevel(logging.CRITICAL)
logging.getLogger('botocore').setLevel(logging.CRITICAL)
logging.getLogger('s3transfer').setLevel(logging.CRITICAL)
logging.getLogger('urllib3').setLevel(logging.CRITICAL)
PARSER = argparse.ArgumentParser(
    formatter_class=argparse.RawDescriptionHelpFormatter,
    description='''\
placementscore.py

This utility has two required options to run:
------------------------------------
1) prefix - The prefix of the s3 buckets you wish to search for.
2) name - This is the dashboard name you would like to create or modify (this will overwrite the settings for an existing dashboard)

Example:
./s3_storage_lens_subset.py

    '''
    )


PARSER.add_argument('-p','--profile', required=False, default="default", help='AWS CLI Profile Name')
PARSER.add_argument('-r','--region', required=False, default="us-east-1", help='From Region Name. Example: us-east-1')
PARSER.add_argument('-v','--debug', action='store_true', help='print debug messages to stderr')

ARGUMENTS = PARSER.parse_args()
PROFILE = ARGUMENTS.profile
REGION_NAME = ARGUMENTS.region

if ARGUMENTS.debug:
    logger.setLevel(logging.DEBUG)
else:
    logger.setLevel(logging.INFO)

class DateTimeEncoder(json.JSONEncoder):
    """Helper class to convert a datetime item to JSON."""
    def default(self, z):
        if isinstance(z, datetime.datetime):
            return str(z)
        return super().default(z)

def getScoreByInstanceType(
    ec2client,
    target_capacity,
    instance_types,
    region_names,
    target_capacity_unit_type,
    single_availability_zone
    ):
    """ Get score for a specific instance in a particular region """

    response = ec2client.get_spot_placement_scores(
        TargetCapacity = target_capacity,
        InstanceTypes = instance_types,
        TargetCapacityUnitType = target_capacity_unit_type,
        SingleAvailabilityZone = single_availability_zone,
        RegionNames = region_names
        )

    # jmesquery = "Buckets[?starts_with(Name, `"+prefix+"`) == `true`].Name"
    #
    # logger.debug("JMES Query string: %s" % jmesquery)
    # answers = jmespath.search(jmesquery, response)
    #
    # logger.debug("Found the following buckets starting with the prefix %s: %s" %(PREFIX, answers))

    return response['SpotPlacementScores']

def getScoreByInstanceRequirements(
    ec2client,
    target_capacity,
    region_names,
    target_capacity_unit_type,
    single_availability_zone,
    instance_requirements
    ):
    """ Get score for a specific instance in a particular region """

    response = ec2client.get_spot_placement_scores(
        TargetCapacity = target_capacity,
        # TargetCapacityUnitType = target_capacity_unit_type,
        # SingleAvailabilityZone = single_availability_zone,
        # RegionNames = region_names,
        InstanceRequirementsWithMetadata = instance_requirements
        )

    # jmesquery = "Buckets[?starts_with(Name, `"+prefix+"`) == `true`].Name"
    #
    # logger.debug("JMES Query string: %s" % jmesquery)
    # answers = jmespath.search(jmesquery, response)
    #
    # logger.debug("Found the following buckets starting with the prefix %s: %s" %(PREFIX, answers))

    return response['SpotPlacementScores']


def main():
    """ Main program run """

    boto3_min_version = "1.19.7"
    # Verify if the version of Boto3 we are running has correct APIs for S3 storage lens included
    if packaging.version.parse(boto3.__version__) < packaging.version.parse(boto3_min_version):
        logger.error("Your Boto3 version (%s) is less than %s. You must ugprade to run this script (pip3 upgrade boto3)" % (boto3.__version__, boto3_min_version))
        sys.exit()

    logger.info("Script version %s" % __version__)
    logger.info("Starting Boto %s Session" % boto3.__version__)

    ACCOUNTID = boto3.client('sts').get_caller_identity().get('Account')
    logger.debug("Calling AccountID: %s", ACCOUNTID)
    # Create a new boto3 session
    SESSION1 = boto3.session.Session(profile_name=PROFILE)

    EC2CLIENT = SESSION1.client('ec2')

    instance_types = [
    # "m5.4xlarge", # 16VCPU 64GBRAM
    # "m5.8xlarge"  # 32VCPU 128GBRAM
    "r5.4xlarge", # 16VCPU 128GB RAM
    "r5.8xlarge"  # 32VCPU 256GB RAM
    ]

    target_capacity = 5
    target_capacity_unit_type = "vcpu"
    single_availability_zone = True
    region_names = [
        "eu-west-1"
    ]

    scoreValues = getScoreByInstanceType(
        EC2CLIENT,
        target_capacity,
        instance_types,
        region_names,
        target_capacity_unit_type,
        single_availability_zone
        )
    # print(json.dumps(scoreValues,cls=DateTimeEncoder))

    scores_above_5 = 0
    for az_score in scoreValues:
        if az_score['Score'] > 5:
            logger.debug("Found a score above 5 (%s) for AZ %s" % (az_score['Score'], az_score['AvailabilityZoneId']))
            scores_above_5+=1
        else:
            logger.debug("Found a score below 5 (%s) for AZ %s" % (az_score['Score'], az_score['AvailabilityZoneId']))

    if scores_above_5 > 0:
        print("You can use these machines")
    else:
        #Let's try again with bigger machines
        logger.debug("Trying again with bigger machines")
        instance_types = [
        "r5.4xlarge",
        "r5.8xlarge",
        "r5.12xlarge"
        ]
        scoreValues = getScoreByInstanceType(
            EC2CLIENT,
            target_capacity,
            instance_types,
            region_names,
            target_capacity_unit_type,
            single_availability_zone
            )
    scores_above_5 = 0
    for az_score in scoreValues:
        if az_score['Score'] > 5:
            logger.debug("Found a score above 5 (%s) for AZ %s" % (az_score['Score'], az_score['AvailabilityZoneId']))
            scores_above_5+=1
        else:
            logger.debug("Found a score below 5 (%s) for AZ %s" % (az_score['Score'], az_score['AvailabilityZoneId']))

    if scores_above_5 > 0:
        print("You can use these machines")

    # InstanceReqMetadata = {
    #   "ArchitectureTypes": [
    #     "x86_64", "i386"
    #   ],
    #   "VirtualizationTypes": [
    #     "hvm","paravirtual"
    #   ],
    #   "InstanceRequirements": {
    #     "VCpuCount": {
    #       "Min": 15,
    #       "Max": 34
    #     },
    #     "MemoryMiB": {
    #       "Min": 63,
    #       "Max": 129
    #     }
    #     # "CpuManufacturers": [
    #     #   "intel",
    #     #   "amd"
    #     # ],
    #     # "InstanceGenerations": [
    #     #   "current",
    #     #   "previous"
    #     #]
    #   }
    # }
    #
    #
    #
    # scoreValues = getScoreByInstanceRequirements(
    #     EC2CLIENT,
    #     target_capacity,
    #     region_names,
    #     target_capacity_unit_type,
    #     single_availability_zone,
    #     InstanceReqMetadata
    #     )
    #
    # print(json.dumps(scoreValues,cls=DateTimeEncoder))


if __name__ == "__main__":
    main()
