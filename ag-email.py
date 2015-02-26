#!/usr/bin/env python3

import sys, os
import datetime, smtplib
import autograder

if sys.hexversion < 0x030000F0:
    print("This script requires Python 3")
    sys.exit(1)


# Load configuration information
config        = autograder.config()
settings      = config.get()
subdirName    = settings['subdirName']
emailSubject  = settings['emailSubject']
domainName    = settings['domainName']
emailUser     = settings['emailUser']
emailPassword = settings['emailPassword']
emailSmtp     = settings['emailSmtp']
emailSmtpPort = settings['emailSmtpPort']
    


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
    recipients = [ studentUsername + "@" + domainName ]   # list of recipients
    body = text  # body of message
    headers = ["From: " + senderEmail,
               "Subject: " + subject,
               "To: " + ', '.join(recipients),
               "MIME-Version: 1.0",
               "Content-Type: text/plain"]
    headers = "\r\n".join(headers)
    global emailSession
    emailSession.sendmail(senderEmail, recipients, headers + "\r\n\r\n" + body)




os.chdir(subdirName)
cwd = os.getcwd()
dirs = [name for name in os.listdir(cwd) if os.path.isdir(os.path.join(cwd, name))]
dirs.sort()

# Login to email server
print(emailUser)
senderEmail = emailUser + '@' + domainName
emailLogin(senderEmail, emailPassword)

# send email messages
for thisDir in dirs:
    agFilename = thisDir + "/AUTOGRADE.txt"
    agEmailedFilename = thisDir + "/AUTOGRADE-EMAILED.txt"

    if not os.path.exists(agFilename):
        print(thisDir + " SKIPPING - AUTOGRADE.txt is missing.")
        continue;
    if os.path.exists(agEmailedFilename):
        print(thisDir + " SKIPPING - AUTOGRADE-EMAILED.txt is present; report has already been emailed.")
        continue;
    # We don't care if AUTOGRADE-DONE.txt is present since that is
    # only used to determine if we need to rerun the autograder---not
    # to determine if we need to email them or not.

    print("Sending message to: "+thisDir+"@"+domainName)
    with open(agFilename, 'r') as content_file:
        content = content_file.read()
    emailStudent(senderEmail, thisDir, emailSubject, content)

    with open(agEmailedFilename, "w") as f:
        f.write("We emailed this student the autograder report at "+str(datetime.datetime.now().ctime()) + " with the subject: " + emailSubject + "\n")

# logout
emailLogout()
