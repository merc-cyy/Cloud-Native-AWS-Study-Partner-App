"""
Downloads the requested audio file given a jobid.
input: jobid
output: the audio file in binary form

"""

import json
import boto3
import os
import base64
import datatier

from configparser import ConfigParser

def lambda_handler(event, context):
  try:
    print("**STARTING**")
    print("**lambda: download audio**")
    # setup AWS based on config file:
    config_file = 'studypartner.config.ini'
    os.environ['AWS_SHARED_CREDENTIALS_FILE'] = config_file
    configur = ConfigParser()
    configur.read(config_file)
    s3_profile = 's3readwrite'
    boto3.setup_default_session(profile_name=s3_profile)
    bucketname = configur.get('s3', 'bucket_name')
    s3 = boto3.resource('s3')
    bucket = s3.Bucket(bucketname)
    rds_endpoint = configur.get('rds', 'endpoint')
    rds_portnum = int(configur.get('rds', 'port_number'))
    rds_username = configur.get('rds', 'user_name')
    rds_pwd = configur.get('rds', 'user_pwd')
    rds_dbname = configur.get('rds', 'db_name')
    # jobid from event: could be a parameter
    # or could be part of URL path ("pathParameters"):
    #
    print("Checked in the config file")
    if "jobid" in event:
      jobid = event["jobid"]
    elif "pathParameters" in event:
      if "jobid" in event["pathParameters"]:
        jobid = event["pathParameters"]["jobid"]
      else:
        raise Exception("requires jobid parameter in pathParameters")
    else:
        raise Exception("requires jobid parameter in event")
        
    print("textjobid:", jobid)
    textjobid = jobid


    #CHECKING IF JOBID EXISTS IN AUDIODATABASE
    print("**Opening connection**")
    dbConn = datatier.get_dbConn(rds_endpoint, rds_portnum, rds_username, rds_pwd, rds_dbname)
    #is jobid valid
    print("**Checking if textjobid is valid**")
    sql = "SELECT * FROM audiojobs WHERE textjobid = %s;"
    row = datatier.retrieve_one_row(dbConn, sql, [textjobid])
    if row == ():  # no such job
      print("**No such audio file, returning...**")
      return {
        'statusCode': 400,
        'body': json.dumps("No such audio job. Try uploading the pdf again")
      }

    print(row)
    audiostatus = row[2]
    audiofilename = row[4]
    audiofilebucketkey = row[3]
    print("Audio job status:", audiostatus)
    print("Audio filename:", audiofilename)
    print("Audiofile bucket key:", audiofilebucketkey)

    #check status in case of any error
    if audiostatus != 'completed':
        print("Audio status was not complete. Check upload function")
        return {
            'statusCode': 480,
            'body': json.dumps(audiostatus)
        }

    #if not, lets download file to temp storage and then send it over
    tmp_audio = '/tmp/audio.mp3'
    print("Downloading audio from S3")
    bucket.download_file(audiofilebucketkey, tmp_audio)

    print("Reading in file")
    infile = open(tmp_audio, "rb")
    audio_bytes = infile.read()
    infile.close()
    print("Done reading in file")
    
    #
    # now encode the data as base64. Note b64encode returns
    # a bytes object, not a string. So then we have to convert
    # (decode) the bytes -> string, and then we can serialize
    # the string as JSON for download:
    data = base64.b64encode(audio_bytes)
    datastr = data.decode('utf-8')
    print("**DONE, returning results**")

    #send back audio file
    return {
        'statusCode': 200,
        'headers': {
        'Content-Type': 'audio/mpeg'
        },
        'isBase64Encoded': True,
        'body': datastr
            }

  except Exception as err:
    print("**ERROR**")
    print(str(err))
    
    return {
      'statusCode': 500,
      'body': json.dumps(str(err))
    }
