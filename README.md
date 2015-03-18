autograder
==========

This collection of scripts implements an automatic grader system for *Linux* that can be used to grade programming assignments written in a variety of languages. It also includes scripts to interact with Canvas.

In short, the normal workflow is:

* *ag.py download*  will download the newest non-late student submissions from Canvas. If the submission. If the submitted file is a tar, tgz, tar.gz, or zip file, the file will be extracted into a subfolder.

* *ag-grade.py* is provided by the instructor and will grade each of the assignments. In the case of programming assignments, this script can compile, run, and examine the output of a computer program. It creates an AUTOGRADE.txt file which contains a report of the automatic grading process. The instructor would use this file to assist with grading and/or share the file with the submitter.

* *ag.py stats* will display general information about the submissions and the scores.

* *ag.py email* emails the autograder reports to students.


Getting started
==============

* This code requires Linux.
* If you are using Canvas, create a file named ".canvas-token" in your home directory that contains:

```
self.CANVAS_API="https://canvas.instructure.com/api/v1/"
self.CANVAS_TOKEN="token-generated-in-canvas"
```

The first line should be the URL for the Canvas API. For Michigan Tech, for example, this URL should be "https://mtu.instructure.com/api/v1". The second line should contain a token that you must generate in Canvas and will be a string of characters and numbers. To generate one, login to Canvas, go to "Settings" and click on the "New Access Token" button.

* Next, make a file named "autograde-config.json" in the folder where you want to accept submissions that contains the following:

```
{                                                 // REMOVE THESE COMMENTS!
    "courseName":"CS4461 Networks - Spring 2015", // name of course on Canvas
    "assignmentName":"HW5: HTTP server",          // name of assignment on Canvas
    "subdirName":"autograder",                    // subdirectory to place submissions in
    "domainName":"mtu.edu",                       // domain name to use for email messages
    "emailSubject":"HW5: autograde results",      // subject line to use for email messages
    "emailUser":"user",                           // email username
    "emailPassword":"password",                   // email password
    "emailSmtp":"smtp.gmail.com",                 // smtp server
    "emailSmtpPort":"587"                         // smtp port
}
```

* Download canvas.py, autograder.py and ag.py onto your machine. If you want to install them in a single location, ensure that your PYTHONPATH and PATH environment variables includes the path where these files exist. Ensure that canvas.py and ag.py are executable.
* Put ag-grade.py in the same folder that contains "autograde-config.json".
* While in the same directory containing autograde-config.json and ag-grade.py:
    * Run "ag.py download" to download the newest non-late submissions.
    * Modify and then run "./ag-grade.py" to grade any submissions that were downloaded
    * Run "ag.py stats" to view results of the grading process
    * Run "ag.py email" to email the results to the students


Additional information
=====================

Submission download process
---------

If you run the "ag.py download" command repeatedly, it will only download the newest non-late submissions---but it will not download a submission again if the current downloaded copy is up-to-date. When it is necessary to download a newer submission to replace an old one, any existing AUTOGRADE.txt reports are discarded. You can also request to download a specific attempt of a specific user with "ag.py download username attempt#"

Locking a submission
-------------

Since the download script will always overwrite older submissions with newer, non-late submissions, sometimes it is useful to indicate that you do not want a submission to be overwritten when "ag.py download" is run. The "ag.py lock username" mechanism makes it possible to lock a particular submission. It can later be unlocked with "ag.py unlock username"

Grading submissions
--------------

A submission will only be graded if an AUTOGRADE.txt grade report is missing. If you only want to grade a specific submission(s), you can use "ag-grade.py username(s)".  If you want to force the grading to occur again on all submissions (for example, if the ag-grade.py script has been changed), you can run the "ag.py regrade" command to clear all AUTOGRADE.txt files for all users (or just specific users if usernames are provided).

A note about email
---------------

The *ag.py email* command will email autograder reports to students. It does not send the student a report if they have already received a copy of that report. Specifically, "ag-grade.py" will set a flag in the json metadata file for that submission indicating that an email has not been sent whenever a submission is autograded. As a result, you can download and email students repeatedly: Only new submissions will be downloaded and only the emails that need to get sent will get sent. You can run *ag.py emailCacheClear* if you want the system to assume that no students have been emailed reports previously.

If there are a group of students associated with a submission, the email will be sent to each student in the group.

If the Canvas login does not include an '@' symbol, then the domain name specified in autograde-config.json is appended to the end of the username.  This code has only been tested at MTU which uses Gmail. If you are using two-factor authentication with Google, you need to generate an 'application specific' password: https://support.google.com/accounts/answer/185833?hl=en




Useful files include:
==========

*canvas.py* implements a python module to interface with Canvas using the Instructure Canvas API. Besides being a module used by ag-download.py, it can also be run directly from the command-line. It allows an instructor to see their Canvas courses, list students in a course, list assignments in a course, list assignments that have been submitted, and download submissions.

*autograde.py* implements a python module that provides useful tools for automatic grading.


