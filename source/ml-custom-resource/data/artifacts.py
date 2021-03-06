#!/usr/bin/python
# -*- coding: utf-8 -*-

##############################################################################
#  Copyright 2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.   #
#                                                                            #
#  Licensed under the Amazon Software License (the 'License'). You may not   #
#  use this file except in compliance with the License. A copy of the        #
#  License is located at                                                     #
#                                                                            #
#      http://aws.amazon.com/asl/                                            #
#                                                                            #
#  or in the 'license' file accompanying this file. This file is distributed #
#  on an 'AS IS' BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND,        #
#  express or implied. See the License for the specific language governing   #
#  permissions and limitations under the License.                            #
##############################################################################
import boto3
import os
import logging
from botocore.client import Config, ClientError
from custom.custom_base import Custom

log = logging.getLogger()
log.setLevel(logging.INFO)


class Artifacts(Custom):
    def __init__(self, event, context, s3_bucket, s3_destination_bucket, sb_bucket, sb_prefix_artifacts,
                 s3_prefix_artifacts, s3_prefix_rawdata, output_path):
        super().__init__(event, context,s3_bucket,s3_prefix_artifacts)
        self.config_file = "ArtifactsConfig.json"
        self.copy_artifactItems = event["ResourceProperties"]["CopyArtifacts"]
        self.copy_synthetic_data = event["ResourceProperties"]["TransferSyntheticData"]
        self.s3 = boto3.client('s3', config=Config(signature_version='s3v4'))
        self.s3resource = boto3.resource('s3')
        self.region = os.environ['AWS_DEFAULT_REGION']
        self.s3_bucket = s3_bucket
        self.s3_destination_bucket = s3_destination_bucket
        self.sb_bucket = sb_bucket
        self.destination_data_dir = output_path
        self.sb_prefix_artifacts = sb_prefix_artifacts
        self.s3_prefix_artifacts = s3_prefix_artifacts

        self.s3_prefix_rawdata = s3_prefix_rawdata
        self.sb_prefix_rawdata = sb_prefix_artifacts + "/data"
        #self.sb_prefix_rawdata = sb_prefix_artifacts + "/synthetic-data/industry/{}".format(industry)
        self.sb_prefix_config = sb_prefix_artifacts + "/config"
        self.s3_prefix_config = s3_prefix_artifacts + "/config"
        self.sb_prefix_notebook = sb_prefix_artifacts + "/notebooks"
        self.s3_prefix_notebook = s3_prefix_artifacts + "/notebooks"
        self.sb_prefix_scripts = sb_prefix_artifacts + "/scripts/glue-script"
        self.s3_prefix_scripts = s3_prefix_artifacts + "/scripts/glue-script"
        self.sb_prefix_lifecycle = sb_prefix_artifacts + "/scripts/sagemaker-script"
        self.s3_prefix_lifecycle = s3_prefix_artifacts + "/scripts/sagemaker-script"
        self.sb_prefix_models = sb_prefix_artifacts + "/models"
        self.s3_prefix_models = s3_prefix_artifacts + "/models"
        self.sb_prefix_schema = sb_prefix_artifacts + "/schema"
        self.s3_prefix_schema = s3_prefix_artifacts + "/schema"

    def __call__(self):
        if self.copy_artifactItems == "true":
            self.create_bucket(self.s3_bucket, self.s3_destination_bucket)

            # copy config
            self.copy_config(self.s3_prefix_config,self.sb_prefix_config,self.config_file)
            artifacts = super().get_artifactJson()

            # copy notebooks
            self.copy_artifacts(self.s3_prefix_notebook, self.sb_prefix_notebook,
                                artifacts['artifacts']['notebooks'])
            # copy scripts
            self.copy_artifacts(self.s3_prefix_scripts, self.sb_prefix_scripts,
                                artifacts['artifacts']['scripts'])
            # copy configs
            self.copy_artifacts(self.s3_prefix_lifecycle, self.sb_prefix_lifecycle,
                                artifacts['artifacts']['configs'])
            #copy models
            self.copy_artifacts(self.s3_prefix_models, self.sb_prefix_models,
                                artifacts['artifacts']['models'])
            # copy schema
            self.copy_artifacts(self.s3_prefix_schema, self.sb_prefix_schema,
                                artifacts['artifacts']['schema'])

            self.update_lifecycle_config(artifacts)

            if self.copy_synthetic_data == "true":
                # copy data
                self.copy_artifacts(self.s3_prefix_rawdata, self.sb_prefix_rawdata,
                                    artifacts['artifacts']['files'], True)

        return {'PhysicalResourceId': self.event["LogicalResourceId"]}

    def create_bucket(self, *args):
        try:
            for bucket in args:
                if not self.check_bucket(bucket):
                    # https://docs.aws.amazon.com/cli/latest/reference/s3api/create-bucket.html
                    # Regions outside of us-east-1 require the appropriate LocationConstraint to be specified in order to create the bucket in the desired region:
                    bucket_name = self.s3.create_bucket(
                        Bucket=bucket) if 'us-east-1' == self.region else self.s3.create_bucket(Bucket=bucket,
                                                                                                CreateBucketConfiguration={
                                                                                                    'LocationConstraint': self.region})

                    log.info('S3 Bucket = %s', bucket_name)

        except Exception as e:
            print('An error occurred: {}.'.format(e))
            raise e

    def check_bucket(self, bucket_name):

        try:
            self.s3resource.meta.client.head_bucket(Bucket=bucket_name)
            print("Bucket Exists!")
            return True
        except ClientError as e:
            # If a client error is thrown, then check that it was a 404 error.
            # If it was a 404 error, then the bucket does not exist.
            error_code = int(e.response['Error']['Code'])
            if error_code == 403:
                print("Private Bucket. Forbidden Access!")
                return True
            elif error_code == 404:
                print("Bucket Does Not Exist!")
                return False

    def copy_config(self,s3_prefix, sb_prefix,value):
        try:
            new_bucket = self.s3_bucket
            copy_source = "{}/{}/{}".format(self.sb_bucket, sb_prefix, value)
            bucket_key = "{}/{}".format(s3_prefix, value)

            response = self.s3.copy_object(ACL='public-read', CopySource=copy_source, Bucket=new_bucket,
                                           Key=bucket_key)
            log.info('Response = %s', response)
            log.info('Copying %s to %s/%s', copy_source, new_bucket, bucket_key)
            status = 'SUCCESS'

        except Exception as e:
            print('An error occurred: {}.'.format(e))
            raise e
        return status

    # Adds Key to Prefix for data
    def copy_artifacts(self, s3_prefix, sb_prefix, artifacts, addkey=False):
        try:
            for key, value in artifacts.items():
                new_bucket = self.s3_bucket
                copy_source = "{}/{}/{}".format(self.sb_bucket, sb_prefix, value)
                bucket_key = "{}/{}".format(s3_prefix, value)
                if addkey:
                    copy_source = "{}/{}/{}/{}".format(self.sb_bucket, sb_prefix, key, value)
                    bucket_key = "{}/{}/{}".format(s3_prefix, key, value)

                response = self.s3.copy_object(ACL='public-read', CopySource=copy_source, Bucket=new_bucket,
                                               Key=bucket_key)
                log.info('Response = %s', response)
                log.info('Copying %s to %s/%s', copy_source, new_bucket, bucket_key)

            responseStatus = 'SUCCESS'

        except Exception as e:
            print('An error occurred: {}.'.format(e))
            raise e
        return responseStatus

    def update_lifecycle_config(self,artifacts):

        try:
            bucket = self.s3_bucket
            key = "{}/scripts/sagemaker-script/{}".format(self.s3_prefix_artifacts,
                                                          artifacts['artifacts']['configs']['sagemaker'])
            destination_data_dir = self.destination_data_dir.replace("s3://", "s3a://")
            s3region = "s3.amazonaws.com" if "us-east-1" == self.region else "s3-{}.amazonaws.com".format(self.region)
            update_item = {
                "CP_SAMPLES=true": "CP_SAMPLES={}".format(self.copy_artifactItems),
                "CP_DATA=true": "CP_DATA={}".format(self.copy_synthetic_data),
                "EXTRACT_CSV=false": "EXTRACT_CSV=false",
                '"<%s3region%>"': s3region,
                '"<%SRC_NOTEBOOK_DIR%>"': "{}/{}".format(self.s3_bucket, self.s3_prefix_notebook),
                '"<%SRC_DATA_DIR%>"': "{}/{}".format(self.s3_bucket, self.s3_prefix_rawdata),
                '"<%DESTINATION_DATA_DIR%>"': destination_data_dir
            }

            try:
                object = self.s3resource.Object(bucket, key)
                obj_data = object.get()['Body'].read().decode('utf-8')
                for key, value in update_item.items():
                    obj_data = obj_data.replace(key, value)
                object.put(Body=obj_data)

            except ClientError as e:
                if e.response['Error']['Code'] == "404":
                    print("The object does not exist.")
                else:
                    raise e

        except Exception as e:
            print('An error occurred: {}.'.format(e))
            raise e
