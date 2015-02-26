#!/usr/bin/env python3
import os,sys,re,datetime,time
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
    emailed=""
    if os.path.exists(os.path.join(d, "AUTOGRADE-EMAILED.txt")):
        emailed="Emailed"
    done=""
    if os.path.exists(os.path.join(d, "AUTOGRADE-DONE.txt")):
        done="Done"
    score="?"
    if os.path.exists(os.path.join(d, "AUTOGRADE.txt")):
        with open(os.path.join(d, "AUTOGRADE.txt"), 'r') as f:
            match = re.search("TOTAL.*: (.*)", f.read())
            if match.group(1):
                score = match.group(1).strip()
                score_list.append(int(score))
    timeString=""
    if os.path.exists(os.path.join(d, "AUTOGRADE-TIME.txt")):
        with open(os.path.join(d, "AUTOGRADE-TIME.txt"), 'r') as f:
            timestring = f.read().strip()
            dt = datetime.datetime.strptime(timestring, '%a %b %d %H:%M:%S %Y')
            timeString = canvas.canvas.prettyDate(dt, datetime.datetime.now())

        
    print("%20s %8s %5s %4s - %s" % (d, emailed,done,score, timeString))

print("Submission count: %d" % len(dirs))
print("Low/average/median/high score: %d/%d/%d/%d" % (min(score_list),
                                                      numpy.average(score_list),
                                                      numpy.median(score_list),
                                                      max(score_list)))
