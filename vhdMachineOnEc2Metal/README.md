# Virtual Box on top of EC2 Metal instance

## Overview
The purpose of this Cloudformation template is to stand up a single EC2 instance running Windows Server with VirtualBox, FireFox, and Cyberduck during creation. It will also pull down a VHD image from a S3 bucket, copy it to the local machine, and configure VirtualBox for it.

## Example Setup
![CFN1](./documentation/CFN1.png)

![CFN2](./documentation/CFN2.png)

![CFN3](./documentation/CFN3.png)
