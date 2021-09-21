#!/usr/bin/env python3
"""
This is a tool to create a S3 Storage Lens report based on a prefix of buckets.

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
__version__   = "0.2"

# Default region listed here
REGION_NAME = "us-east-1"
blankjson = {}
response = ""

# Defaults
MAXBUCKETS=50

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
s3_storage_lens_subset.py

This utility has two required options to run:
------------------------------------
1) prefix - The prefix of the s3 buckets you wish to search for.
2) name - This is the dashboard name you would like to create or modify (this will overwrite the settings for an existing dashboard)

Example:
./s3_storage_lens_subset.py -v -x "customerx-" -n testDashboard

    '''
    )


PARSER.add_argument('-p','--profile', required=False, default="default", help='AWS CLI Profile Name')
PARSER.add_argument('-r','--region', required=False, default="us-east-1", help='From Region Name. Example: us-east-1')
PARSER.add_argument('-x','--prefix', required=True, default="ep-", help='Prefix to search for')
PARSER.add_argument('-n','--name', required=True, help='Dashboard Name')
PARSER.add_argument('-v','--debug', action='store_true', help='print debug messages to stderr')

ARGUMENTS = PARSER.parse_args()
PROFILE = ARGUMENTS.profile
PREFIX = ARGUMENTS.prefix
DASHBOARDNAME = ARGUMENTS.name
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

def getBucketsByPrefix(
    s3client,
    prefix
    ):
    """ Get a list of all buckets that start with a specific string"""

    response = s3client.list_buckets()

    jmesquery = "Buckets[?starts_with(Name, `"+prefix+"`) == `true`].Name"

    logger.debug("JMES Query string: %s" % jmesquery)
    answers = jmespath.search(jmesquery, response)

    logger.debug("Found the following buckets starting with the prefix %s: %s" %(PREFIX, answers))

    return answers

def putStorageLens(
    s3client,
    s3control,
    bucketList,
    dashboardName,
    accountId,
    ):
    """ Genereate a Storage Lens config for a list of buckets """

    includeBucketList = []
    for bucket in bucketList:
        includeBucketList.append("arn:aws:s3:::"+bucket)

    storageLensConfig = {
        "Id": dashboardName,
        "AccountLevel": {
          "ActivityMetrics": {
            "IsEnabled": True
          },
          "BucketLevel": {
            "ActivityMetrics": {
              "IsEnabled": True
            }
          }
        },
        "Include": {
          "Buckets": includeBucketList
        },
        "IsEnabled": True
      }

    # Just to double check we are not passing along to many buckets, double check here
    if (len(storageLensConfig["Include"]["Buckets"])) > MAXBUCKETS:
        logger.error("Sorry, found %s buckets and the max is %s." % (len(storageLensConfig["Include"]["Buckets"]),MAXBUCKETS))
    else:
        logger.info("Modifying %s dashboard with new configuration", dashboardName)
        logger.debug("Storage Lens Config: %s", json.dumps(storageLensConfig))
        response = s3control.put_storage_lens_configuration(
            ConfigId = dashboardName,
            AccountId = accountId,
            StorageLensConfiguration = storageLensConfig
        )

def main():
    """ Main program run """

    boto3_min_version = "1.16.21"
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

    # Initiate s3 client resource
    S3CLIENT = SESSION1.client(
        service_name='s3',
        region_name=REGION_NAME,
    )

    # Initiate s3 client resource
    S3CONTROL = SESSION1.client(
        service_name='s3control',
        region_name=REGION_NAME,
    )

    bucketList = getBucketsByPrefix(S3CLIENT,PREFIX)
    if len(bucketList) > MAXBUCKETS:
        logger.error("Sorry, found %s buckets and the max is %s" % (len(bucketList),MAXBUCKETS))
    else:
        logger.info("Found %s (out of %s MAX) for AWS S3 Storage Lens Dashboard" %(len(bucketList),MAXBUCKETS))
        putStorageLens(S3CLIENT, S3CONTROL, bucketList, DASHBOARDNAME, ACCOUNTID)


if __name__ == "__main__":
    main()
