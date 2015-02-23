#!/usr/bin/env python3

import sys, os
import getpass, smtplib

if sys.hexversion < 0x030000F0:
    print("This script requires Python 3")
    sys.exit(1)


emailSession = None
domain = None

def emailLogin(senderEmail, mypassword):
    global emailSession
    emailSession = smtplib.SMTP("smtp.gmail.com", 587)
    emailSession.ehlo()
    emailSession.starttls()
    emailSession.ehlo
    emailSession.login(senderEmail, mypassword)

def emailLogout():
    global emailSession
    emailSession.quit()

def emailStudent(senderEmail, studentUsername, subject, text):
    recipients = [ studentUsername + "@" + domain ]   # list of recipients
    body = text  # body of message
    headers = ["From: " + senderEmail,
               "Subject: " + subject,
               "To: " + ', '.join(recipients),
               "MIME-Version: 1.0",
               "Content-Type: text/plain"]
    headers = "\r\n".join(headers)
    global emailSession
    emailSession.sendmail(senderEmail, recipients, headers + "\r\n\r\n" + body)


import sys
print("Enter the directory that contains subdirectories (one per student, named after students' usernames):")
subdir = sys.stdin.readline().strip()

if not os.path.exists(subdir):
    print("Directory doesn't exist. Exiting.")
    exit(1)

print("Enter the domain name of the sender and recipients:")
domain = sys.stdin.readline().strip()


os.chdir(subdir)
cwd = os.getcwd()
dirs = [name for name in os.listdir(cwd) if os.path.isdir(os.path.join(cwd, name))]
dirs.sort()

errorOccured = False
for thisDir in dirs:
    if not os.path.exists(thisDir + "/AUTOGRADE.txt"):
        print("ERROR: No AUTOGRADE.txt file to send to "+thisDir+"@"+domain)
        errorOccured = True
if errorOccured:
    print("Press any key to email reports or Ctrl+C to exit.")
    sys.stdin.readline()

print("Enter the subject line for the email message.")
subject = sys.stdin.readline().strip()

# Login to email server
senderEmail = getpass.getuser() + '@' + domain
mypassword = getpass.getpass("Password for " + senderEmail + ": ")
emailLogin(senderEmail, mypassword)


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

    print("Sending message to: "+thisDir+"@"+domain)
    with open(agFilename, 'r') as content_file:
        content = content_file.read()
    #emailStudent(senderEmail, thisDir, subject, content)
    with open(agEmaieldFilename, "w") as f:
        f.write("Autograder report has been emailed to the student\n")

# logout
emailLogout()
