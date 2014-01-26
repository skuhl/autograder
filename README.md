autograder
==========

This collection of scripts implements an automatic grader system for *Linux* that can be used to grade programming assignments written in a variety of languages. These scripts assume that students use Instructure Canvas to submit a single .tgz, .tar.gz, or .zip file containing all of their code.

*ag-download.py* downloads all non-late student submissions from Canvas and extracts the submissions in to subfolder. Each student has a subfolder that has a name based on their username. This script uses the *canvas.py* module.

*ag-grade.py* is a script that the instructor must modify to actually grade the assignments. It can check to make sure that the student submitted the proper files, can try compiling the code (and deduct points for compiler warnings/errors), run test cases (and check the program prints the correct messages and/or creates the correct output files), etc. When completed, each student will have an AUTOGRADE.txt file in their directory and the last line of the file will contain their "autograder" score (and the instructor can choose to adjust it as needed). Currently, this script does not actually enter any grades for the student on Canvas---assigning actual grades must be done manually. This script uses the *autograder.py* module.

*ag-email.py* emails the AUTOGRADE.txt files to students. This script assumes that their email address is username@domain.edu where "username" is the student's Canvas username and "domain.edu" is set by the user. It also assumes that your university is using Gmail (although this can be easily modified). If you are using two-factor authentication with Google, you need to generate an 'application specific' password: https://support.google.com/accounts/answer/185833?hl=en

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

* Run "ag-download.py"
* Run "ag-grade.py"
* If you want to email the results to students, run "ag-email.py"
