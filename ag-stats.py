#!/usr/bin/env python3
import os,sys,re,datetime,time,json
import numpy
import canvas
import autograder

if sys.hexversion < 0x030000F0:
    print("This script requires Python 3")
    sys.exit(1)

# Load configuration information
config = autograder.config()
settings = config.get()
subdirName = settings['subdirName']


dirs = [name for name in os.listdir(subdirName) if os.path.isdir(os.path.join(subdirName, name))]
dirs.sort()
os.chdir(subdirName)

score_list=[]

for d in dirs:
    metadataFile = d + "/AUTOGRADE.json"
    metadata = []
    if os.path.exists(metadataFile):
        with open(metadataFile, "r") as f:
            metadata = json.load(f)
    
    emailed=""
    if 'emailSent' in metadata and metadata['emailSent']==1:
        emailed="Emailed"
    score="?"
    if os.path.exists(os.path.join(d, "AUTOGRADE.txt")):
        with open(os.path.join(d, "AUTOGRADE.txt"), 'r') as f:
            match = re.search("TOTAL.*: (.*)", f.read())
            if match.group(1):
                score = match.group(1).strip()
                score_list.append(int(score))
    attempt=0
    timeString=''
    if 'canvasSubmission' in metadata:
        if 'attempt' in metadata['canvasSubmission']:
            attempt = metadata['canvasSubmission']['attempt']
        if 'submitted_at' in metadata['canvasSubmission']:
            import datetime
            utc_dt = datetime.datetime.strptime(metadata['canvasSubmission']['submitted_at'],
                                                '%Y-%m-%dT%H:%M:%SZ')
            utc_dt = utc_dt.replace(tzinfo=datetime.timezone.utc)
            timeString = canvas.canvas.prettyDate(utc_dt, datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc))

    print("%20s %8s %5s - %s - attempt %d" % (d, emailed,score, timeString, attempt))

print("Submission count: %d" % len(dirs))
if len(score_list) > 0:
    print("Low/average/median/high score: %d/%d/%d/%d" % (min(score_list),
                                                          numpy.average(score_list),
                                                          numpy.median(score_list),
                                                          max(score_list)))
