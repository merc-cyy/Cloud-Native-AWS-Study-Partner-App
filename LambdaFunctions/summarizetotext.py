# """
# triggered by upload of pdf into s3
# calls the chatgpt api
# gets back summarized text and questions.
# saves text to pdf
# save pdf in s3
# return jobid
# """

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
from pypdf import PdfReader
#from google import genai
from openai import OpenAI

def lambda_handler(event, context):
  try:
    print("WELCOME to summarizetotext")
    print("This function has been triggered by S3 and will now call chatGPT, analyze the text, summarize it and upload summarized pdf")

    
    # 
    # in case we get an exception, initial this filename
    # so we can write an error message if need be:
    #
    bucketkey_results_file = ""
    
    #
    # setup AWS based on config file:
    #
    config_file = 'studypartner.config.ini'
    os.environ['AWS_SHARED_CREDENTIALS_FILE'] = config_file
    
    configur = ConfigParser()
    configur.read(config_file)
    
    #
    # configure for S3 access:
    #
    s3_profile = 's3readwrite'
    boto3.setup_default_session(profile_name=s3_profile)
    
    bucketname = configur.get('s3', 'bucket_name')
    
    s3 = boto3.resource('s3')
    bucket = s3.Bucket(bucketname)
    
    #
    # configure for RDS access
    #
    rds_endpoint = configur.get('rds', 'endpoint')
    rds_portnum = int(configur.get('rds', 'port_number'))
    rds_username = configur.get('rds', 'user_name')
    rds_pwd = configur.get('rds', 'user_pwd')
    rds_dbname = configur.get('rds', 'db_name')
    
    #
    # this function is event-driven by a PDF being
    # dropped into S3. The bucket key is sent to 
    # us and obtain as follows:
    #
    bucketkey = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'], encoding='utf-8')
    
    print("bucketkey:", bucketkey)
      
    extension = pathlib.Path(bucketkey).suffix
    
    if extension != ".pdf" : 
      raise Exception("expecting S3 document to have .pdf extension")
    
    bucketkey_results_file = bucketkey[0:-4] + ".txt"
    
    print("bucketkey results file:", bucketkey_results_file)
      
    #
    # download PDF from S3 to LOCAL file system:
    #
    print("Currently downloading pdf file to tmp storage to be shipped to OpenAI")
    print("**DOWNLOADING '", bucketkey, "'**")

    local_pdf = "/tmp/data.pdf"
    
    bucket.download_file(bucketkey, local_pdf)

    #
    # open LOCAL pdf file:
    #r
    print("**Converting PDF to text**")
    reader = PdfReader(local_pdf)#creates a new object of PdfReader
    if not reader:
      print("**MALFORMED PDF, returningco...**")
      return {
        'statusCode': 400,
        'body': json.dumps("Could not read Null object")
      }

    number_of_pages = len(reader.pages)#pages gives a list of page objects

    ##DATABASE UPDATE CHANGE STATUS TO STARTING
    # change the value to "processing - starting". Use the
    # bucketkey --- stored as datafilekey in the table ---
    # to identify the row to update. Use the datatier.
    # open connection to the database:
    #
    print("**Opening DB connection**")
    dbConn = datatier.get_dbConn(rds_endpoint, rds_portnum, rds_username, rds_pwd, rds_dbname)
    sql1 = "UPDATE textjobs SET textstatus = 'processing - starting' WHERE textdatafilekey = %s";
    datatier.perform_action(dbConn, sql1, [bucketkey])

    print("SQL status changed to processing - starting")
    print("bucketkey:", bucketkey)
    sqlgetid = "SELECT textjobid FROM textjobs WHERE textdatafilekey = %s";
    row2 = datatier.retrieve_one_row(dbConn, sqlgetid, [bucketkey])
    print(f"The row: {row2}")
    jobid = row2[0]
    print("Jobid retrieved! ")


    local_results_file = "/tmp/results.txt"
    print("local results file:", local_results_file)
    print("Just about to extract text from the pdf")
    txtarray = ""
    for page_index, page in enumerate(reader.pages, start=1):
        text = page.extract_text()
        txtarray += text
        sql_page1 = "UPDATE textjobs SET textstatus = 'processing - page %s of %s completed' WHERE textdatafilekey = %s";
        datatier.perform_action(dbConn, sql_page1, [page_index, number_of_pages, bucketkey])
    print("Text extraction from pdf done")
    #before uploading to s3, call chatgpt openai and pass in my txt file.

    print("Just about to call ChatGPT ")
    client = OpenAI()
    completion1 = client.chat.completions.create(
        model='gpt-4o',
        messages =[
            {
                "role": "developer",
                "content": "You are a good assistant. The user will provide text from a pdf. The user needs a good summary of the contents of that text that will help them revise and understand the concepts. Make your summary structured and in different sections. Make the output very readable (as in reomve the hashtags and unnecessary punctuation) since its will be converted to speech."
            },
            {
                "role": "user",
                "content": txtarray
            }
        ]
    )

    res = completion1.choices[0].message.content

    with open(local_results_file, 'w', encoding='utf-8') as file:
            file.write(res) 

    ######################
    #Get the topic labels
    print("Getting the topic title")
    completion2 = client.chat.completions.create(
      model="gpt-4o",
      messages=[
        {
          "role": "developer",
          "content": "You are a helpful assistant. Using the summary you just made. give me ONE short 3 -5 word sentence that our user can search on in order to learn more about their topic."
        },
        {
          "role": "user",
          "content": res
        }
      ],
    )
    res_topic = completion2.choices[0].message.content
    #Insert into the content database
    sql_content = "INSERT INTO contentjobs(textjobid, topic) VALUES(%s, %s);"
    datatier.perform_action(dbConn, sql_content, [jobid, res_topic])
    print("Content database updated")


    print("ChatGPT is done!")

    print("Saved the temp text file to S3. ")
    print("**UPLOADING to S3 file", bucketkey_results_file, "**")

    bucket.upload_file(local_results_file,
                       bucketkey_results_file,
                       ExtraArgs={
                         'ACL': 'public-read',
                         'ContentType': 'text/plain'
                       })
    ##DATABASE STATUS UPDATE
    #Status updated to completed
    sql_end = "UPDATE textjobs SET textstatus = %s, textresultsfilename = %s WHERE textdatafilekey = %s";
    stat = 'completed'
    datatier.perform_action(dbConn, sql_end, [stat, bucketkey_results_file, bucketkey])

    print("**DONE, returning success**")
    
    return {
      'statusCode': 200,
      'body': json.dumps("success")
    }
    
  #
  # on an error, try to upload error message to S3:
  #
  except Exception as err:
    print("**ERROR**")
    print(str(err))
    
    local_results_file = "/tmp/results.txt"
    outfile = open(local_results_file, "w")

    outfile.write(str(err))
    outfile.write("\n")
    outfile.close()
    
    if bucketkey_results_file == "": 
      #
      # we can't upload the error file:
      #
      pass
    else:
      # 
      # upload the error file to S3
      #
      print("**UPLOADING**")
      #
      bucket.upload_file(local_results_file,
                         bucketkey_results_file,
                         ExtraArgs={
                           'ACL': 'public-read',
                           'ContentType': 'text/plain'
                         })

      #DATABSE UPDATE STATUS TO ERROR
      dbConn = datatier.get_dbConn(rds_endpoint, rds_portnum, rds_username, rds_pwd, rds_dbname)
      sql_end1 = "UPDATE textjobs SET textstatus = 'error', textresultsfilename = %s WHERE textdatafilekey = %s";
      datatier.perform_action(dbConn, sql_end1, [bucketkey_results_file, bucketkey])
      return {
      'statusCode': 500,
      'body': json.dumps(str(err))
      }

                               
# from openai import OpenAI
# client = OpenAI()

# response = client.responses.create(
#   model="gpt-4o",
#   input=[
#     {
#       "role": "system",
#       "content": [
#         {
#           "type": "input_text",
#           "text": "You are a helpful assistant. The user will provide text from a pdf. You need to do 2 things: 1. The user needs a good summary of the contents of that text that will help them revise and understand the concepts. Make your summary structured and in different sections.  2. Give me no more than 5 words that represent this topic that the user can use to search more on the topic to learn more about it. Thanks\"\n           "
#         }
#       ]
#     }
#   ],
#   text={
#     "format": {
#       "type": "text"
#     }
#   },
#   reasoning={},
#   tools=[],
#   temperature=1,
#   max_output_tokens=2048,
#   top_p=1,
#   store=True
# )
