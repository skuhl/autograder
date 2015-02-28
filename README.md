autograder
==========

This collection of scripts implements an automatic grader system for *Linux* that can be used to grade programming assignments written in a variety of languages. These scripts assume that students use Instructure Canvas to submit a single .tgz, .tar.gz, or .zip file containing all of their code.

The command *ag.py download* will download the newest non-late student submission from canvas and extract the submissions into subfolders based on the student usernames. 

*ag-grade.py* is a script that the instructor must modify to actually grade the assignments. It can check to make sure that the student submitted the proper files, can try compiling the code (and deduct points for compiler warnings/errors), run test cases (and check the program prints the correct messages and/or creates the correct output files), etc. When completed, each student will have an AUTOGRADE.txt file in their directory and the last line of the file will contain their "autograder" score (and the instructor can choose to adjust it as needed). Currently, this script does not enter any grades for the student on Canvas---grade assignment must be done manually.

The *ag.py email* command will email autograder reports to students. This script assumes that their email address is username@domain.edu where "username" is the student's Canvas username and "domain.edu" is set by the user. It also assumes that your university is using Gmail (although this can be easily modified). If you are using two-factor authentication with Google, you need to generate an 'application specific' password: https://support.google.com/accounts/answer/185833?hl=en

The *ag.py stats* command provides an overview of all of the submissions you have received (scores, submission date, attempt number, if the submission is late, and if the latest autograder report has been emailed to the students).


Other useful files include:
------------------------------

*canvas.py* implements a python module to interface with Canvas using the Instructure Canvas API. Besides being a module used by ag-download.py, it can also be run directly from the command-line. It allows an instructor to see their Canvas courses, list students in a course, list assignments in a course, list assignments that have been submitted, and download submissions.

*autograde.py* implements a python module that provides useful tools for automatic grading.


Getting started
------------------------------

* Make sure you are on a Linux machine
* If you are using canvas, create a file named ".canvas-token" in your home directory that contains:

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
