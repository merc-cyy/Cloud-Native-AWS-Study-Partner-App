"""
triggered by upload of txt file into s3.
covnerts txt to audio 
uploads mp3 file
updates database accordingly

"""

import json
import boto3
import os
import uuid
import base64
import pathlib
import urllib.parse
import string
import datatier

from configparser import ConfigParser

def lambda_handler(event, context):
    try:
        print("Welcome to convert txt to audio function")
        
        audiofilebucketkey = ""# bucketkey that points to our audio file

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

        #this is called by a trigger from s3 when a TEXT file is uploaded into s3
        textfilebucketkey = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'], encoding='utf-8')#bucketkey of the uploaded txt file
        print("Text file bucketkey:", textfilebucketkey)
        extension = pathlib.Path(textfilebucketkey).suffix
        if extension != ".txt" : 
            raise Exception("expecting S3 document to have .txt extension")#only runs when its a text file is uploaded
        audiofilebucketkey = textfilebucketkey[0:-4] + ".mp3"#the audio file bucketkey
        print("Audio file bucketkey:", audiofilebucketkey)

        #download txt file from s3 to tmp storage
        print("currently downloading text file to aws temp storage to be converted")
        local_txt = '/tmp/data.txt'#aws file storage
        bucket.download_file(textfilebucketkey, local_txt)#download txt file to tmp storage

        print("Now our AWS local_txt has the text file ready to be converted")

        #open the audio file 
        local_results_file = '/tmp/audio.mp3'
        outfile = open(local_results_file, 'wb')

        #CONVERSION TO AUDIO
        chunk_size = 1000
        polly = boto3.client('polly')
        with open(local_txt, 'r') as file:
            while True:
                chunk = file.read(chunk_size)#take the first 1000 characters

                if not chunk:
                    break

                #call polly
                
                response = polly.synthesize_speech(
                    Engine='standard',
                    OutputFormat = 'mp3',
                    Text= chunk,
                    VoiceId = 'Amy',
                )
                outfile.write(response['AudioStream'].read())
        file.close()
        outfile.close()

        print("Audio file is done!")
        print("Uploading audio file to s3 now")

        #UPLOADING TO S3
        bucket.upload_file(local_results_file,
                       audiofilebucketkey,
                       ExtraArgs={
                         'ACL': 'public-read',
                         'ContentType': 'audio/mpeg'
                       })

        ##DATABASE STATUS UPDATE
        #Get textjobid first using the given bucketkey
        print("**Opening DB connection**")
        dbConn = datatier.get_dbConn(rds_endpoint, rds_portnum, rds_username, rds_pwd, rds_dbname)
        sql_gettextjobid = "SELECT textjobid FROM textjobs WHERE textresultsfilename = %s"
        row = datatier.retrieve_one_row(dbConn, sql_gettextjobid, [textfilebucketkey])
        if not row:
            return {
                'statusCode': 400,
                'body': 'Text job id doesnt exist'
                }
        textjobid = row[0]
        print(f"The textjobid is {textjobid}")
        print(f"The textfilebucketkey is {textfilebucketkey}")

        #audiofilename
        regex = r'\/\S*\/\D[a-zA-Z]*'
        audiofilename = textfilebucketkey[0:-4]

        #Inserting audiojob to database
        print("Inserting audio filejob to database")
        sql_insert = "INSERT audiojobs(textjobid, audiostatus, audiofilebucketkey, audiofilename) VALUES(%s, %s, %s, %s);"
        datatier.perform_action(dbConn, sql_insert, [textjobid, 'completed', audiofilebucketkey, audiofilename])

        print("**DONE, returning success**")
    
        return {
        'statusCode': 200,
        'body': json.dumps("success")
        }

    except Exception as err:
        print("**ERROR**")
        print(str(err))
        return {
            'statusCode': 500,
            'body': json.dumps(str(err))
                }



      



        


