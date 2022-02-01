# Virtual Box on top of EC2 Metal instance

## Overview
The purpose of this Cloudformation template is to stand up a single EC2 instance running Windows Server with VirtualBox, FireFox, and Cyberduck during creation. It will also pull down a VHD image from a S3 bucket, copy it to the local machine, and configure VirtualBox for it.

## Example CloudFormation Deployment
1. Login to your AWS account and select CloudFormation from the service list.
    ![CFN1](./documentation/CFN1.png)
1. Click on the "create stack" then "with new resources (standard)"
  ![CFN2](./documentation/CFN2.png)
1. Click on "Upload a template file" and then click "Choose File"
1. Select
  ![CFN3](./documentation/CFN3.png)
