
# Authors:
#   << MERCY WANGUI MUIRURI >>

import json
import requests
import jsons

import uuid
import pathlib
import logging
import sys
import os
import base64
import time

from configparser import ConfigParser


############################################################
#
# classes
#
class Channel:
  def __init__(self, row):
    self.title = row[0]
    self.description = row[1]



###################################################################
#
# web_service_get
#
# When calling servers on a network, calls can randomly fail. 
# The better approach is to repeat at least N times (typically 
# N=3), and then give up after N tries.
#
def web_service_get(url):
  """
  Submits a GET request to a web service at most 3 times, since 
  web services can fail to respond e.g. to heavy user or internet 
  traffic. If the web service responds with status code 200, 400 
  or 500, we consider this a valid response and return the response.
  Otherwise we try again, at most 3 times. After 3 attempts the 
  function returns with the last response.
  
  Parameters
  ----------
  url: url for calling the web service
  
  Returns
  -------
  response received from web service
  """

  try:
    retries = 0
    
    while True:
      response = requests.get(url)
        
      if response.status_code in [200, 400, 480, 481, 482, 500]:
        #
        # we consider this a successful call and response
        #
        break;

      #
      # failed, try again?
      #
      retries = retries + 1
      if retries < 3:
        # try at most 3 times
        time.sleep(retries)
        continue
          
      #
      # if get here, we tried 3 times, we give up:
      #
      break

    return response

  except Exception as e:
    print("**ERROR**")
    logging.error("web_service_get() failed:")
    logging.error("url: " + url)
    logging.error(e)
    return None



def web_service_post(url, dataset):
  try:
    retries = 0
    while True:
      response = requests.post(url, json=dataset)

      if response.status_code in [200, 400, 500]:
        break
      retries += 1

      if retries < 3:
        time.sleep(retries)#give the system a chance to take a break
        continue
      break
    return response
  
  except Exception as e:
    print("**ERROR**")
    logging.error("web_service_post() failed:")
    logging.error("url: " + url)
    logging.error(e)
    logging.error(f"data sent: {dataset}")
    return None 

############################################################
#
# prompt
#
def prompt():
  """
  Prompts the user and returns the command number

  Parameters
  ----------
  None

  Returns
  -------
  Command number entered by user (0, 1, 2, ...)
  """
  try:
    print()
    print(">> Enter a command:")
    print("   0 => exit")
    print("   1 => upload pdf")
    print("   2 => download textresults")
    print("   3 => get summarized audio")
    print("   4 => get YouTube channels")

    cmd = input()

    if cmd == "":
      cmd = -1
    elif not cmd.isnumeric():
      cmd = -1
    else:
      cmd = int(cmd)

    return cmd

  except Exception as e:
    print("**ERROR")
    print("**ERROR: invalid input")
    print("**ERROR")
    return -1



############################################################
#
# upload
#
def upload(baseurl):
  """
  Prompts the user for a local filename and user id, 
  and uploads that asset (PDF) to S3 for processing. 

  Parameters
  ----------
  baseurl: baseurl for web service

  Returns
  -------
  nothing
  """

  try:
    print("Enter PDF filename>")
    local_filename = input()

    if not pathlib.Path(local_filename).is_file():
      print("PDF file '", local_filename, "' does not exist...")
      return

    print("Enter user id>")
    userid = input().strip()

    #
    # build the data packet. First step is read the PDF
    # as raw bytes:
    #
    infile = open(local_filename, "rb")
    raw_bytes = infile.read()
    infile.close()

    # ENCODING: this converts the files bytes object to base64 to be converted to string
    # now encode the pdf as base64. Note b64encode returns a bytes object, not a string. 
    # So then we have to convert (decode) the bytes -> string, and then 
    # we can serialize the string as JSON for upload to server:
  
    raw_data = base64.b64encode(raw_bytes)#still bytes but in base64format
    datastr = raw_data.decode()#decodes the base64bytes into a str 
    payload = {"filename": local_filename, "data": datastr}

    #
    # call the web service:
    #
    
    res = None
    api = '/pdf' # api for uploading
    url = baseurl + api + "/" + userid #pass in user_id as part of the url

    res = requests.post(url, json=payload) # sendt eh data to AWS

    # let's look at what we got back:
    #
    if res.status_code == 200: #success
      pass
    elif res.status_code == 400: # no such user
      body = res.json()
      print(body)
      return
    else:
      # failed:
      print("Failed with status code:", res.status_code)
      print("url: " + url)
      if res.status_code == 500:
        # we'll have an error message
        body = res.json()
        print("Error message:", body)
      #
      return

    #
    # success, extract jobid:
    #
    body = res.json()

    jobid = body

    print("PDF uploaded, job id =", jobid)
    return

  except Exception as e:
    logging.error("**ERROR: upload() failed:")
    logging.error("url: " + url)
    logging.error(e)
    return


############################################################
#
# download
#
def downloadtext(baseurl):
  """
  Prompts the user for the job id, and downloads
  that asset (PDF).

  Parameters
  ----------
  baseurl: baseurl for web service

  Returns
  -------
  nothing
  """
  
  try:
    print("Enter job id>")
    jobid = input()
    
    #
    # call the web service:
    #

    res = None
  
    api = '/downloadtextresults'
    url = baseurl + api + '/' + jobid
    res = web_service_get(url)
    #print(res)
    #
    # let's look at what we got back:
    #
    if res.status_code == 200: #success
      pass
    elif res.status_code == 400: # no such job
      body = res.json()
      print(body)
      return
    elif res.status_code in [480, 481, 482]:  # uploaded
      msg = res.json()
      print("No results available yet...")
      print("Job status:", msg)
      return
    else:
      # failed:
      print("Failed with status code:", res.status_code)
      print("url: " + url)
      if res.status_code == 500:
        # we'll have an error message
        body = res.json()
        print("Error message:", body)
      #
      return
      
    #
    # if we get here, status code was 200, so we
    # have results to deserialize and display:
    #
    
    body = ""
    response = res.json()
    #print(f"JSON response:{response}")
    
    # deserialize the message body:

    filesavename = response.get("filename")
    datastr = response.get("text")

    #
    # encode the data string to obtain the raw bytes in base64,
    # then call b64decode to obtain the original raw bytes.
    # Finally, decode() the bytes to obtain the results as a 
    # printable string.
    #
  

    datastr_encoded = datastr.encode()
    b64_bytes_decode = base64.b64decode(datastr_encoded)
    results = b64_bytes_decode.decode()

    # with open('output.txt', 'w') as file:
    #   file.write(str(datastr))
    # print(datastr)
    filesave_name = filesavename + ".txt"
    print(f"Your text file has been saved as {filesave_name}")
    with open (filesave_name, 'w') as file:
      file.write(str(results))
    return

  except Exception as e:
    logging.error("**ERROR: download() failed:")
    logging.error("url: " + url)
    logging.error(e)
    return

############################################################

############################################################
#
# upload
#
def downloadaudiofile(baseurl):
  """
  Prompts the user for a jobid and downloads the summarized study guide for that pdf in audio format to the user's local file storage. 

  """

  try:
    print("Enter job id>")
    jobid = input()
    
    #
    # call the web service:
    #

    res = None
    header = {"Accept": "audio/mpeg"}
    api = '/downloadaudio'
    url = baseurl + api + '/' + jobid
    res = requests.get(url, headers=header)
    #print(res)
    #
    # let's look at what we got back:
    #
    if res.status_code == 200: #success
      print("Response was fine")
      pass
    else:
      # failed:
      print("Failed with status code:", res.status_code)
      print("url: " + url)
      if res.status_code == 500:
        # we'll have an error message
        print("Error")
      #
      return
      
    #
    # if we get here, status code was 200, so 
    filesave_name = jobid
    filesave_name = filesave_name + ".mp3"
    audio_data = res.content
    print(f"Your audio file has been saved as {filesave_name}")
    with open (filesave_name, 'wb') as file:
      file.write(audio_data)#since tis audio just write the audio bytes
    return

  except Exception as e:
    logging.error("**ERROR: download() failed:")
    logging.error("url: " + url)
    logging.error(e)
    return

############################################################

############################################################
#
# get YouTube resources
#
def getYTchannels(baseurl):
  """
  Prompts the user for a jobid and downloads a list of YouTube channels that offer content based on the pdf's main topics  

  """

  try:
    print("Enter job id>")
    jobid = input()
    
    #
    # call the web service:
    #

    res = None
    api = '/getYTresources'
    url = baseurl + api + '/' + jobid
    res = requests.get(url)
    #print(res)
    #
    # let's look at what we got back:
    #
    if res.status_code == 200: #success
      #print("Response was fine")
      pass
    else:
      # failed:
      print("Failed with status code:", res.status_code)
      print("url: " + url)
      if res.status_code == 500:
        # we'll have an error message
        print("Error")
      #
      return
      
    #
    # if we get here, status code was 200, so 
    body = res.json()
    # print(body)
    channels = []
    for title, description in body.items():
      yt = Channel((title, description))
      channels.append(yt)

    filesave_name = jobid
    filesave_name = filesave_name + "_extraresources.txt"
    
    #print("Here are some highly recommended YouTube channels to offer you more resources on the subject")
    print(f"The resources are  saved in your local file storage as {filesave_name}")
    with open(filesave_name, 'w') as file:
      file.write("This is a list of the top 5 YouTube channels you can research on for your topic\n")
      for show in channels:
        #print(f"{show.title}: {show.description}")
        file.write(f"Title: {show.title} Description: {show.description}\n")
    return
  
    
  except Exception as e:
    logging.error("**ERROR: download() failed:")
    logging.error("url: " + url)
    logging.error(e)
    return
############################################################
# main
#
try:
  print('** Welcome to Your StudyGuide!**')


  # eliminate traceback so we just get error message:
  sys.tracebacklimit = 0

  #
  # what config file should we use for this session?
  #
  config_file = 'studypartner-client.config.ini' # AWS Gateway endpoint

  print("Config file to use for this session?")
  print("Press ENTER to use default, or")
  print("enter config file name>")
  s = input()

  if s == "":  # use default
    pass  # already set
  else:
    config_file = s

  #
  # does config file exist?
  #
  if not pathlib.Path(config_file).is_file():
    print("**ERROR: config file '", config_file, "' does not exist, exiting")
    sys.exit(0)

  #
  # setup base URL to web service:
  #
  configur = ConfigParser()
  configur.read(config_file)
  baseurl = configur.get('client', 'webservice')

  #
  # make sure baseurl does not end with /, if so remove:
  #
  if len(baseurl) < 16:
    print("**ERROR: baseurl '", baseurl, "' is not nearly long enough...")
    sys.exit(0)

  if baseurl == "https://YOUR_GATEWAY_API.amazonaws.com":
    print("**ERROR: update config file with your gateway endpoint")
    sys.exit(0)

  if baseurl.startswith("http:"):
    print("**ERROR: your URL starts with 'http', it should start with 'https'")
    sys.exit(0)

  lastchar = baseurl[len(baseurl) - 1]
  if lastchar == "/":
    baseurl = baseurl[:-1]

  #
  # main processing loop:
  #
  cmd = prompt()

  while cmd != 0:
    #
    if cmd == 1:
      upload(baseurl) # upload a pdf 
    elif cmd == 2:
      downloadtext(baseurl)
    elif cmd == 3:
      downloadaudiofile(baseurl)
    elif cmd == 4:
      getYTchannels(baseurl)
    else:
      print("** Unknown command, try again...")
    #
    cmd = prompt()

  #
  # done
  #
  print()
  print('** done **')
  sys.exit(0)

except Exception as e:
  logging.error("**ERROR: main() failed:")
  logging.error(e)
  sys.exit(0)
