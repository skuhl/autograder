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
    print(" download [username attempt#]")
    print("     Download the any updated submissions (ignoring late submissions)")

    print()
    print(" stats [usernames...]")
    print("     Display basic statistics about submissions")
    
    print()
    print(" email [usernames...]")
    print("     Sends emails containing the AUTOGRADE.txt reports to students as needed.")

    print()
    print(" lock [usernames...]")
    print(" unlock [usernames...]")
    print("     Lock or unlock submissions so subsequent downloads won't overwrite the submissions for one or more students.")

    print()
    print(" regrade [usernames...]")
    print("     Erase all AUTOGRADE.txt files to force complete regrading. Useful when the ag-grade.py script is changed by the instructor.")
    
    print()
    print(" emailClearCache [usernames...]")
    print("     Forces new emails to get sent to all students (this option is usually only useful for debugging the autograder)")

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
        agfile = os.path.join(thisDir, "AUTOGRADE.txt")
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
    


def removeELFs():
    # Look for ELF executables the user might have submitted and remove them!
    for dirpath, dnames, fnames in os.walk(subdirName):
        for f in fnames:            # for each file in tree
            f = os.path.join(dirpath, f)
            if os.path.isfile(f):   # check that it is a file
                with open(f, "rb") as fileBytes:  # open the file
                    magic = fileBytes.read(4)     # read 4 bytes
                    # print("".join("%02x" % b for b in magic))
                    # check that the 4 bytes match first 4 bytes of an ELF executable
                    if len(magic) >= 4 and magic[0] == 0x7f and magic[1] == 0x45 and magic[2]==0x4c and magic[3]==0x46:
                            print(f + " is ELF executable, removing")
                            os.unlink(f)

def stats(dirs):
    score_list=[]
    print("%-12s %s %14s %5s %5s %5s %5s" % ("name", "pts", "SubmitTime", "atmpt", "late", "lock", "email"))
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

        score="---"
        if os.path.exists(os.path.join(d, "AUTOGRADE.txt")):
            with open(os.path.join(d, "AUTOGRADE.txt"), 'r') as f:
                match = re.search("TOTAL.*: (.*)", f.read())
                if match.group(1):
                    score_int = int(match.group(1).strip())
                    score_list.append(score_int)
                    score = "%3d" % score_int

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

        print("%-12s %3s %14s %5d %5s %5s %5s" % (d, score, timeString, attempt, late, locked, emailed))

    print("Submission count: %d" % len(dirs))
    try:
        import numpy
        average = "%.1f" % numpy.average(score_list)
        median  = "%.1f" % numpy.median(score_list)
    except ImportError:
        average = "?"
        media = "?"
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

def emailStudent(senderEmail, studentUsername, subject, text):
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
    msg['From'] = formataddr( (str(Header(emailFromName, 'utf-8')),
                               emailFrom) )
    msg['To'] = ', '.join(recipients)
    part = MIMEBase("text", "plain")
    part.set_payload(text)
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', 'attachment; filename="{0}"'.format("AUTOGRADE.txt"))
    msg.attach(part)
    
    part = MIMEText("Your autograder report is attached.")
    msg.attach(part)
    emailSession.sendmail(senderEmail, recipients, msg.as_string())


def emailSend(dirs):
    # Login to email server
    if '@' in emailFrom:
        senderEmail = emailFrom;
    else:
        senderEmail = emailFrom + '@' + domainName
    emailLogin(senderEmail, emailPassword)

    # send email messages
    for thisDir in dirs:
        agFilename = thisDir + "/AUTOGRADE.txt"
        metadataFile = thisDir + "/AUTOGRADE.json"
        metadata = {}
        if os.path.exists(metadataFile):
            with open(metadataFile, "r") as f:
                metadata = json.load(f)
        if metadata.get('emailSent', 0):
            print("%-12s SKIPPING - Already emailed a report." % thisDir)
            continue;
        if not os.path.exists(agFilename):
            print("%-12s SKIPPING - AUTOGRADE.txt is missing." % thisDir)
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
                    content = content_file.read()
                    emailStudent(senderEmail, student['login_id'], emailSubject, content)
        else:
            print("%-12s Sending message to %s" % (thisDir, emailToAddr))
            with open(agFilename, 'r') as content_file:
                content = content_file.read()
                emailStudent(senderEmail, emailToAddr, emailSubject, content)

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
    removeELFs()
    
elif sys.argv[1] == 'email':
    os.chdir(subdirName)
    if len(sys.argv) > 2:
        emailSend(sys.argv[2:])
    else:
        emailSend(dirs)
else:
    print("Unknown action: %s" % sys.argv[1])
    exit(1)







    
