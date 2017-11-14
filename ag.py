#!/usr/bin/env python3
import shutil, os, stat, sys, re, json, datetime
import autograder,canvas
import smtplib

if sys.hexversion < 0x030000F0:
    print("This script requires Python 3")
    sys.exit(1)

if len(sys.argv) < 2:
    print("Usage: ag.py action [args]")
    print("Each action allows can be passed an optional argument:")

    print()
    print(" download")
    print(" download [username attempt#]")
    print("     Download any updated submissions (ignores late submissions unless you specifically specify an attempt that was late.)")

    print()
    print(" downloadlate [username]")
    print("     Download any updated submissions (including late submissions)")

    print()
    print(" stats [usernames...]")
    print("     Display basic statistics about submissions")
    
    print()
    print(" email [usernames...]")
    print("     Sends emails containing the AUTOGRADE.html reports to students as needed.")

    print()
    print(" emailsent [usernames...]")
    print("     Makes the autograder believe that it has already sent the student an email.")

    print()
    print(" emailClearCache [usernames...]")
    print("     Makes the autograder believe that no emails have been sent.")
    
    print()
    print(" lock [usernames...]")
    print(" unlock [usernames...]")
    print("     Lock or unlock submissions so subsequent downloads won't overwrite the submissions for one or more students.")

    print()
    print(" regrade [usernames...]")
    print("     Erase all AUTOGRADE.html files to force complete regrading. Useful when the ag-grade.py script is changed by the instructor.")

    print()
    print(" view username")
    print("     View autograder report via command line.")

    print()
    print(" viewgui username")
    print("     View autograder report via web browser.")

    
    sys.exit(1)

config = autograder.config()
settings = config.get()
subdirName = settings['subdirName']
courseName = settings['courseName']
assignmentName = settings['assignmentName']
emailSubject  = settings['emailSubject']
domainName    = settings['domainName']
emailFrom     = settings['emailFrom']
emailFromName = settings['emailFromName']
emailPassword = settings['emailPassword']
emailSmtp     = settings['emailSmtp']
emailSmtpPort = settings['emailSmtpPort']


def changeLock(dirs, lock):
    for thisDir in dirs:
        metadataFile = thisDir + "/AUTOGRADE.json"
        metadata = {}
        if os.path.exists(metadataFile):
            with open(metadataFile, "r") as f:
                metadata = json.load(f)
        metadata['locked']=lock
        with open(metadataFile, "w") as f:
            json.dump(metadata, f, indent=4)
def unlock(dirs):
    changeLock(dirs, 0)
def lock(dirs):
    changeLock(dirs, 1)
def regrade(dirs):
    for thisDir in dirs:
        agfile = os.path.join(thisDir, "AUTOGRADE.html")
        if os.path.exists(agfile):
            os.unlink(agfile)
    # Whenever a new autograde report is generated, we change the
    # metadata file to indicate that an email should be sent. Here, we
    # proactively do this so it is clear that an email message will
    # need to get sent.
    emailClearCache(dirs)
            

def emailClearCache(dirs):
    for thisDir in dirs:
        metadataFile = thisDir + "/AUTOGRADE.json"
        metadata = {}
        if os.path.exists(metadataFile):
            with open(metadataFile, "r") as f:
                metadata = json.load(f)
        metadata['emailSent']=0
        with open(metadataFile, "w") as f:
            json.dump(metadata, f, indent=4)


def emailSent(dirs):
    for thisDir in dirs:
        metadataFile = thisDir + "/AUTOGRADE.json"
        metadata = {}
        if os.path.exists(metadataFile):
            with open(metadataFile, "r") as f:
                metadata = json.load(f)
        metadata['emailSent']=1
        with open(metadataFile, "w") as f:
            json.dump(metadata, f, indent=4)


                            
def stats(dirs):
    score_list=[]
    print("%-12s %5s %9s %9s %14s %5s %5s %5s %5s" % ("name", "agPts", "agPtsOrig", "canvasPts", "SubmitTime", "atmpt", "late", "lock", "email"))
    for d in dirs:
        metadataFile = d + "/AUTOGRADE.json"
        metadata = {}
        if os.path.exists(metadataFile):
            with open(metadataFile, "r") as f:
                metadata = json.load(f)

        if metadata.get('emailSent', 0):
            emailed="X"
        else:
            emailed=""

        score="  ---"
        if 'autograderScore' in metadata and os.path.exists(os.path.join(d, "AUTOGRADE.html")):
                score = "%5d" % metadata['autograderScore']
                score_list.append(int(metadata['autograderScore']))

        scoreOrig="      ---"
        if 'autograderScorePreAdjustment' in metadata and os.path.exists(os.path.join(d, "AUTOGRADE.html")):
                scoreOrig = "%9d" % metadata['autograderScorePreAdjustment']

                
        canvasScore="    --- "
        if 'canvasSubmission' in metadata:
            canvasScore_string = metadata['canvasSubmission'].get('score', "0")
            if canvasScore_string:
                canvasScore_int = int(canvasScore_string)
                
                if metadata['canvasSubmission']['grade_matches_current_submission'] == False:                
                    canvasScore = "%8d*"%canvasScore_int
                else:
                    canvasScore = "%8d "%canvasScore_int
            


        attempt=0
        timeString=''
        late=''
        locked=''
        if 'canvasSubmission' in metadata:
            attempt = metadata['canvasSubmission'].get('attempt', "0")
            if metadata['canvasSubmission']['late']:
                late="X"
            if 'locked' in metadata and metadata['locked']==1:
                locked="X"

            if 'submitted_at' in metadata['canvasSubmission']:
                import datetime
                utc_dt = datetime.datetime.strptime(metadata['canvasSubmission']['submitted_at'],
                                                    '%Y-%m-%dT%H:%M:%SZ')
                utc_dt = utc_dt.replace(tzinfo=datetime.timezone.utc)
                timeString = canvas.canvas.prettyDate(utc_dt, datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc))

        print("%-12s %5s %9s %9s %14s %5d %5s %5s %5s" % (d, score, scoreOrig, canvasScore, timeString, attempt, late, locked, emailed))

    print("Submission count: %d" % len(dirs))

    average = "?"
    media = "?"
    try:
        import numpy
        if len(score_list) > 0:
            average = "%.1f" % numpy.average(score_list)
            median  = "%.1f" % numpy.median(score_list)
    except ImportError:
        print("Install numpy for full statistics information.")
        
    if len(score_list) > 0:
        print("Low/average/median/high score: %d/%s/%s/%d" % (min(score_list),
                                                              average, median,
                                                              max(score_list)))
emailSession = None


def emailLogin(senderEmail, mypassword):
    global emailSession
    emailSession = smtplib.SMTP(emailSmtp, emailSmtpPort)
    emailSession.ehlo()
    emailSession.starttls()
    emailSession.ehlo
    emailSession.login(senderEmail, mypassword)

def emailLogout():
    global emailSession
    emailSession.quit()

def emailStudent(senderEmail, studentUsername, subject, htmlattach, message):
    if '@' in studentUsername:
        recipients = [ studentUsername ]
    else:
        recipients = [ studentUsername + "@" + domainName ]   # list of recipients

    global emailSession

    # Send the report in the body of the email.
    # headers = ["From: " + senderEmail,
    #            "Subject: " + subject,
    #            "To: " + ', '.join(recipients),
    #            "MIME-Version: 1.0",
    #            "Content-Type: text/plain"]
    # headers = "\r\n".join(headers)
    # emailSession.sendmail(senderEmail, recipients, headers + "\r\n\r\n" + text)

    # Send the report as an attachment.
    from email.mime.multipart import MIMEMultipart
    from email.mime.base import MIMEBase
    from email.mime.text import MIMEText
    from email import encoders
    from email.utils import formataddr
    msg = MIMEMultipart()
    msg['Subject'] = subject
    msg['From'] = formataddr( (emailFromName, emailFrom) )
    msg['To'] = ', '.join(recipients)
    part = MIMEBase("text", "html")
    part.set_payload(htmlattach)
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', 'attachment; filename="{0}"'.format("AUTOGRADE.html"))
    msg.attach(part)

    part = MIMEText(message)
    msg.attach(part)
    emailSession.sendmail(senderEmail, recipients, msg.as_string())


def getAllScores():
    dirs = [name for name in os.listdir(".") if os.path.isdir(name)]
    allScores = []
    for d in dirs:
        metadataFile = d + "/AUTOGRADE.json"
        metadata = {}
        if os.path.exists(metadataFile):
            with open(metadataFile, "r") as f:
                metadata = json.load(f)
        if 'autograderScore' in metadata and os.path.exists(os.path.join(d, "AUTOGRADE.html")):
            allScores.append(int(metadata['autograderScore']))
    allScores.sort()
    return allScores;

def getSumOfAttempts():
    dirs = [name for name in os.listdir(".") if os.path.isdir(name)]
    attempts = 0;
    for d in dirs:
        metadataFile = d + "/AUTOGRADE.json"
        metadata = {}
        if os.path.exists(metadataFile):
            with open(metadataFile, "r") as f:
                metadata = json.load(f)
        if 'canvasSubmission' in metadata:
            attempts += int(metadata['canvasSubmission'].get('attempt', 0))

    return attempts;
    



import statistics
def emailSend(dirs):
    # Login to email server
    if '@' in emailFrom:
        senderEmail = emailFrom;
    else:
        senderEmail = emailFrom + '@' + domainName
    emailLogin(senderEmail, emailPassword)

    message = "Your autograder report is attached. "
    allScores = getAllScores()
    totalAttempts = getSumOfAttempts()
    if len(allScores) == 1:
        message += "Congratulations. You are the first and only student to have submitted something. "
    elif len(allScores) > 1:
        message += "%d students have made %d submissions for this assignment (an average of about %d submissions per student). " % (len(allScores), totalAttempts, int(round(totalAttempts/len(allScores))))

    if len(allScores) > 5:
        message += "The average score is %d. " % int(round(statistics.mean(allScores)))
        message += "The median score is %d. " % int(round(statistics.median(allScores)))
        try:
            message += "The most common score is %d. " % statistics.mode(allScores)
        except statistics.StatisticsError:
            # If there is more than one mode, this exception occurs.
            pass
        message += "The scores range from %d to %d. " % (allScores[0], allScores[-1])

    # send email messages
    for thisDir in dirs:
        agFilename = thisDir + "/AUTOGRADE.html"
        metadataFile = thisDir + "/AUTOGRADE.json"
        metadata = {}
        if os.path.exists(metadataFile):
            with open(metadataFile, "r") as f:
                metadata = json.load(f)
        if metadata.get('emailSent', 0):
            print("%-12s SKIPPING - Already emailed most recent report." % thisDir)
            continue;
        if not os.path.exists(agFilename):
            print("%-12s SKIPPING - AUTOGRADE.html is missing." % thisDir)
            continue;

        # Start by assuming directory name is the username
        emailToAddr = thisDir

        # If there is metadata file, get the name of the submitter
        if metadata.get("canvasStudent", False):
            emailToAddr = metadata['canvasStudent']['login_id']

        # If this directory seems to be a group...
        group = metadata.get("canvasStudentsInGroup", None)
        if group:
            # Email every student in the group
            for student in group:
                print("%-12s Sending message to group member %s" % (thisDir, student['login_id']))
                with open(agFilename, 'r') as content_file:
                    attachment = content_file.read()
                    emailStudent(senderEmail, student['login_id'], emailSubject, attachment, message)
        else:
            print("%-12s Sending message to %s" % (thisDir, emailToAddr))
            with open(agFilename, 'r') as content_file:
                content = content_file.read()
                emailStudent(senderEmail, emailToAddr, emailSubject, content, message)

        metadata['emailSubject'] = emailSubject
        metadata['emailCtime'] = str(datetime.datetime.now().ctime())
        metadata['emailSent']=1
        with open(metadataFile, "w") as f:
            json.dump(metadata, f, indent=4)

    # logout
    emailLogout()


    
        
# Get a list of subdirectories (each student submission will be in its own subdirectory)
if not os.path.exists(subdirName):
    os.mkdir(subdirName);

dirs = [name for name in os.listdir(subdirName) if os.path.isdir(os.path.join(subdirName, name))]
dirs.sort()

if sys.argv[1] == "lock":
    os.chdir(subdirName)
    if len(sys.argv) > 2:
        lock(sys.argv[2:])
    else:
        lock(dirs)
elif sys.argv[1] == "unlock":
    os.chdir(subdirName)
    if len(sys.argv) > 2:
        unlock(sys.argv[2:])
    else:
        unlock(dirs)
elif sys.argv[1] == 'regrade':
    os.chdir(subdirName)        
    if len(sys.argv) > 2:
        regrade(sys.argv[2:])
    else:
        regrade(dirs)
elif sys.argv[1] == 'emailClearCache':
    os.chdir(subdirName)        
    if len(sys.argv) > 2:
        emailClearCache(sys.argv[2:])
    else:
        emailClearCache(dirs)

elif sys.argv[1] == 'stats' or sys.argv[1] == 'stat':
    os.chdir(subdirName)
    if len(sys.argv) > 2:
        stats(sys.argv[2:])
    else:
        stats(dirs)

elif sys.argv[1] == 'download':
    c = canvas.canvas()
    if len(sys.argv) == 2:
        c.downloadAssignment(courseName=courseName, assignmentName=assignmentName, subdirName=subdirName)
    elif len(sys.argv) == 3:
        c.downloadAssignment(courseName=courseName, assignmentName=assignmentName, subdirName=subdirName, userid=sys.argv[2])
    elif len(sys.argv) == 4:
        # Delete the any existing submission with the given name
        if os.path.exists(os.path.join(subdirName, sys.argv[2])):
            shutil.rmtree(os.path.join(subdirName, sys.argv[2]))
        c.downloadAssignment(courseName=courseName, assignmentName=assignmentName, subdirName=subdirName, userid=sys.argv[2], attempt=int(sys.argv[3]))
    else:
        print("Usage:")
        print(" ag.py download   --> downloads all non-late submissions")
        print(" ag.py download username attempt# --> downloads one specific submission (even if it is late)")
        exit(1)

elif sys.argv[1] == 'downloadlate':
    c = canvas.canvas()
    if len(sys.argv) == 2:
        c.downloadAssignment(courseName=courseName, assignmentName=assignmentName, subdirName=subdirName, acceptLate=True)
    if len(sys.argv) == 3:
        # Delete the any existing submission with the given name
        if os.path.exists(os.path.join(subdirName, sys.argv[2])):
            shutil.rmtree(os.path.join(subdirName, sys.argv[2]))
        c.downloadAssignment(courseName=courseName, assignmentName=assignmentName, subdirName=subdirName, userid=sys.argv[2], acceptLate=True)
    else:
        print("Usage:")
        print(" ag.py downloadlate   --> downloads all submissions (including late ones)")
        print(" ag.py downloadlate username  --> download newest submission from user (including late ones)")
        print(" Use the 'download' command to download a specific submission")
        exit(1)
        
elif sys.argv[1] == 'email':
    os.chdir(subdirName)
    if len(sys.argv) > 2:
        emailSend(sys.argv[2:])
    else:
        emailSend(dirs)

elif sys.argv[1] == 'emailsent':
    os.chdir(subdirName)
    if len(sys.argv) > 2:
        emailSent(sys.argv[2:])
    else:
        emailSent(dirs)


elif sys.argv[1] == 'view':
    if len(sys.argv) == 3:
        path = os.path.join(subdirName, sys.argv[2], "AUTOGRADE.html")
        print("viewing: %s"%path)
        os.system('links -codepage utf-8 -dump -width %d %s | less' %
                  (shutil.get_terminal_size((80,20)).columns,
                   path))
    else:
        print("Usage:")
        print(" ag.py view username")
        exit(1)

elif sys.argv[1] == 'viewgui':
    if len(sys.argv) == 3:
        path = os.path.join(subdirName, sys.argv[2], "AUTOGRADE.html")
        print("viewing: %s"%path)
        os.execvp('xdg-open', ['xdg-open',path])
    else:
        print("Usage:")
        print(" ag.py viewgui username")
        exit(1)

        
        
else:
    print("Unknown action: %s" % sys.argv[1])
    exit(1)
    
