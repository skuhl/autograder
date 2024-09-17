import hashlib
import os
import subprocess, threading
import shutil
import glob
import stat
import string
import signal
import time,datetime
import json
import tempfile
import cgi
import html
import resource
import re

# Set to True if you wish to run the autograder scripts as root, but
# then have the script automatically switch to a different user
# account before running the submitted code. Changing this to True
# also requires that you set the user ids correctly.
switchUser=True

# The id of the user that the program is normally run with. Use "id" command to retrieve these.
normalUid=1000
normalGid=1000

# The id of the user that the submissions should be run as.
autograderUid=1001


class bcolors:
    FAIL = '\033[91m\033[1m'  # red, bold
    WARN = '\033[93m\033[1m'  # yellow, bold
    ENDC = '\033[0m'          # reset colors back to normal
    BOLD = '\033[1m'


class config():
    configfile = ""
    settings = {}

    def __init__(self, configfile="autograde-config.json"):
        """Load a config file, overwrite existing settings"""
        self.configfile = os.path.abspath(configfile)
        if os.path.exists(self.configfile):
            with open(self.configfile, "r") as f:
                self.settings = json.load(f)
        else:
            print("autograde-config.json file is missing.")
            exit(1)


    def get(self):
        return self.settings

    def set(self, newSettings):
        self.settings = newSettings

    def write(self):
        with open(self.configfile, "w") as f:
            json.dump(self.settings, f, indent=4)
            # add trailing newline
            f.write('\n')


# http://stackoverflow.com/questions/1191374/subprocess-with-timeout
class Command(object):
    def __init__(self, cmd):
        self.cmd = cmd
        self.cmdShort = cmd[0]
        self.cmdSpaces = " ".join(cmd)
        self.process = None

        self.timeout = 1

        self.stdoutdata = ""
        self.stderrdata = ""
        self.retcode = 0
        self.didRun = False
        self.tooSlow = False


    def setProcessLimits(x):
        # This is called after fork and before exec. Any messages
        # printed here will look like the program that we are calling
        # printed them out.

        #print("pre switch user")
        if switchUser:
            os.setreuid(autograderUid,autograderUid)
            if os.geteuid() == 0:
                print("Still root after trying to switch to autograder user?")
                exit(1)
        else:
            # If we are not switching to a different user, make sure that we don't run as root.
            if os.geteuid() == 0:
                print("Halting. Do not run submitted programs as root.")
                exit(1)

        #print("post switch user")

        #print("Preexec start")
        if os.setpgrp() == -1:  # put all processes in the same process group so we can kill it and all children it creates.
            print("Failed to set process group!")
        #print("Preexec middle")

        def limitHelper(limitType, limit):
            # limit is a string referring to a previously set environment variable.
            if limit in os.environ:
                limit = int(os.environ[limit])
                (soft, hard) = resource.getrlimit(limitType)
                #print("soft %d, hard %d, requested %d\n" % (soft, hard, limit))
                if hard > 0 and limit > hard:
                    limit = hard
                resource.setrlimit(limitType, (limit, limit))

        limitHelper(resource.RLIMIT_NPROC, "ULIMIT_NPROC")
        limitHelper(resource.RLIMIT_AS, "ULIMIT_AS")
        limitHelper(resource.RLIMIT_DATA, "ULIMIT_DATA")


    def run(self, autogradeobj, timeout=5, stdindata=None, workToDoWhileRunning=None):
        def target():

            #print("target %s"%str(self.cmd))
            # To print current number of used processes, run: ps -eLF | grep $USER | wc -l
            os.environ["ULIMIT_NPROC"] = str(1024*4)            # Maximum number of processes
            os.environ["ULIMIT_DATA"]  = str(1024*1024*1024*8)  # 8 GB of memory
            os.environ["ULIMIT_FSIZE"] = str(1024*1024*1024*50) # 50 GB of space for files

            limitString  = "%s: Limits are " % self.cmdShort
            limitString += "time="  + str(timeout) + "sec "
            limitString += "memory=" + autogradeobj.humanSize(int(os.environ["ULIMIT_DATA"]))  + " "
            limitString += "fsize="  + autogradeobj.humanSize(int(os.environ["ULIMIT_FSIZE"])) + " "

            msg='%s: Thread started: <b>%s</b><br>' % (self.cmdShort, self.cmdSpaces)
            msg+=limitString
            autogradeobj.log_generic(msg, deductPoints=0, needSanitize=False)
            startTime = time.time()

            try:
                # write stderr/stdout to temp file in case students print tons of stuff out.
                #print("mkstemp %s"%str(self.cmd))
                stdoutFile = tempfile.mkstemp(prefix="ag-"+autogradeobj.username+"-stdout-")
                stderrFile = tempfile.mkstemp(prefix="ag-"+autogradeobj.username+"-stderr-")
                #print("popen %s"%str(self.cmd))

                # If we run the program directly, stdout and stderr
                # messages might not be fully written out before a
                # program crashes---making it difficult for students
                # to see what is going on. stdbuf seems to be the best
                # way to fix this. unbuffer also works but seems to
                # make the autograder fail to detect segfaults.
                fixBuffering = []
                if os.path.exists("/usr/bin/stdbuf"):
                    # Disabled stderr and stdout buffering; leave stdin buffering
                    fixBuffering = [ "/usr/bin/stdbuf", "-o0", "-e0" ]
                elif os.path.exists("/usr/bin/unbuffer"):
                    fixBuffering = ["/usr/bin/unbuffer"]
                if len(fixBuffering) > 0:
                    # stdbuf and unbuffer make our code fail to
                    # produce an OSerror when the program doesn't
                    # exist. So, we raise an OSError ourself if we
                    # can't find the executable.
                    if autogradeobj.which(self.cmd[0]) == None:
                        raise OSError

                my_env = os.environ.copy()
                my_env["GCC_COLORS"] = ""
                my_env["TERM"]="dumb"

                if stdindata:
                    self.process = subprocess.Popen(fixBuffering+self.cmd, stdin=subprocess.PIPE, stdout=stdoutFile[0], stderr=stderrFile[0], preexec_fn=self.setProcessLimits, env=my_env)
                    with autogradeobj.logLock:
                        autogradeobj.log("<tr>")
                        autogradeobj.log_lineNumber()
                        autogradeobj.log("<td></td><td>%s: Data sent to stdin:" % self.cmdShort)
                        autogradeobj.log_pre(str(stdindata))
                        autogradeobj.log("</td></tr>")
                    try:
                        # An IOError can occur if we can't write or close due to a broken pipe.
                        self.process.stdin.write(bytes(stdindata, encoding='ascii'))
                        self.process.stdin.close()
                    except:
                        pass
                else:
                    # No stdin provided.
                    self.process = subprocess.Popen(fixBuffering+self.cmd, stdout=stdoutFile[0], stderr=stderrFile[0], preexec_fn=self.setProcessLimits, env=my_env)

                #print("wait %s"%str(self.cmd))
                self.process.wait()
                #print("wait after - %s"%str(self.cmd))

                # Close the temp files we wrote to, get an
                # (potentially abbreviated) string from the file,
                # delete the file.
                #print("close stdout - %s"%str(self.cmd))
                os.close(stdoutFile[0])
                self.stdoutdata = autogradeobj.get_abbrv_string_from_file(stdoutFile[1])
                os.unlink(stdoutFile[1])

                #print("close stderr - %s"%str(self.cmd))
                os.close(stderrFile[0])
                self.stderrdata = autogradeobj.get_abbrv_string_from_file(stderrFile[1])
                os.unlink(stderrFile[1])

                self.retcode = self.process.returncode
                self.didRun = True
            except OSError as e:
                autogradeobj.log_addEntry("%s: Unable to start process: %s" % (self.cmdShort, self.cmdSpaces))
                self.didRun = False
            elapsedTime = "%0.2fsec" % (time.time()-startTime)
            if self.retcode < 0:
                autogradeobj.log_addEntry('%s: Exited after %s due to signal %d %s' % (self.cmdShort, elapsedTime, -self.retcode, autogradeobj.signal_to_string(-self.retcode)))
            else:
                autogradeobj.log_addEntry('%s: Exited after %s with return code %d' % (self.cmdShort, elapsedTime, self.retcode))

        # END definition of target() function.

        try:
            if switchUser==False and os.geteuid() == 0:
                print("Don't set switchUser==False and grade student submissions as root since student submissions would be run as root.")
                exit(1)

            if switchUser==True and os.geteuid() != 0:
                print("If switchUser==True, you should run this as root.")
                exit(1)

            if switchUser==True and os.geteuid() == 0:
                # Don't kill processes if the user is intentionally running multiple processes via workToDoWhileRunning() function
                if threading.activeCount() == 1:
                    import pwd
                    username = pwd.getpwuid(autograderUid)[0]
                    subprocess.call(['killall', '-u', username, '-SIGINT'])
                    time.sleep(.1)
                    subprocess.call(['killall', '-u', username, '-SIGSTOP'])
                    time.sleep(.1)
                    subprocess.call(['killall', '-u', username, '-SIGKILL'])

            #print("prepare thread - %s"%str(self.cmd))
            thread = threading.Thread(target=target)
            #print("start thread - %s"%str(self.cmd))

            thread.start()
            if workToDoWhileRunning:
                # time.sleep(.2) # give time for process to start.
                #
                # IMPORTANT: If workToDoWhileRunning hangs, then our
                # timeout mechanism won't work because we will not
                # return from this function.
                workToDoWhileRunning()
            #print("join before - %s"%str(self.cmd))
            thread.join(timeout)
            #print("join after - %s"%str(self.cmd))

            if switchUser and os.geteuid() == 0:
                os.chown(autogradeobj.logFile, normalUid, -1)


            # Check to see if we timed out
            self.tooSlow = False
            if thread.is_alive():
                autogradeobj.log_addEntry("%s: Ran for more than %d seconds. Terminating process..." % (self.cmdShort, timeout))
                self.tooSlow = True

                # Try to politely kill the process
                if self.process != None:
                    try:
                        #print("killpg 1 - %s"%str(self.cmd))
                        os.killpg(self.process.pid, signal.SIGINT) # send Ctrl+C to process group
                        # self.process.send_signal(signal.SIGINT)    # send Ctrl+C to the parent process
                        time.sleep(.3)  # give process a chance to cleanup (for example valgrind printing its final summary)
                        #print("killpg 2 - %s"%str(self.cmd))
                        os.killpg(self.process.pid, signal.SIGKILL) # kill the process group
                    except ProcessLookupError:
                        # print("ProcessLookupError - %s"%str(self.cmd))
                        #
                        # ProcessLookupError occurs if the PID is
                        # already killed. This seems to happen
                        # sometimes when we try to write to
                        # stdin.
                        pass

                    # Make sure that we join up with the thread. It should be dead now.
                    thread.join(.5)

            # In the unlikely event the thread is still alive, exit so
            # we know something went wrong.
            if thread.is_alive():
                print("%s: We failed to kill thread after timeout was reached. Exiting." % self.cmdShort)
                exit(1)


        # Without this, Ctrl+C will cause python to exit---but we will
        # be forced to wait until the process we are running times out
        # too. With this, we try to exit gracefully.
        except KeyboardInterrupt as e:
            os.killpg(self.process.pid, signal.SIGKILL)
            thread.join(.5)
            raise

        return (self.didRun, self.tooSlow, self.retcode, self.stdoutdata, self.stderrdata)


class autograder():
    def __init__(self, username, totalPoints=100):
        self.lineNumber = 0
        self.logPointsTotal = totalPoints


        # The temporary location of the autograder report file. It
        # will be moved to the student submission directory when the
        # autograder is complete (i.e., cleanup() is called).
        self.tempdir = tempfile.mkdtemp(prefix="autograder-"+username+"-")
        if switchUser:
            os.chown(self.tempdir, autograderUid, 0)
            os.chmod(self.tempdir, 0o770)
        self.logFile = os.path.join(self.tempdir, "report.html")
        # Prevent multiple threads from writing to log file at same time.
        self.logLock = threading.Lock()

        # Absolute path that we need to chdir back to when finished
        self.origwd = os.getcwd()

        # Absolute path to the folder containing the student
        # submission.
        self.directory = os.path.join(self.origwd, username)

        # The autograder will do its work in a working directory
        self.workingDirectory = os.path.join(self.tempdir, "working")
        os.mkdir(self.workingDirectory)
        if switchUser:
            os.chown(self.workingDirectory, autograderUid, 0)
            os.chmod(self.workingDirectory, 0o770)
        self.username = username

        # Copy the student's submission into the working
        # directory. The only thing that needs to be copied back to
        # the original submission is the AUTOGRADE.txt file.
        self.pristine(quiet=True) ## This also cd's into self.workingDirectory

        # Print a header for this student to the console and log file.
        print(bcolors.BOLD + username + bcolors.ENDC)

        self.log("<!DOCTYPE html>")
        self.log("<html lang='en'>")
        self.log("<head>")
        self.log("<meta charset='utf-8'>")
        self.log("<title>%s - Autograder report</title>" % username)
        self.log("<style>")
        self.log("table, th, td { border: 1px solid #eee; margin: 0px; border-collapse: collapse; border-spacing: 0px; margin: 0px; }")

        self.log("table td:nth-child(1) { font-family: monospace; text-align: right; color: #999; }")
        self.log("table td:nth-child(2) { color: darkred; font-weight: bold; font-size: 130%; text-align: center }")

        self.log("table { width: 100%; }")
        self.log("div.preformatcode { max-height: 20em; width: 80vw; overflow: auto; background-color: #eee; resize: both; }")
        self.log("h2 { margin: 0px; font-size: 130%; }")
        self.log("pre { margin: 2px; white-space: pre-wrap}")
        self.log("body { font-family: sans }")

        self.log("</style>")

        self.log("</head><body>")
        self.log("<h1>%s</h1>"%username)
        self.log("<p><i>Gmail users:</i> This page may be easier to read if you download the file and then view it (Gmail removes some of the formatting).")
        self.log("<table>")
        self.log("<tr><th></th><th>Points</th><th>Details</th></tr>")

        self.log_addEntry("Autograder ran at: %s" % str(datetime.datetime.now().ctime()))


        # Add some basic information to AUTOGRADE.html so that students
        # can figure out exactly which submission the autograder
        # graded. This data is retrieved from the AUTOGRADE.json
        # metadata file.
        metadataFile = os.path.join(self.directory, "AUTOGRADE.json")
        metadata = {}
        if os.path.exists(metadataFile):
            with open(metadataFile, "r") as f:
                metadata = json.load(f)

        if 'canvasSubmission' in metadata:
            cs = metadata['canvasSubmission']
            if 'submitted_at' in cs:
                utc_dt = datetime.datetime.strptime(cs['submitted_at'],'%Y-%m-%dT%H:%M:%SZ')
                dt = utc_dt.replace(tzinfo=datetime.timezone.utc).astimezone(tz=None)
                self.log_addEntry("Using Canvas submission from: %s" % dt.ctime())
            if 'attempt' in cs:
                self.log_addEntry("This is attempt #%d (your first Canvas submission will be #1)" % cs['attempt'])
            if 'attachments' in cs and cs['attachments'][0] and 'filename' in cs['attachments'][0]:
                self.log_addEntry("You submitted a file named '%s'" % cs['attachments'][0]['filename'])
            if 'attachments' in cs and cs['attachments'][0] and 'display_name' in cs['attachments'][0]:
                self.log_addEntry("Canvas calls your submitted file '%s'" % cs['attachments'][0]['display_name'])
            if 'attachments' in cs and cs['attachments'] and 'late' in cs['attachments']:
                if cs['attachments']['late'] == True:
                    self.log_addEntry("LATE: This submission was turned in late.")

        if 'md5sum' in metadata:
            self.log_addEntry("Submitted file had md5sum " + metadata['md5sum'])

        # Put submitter's name or group name in report
        if 'canvasGroup' in metadata and \
           'name' in metadata['canvasGroup']:
            self.log_addEntry("Your group name: " + metadata['canvasGroup']['name'])
        else: # if not a group assignment
            if 'canvasStudent' in metadata and \
               'short_name' in metadata['canvasStudent']:
                self.log_addEntry("Your name: " + metadata['canvasStudent']['short_name'])


        import platform
        self.log_addEntry("Autograder is running on: %s" % platform.platform())

        self.log_addEntry("You initially have "+str(self.logPointsTotal)+" points; autograder will deduct points below; total at bottom.")

        self.log_addEntry("=== Begin autograding")

     # http://stackoverflow.com/questions/377017/
    def which(self,program):
        """Finds a program by consulting the PATH variable."""
        import os
        def is_exe(fpath):
            return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

        fpath, fname = os.path.split(program)
        if fpath:
            if is_exe(program):
                return program
        else:
            for path in os.environ["PATH"].split(os.pathsep):
                path = path.strip('"')
                exe_file = os.path.join(path, program)
                if is_exe(exe_file):
                    return exe_file

        return None


    def cleanup(self):
        """Remove the working directory and copy the autograde score to the original directory."""
        os.chdir(self.origwd)
        shutil.rmtree(self.workingDirectory)

        origScore = self.logPointsTotal
        if self.logPointsTotal < 0:
            self.logPointsTotal = 0

        # Appends the student's total score to the log file.
        self.log("<tr><td></td><td><b><span style='font-size: 140%%'>%s</span></b></td><td><b>TOTAL</b></td></tr>" % self.logPointsTotal)

        # Since we don't actually use negative scores in grading and since students don't like to see them, we make them less noticeable.
        if origScore < 0:
            self.log_addEntry("ADJUSTMENT: Your score was adjusted from %d to %d. We don't give negative scores." % (origScore, self.logPointsTotal))

        if self.logPointsTotal == 0:
            self.log_addEntry("ZERO: Although the autograder gave you a zero, if you have made some progress toward completing the assignment, you will likely get higher score from the human grader.")

        self.log_addEntry("Reports sent PRIOR to the deadline are for your information only. Autograder tests may change either before or after the deadline.")
        self.log_addEntry("Reports sent AFTER the deadline will be used by the grader/TA/instructor to assist with grading. Your actual grade may differ from what this report says.")
        self.log_addEntry("Want to talk to the grader? If you have any information that the instructor or TA should know about when grading your submission, please leave a comment on your submission in Canvas. Go to the assignment or submission page and look for a link named 'Submission details'. If you have an urgent question or find an autograder bug, email your instructor.")

        self.log("</table></body></html>")

        # move autograde file to its final destination (in the
        # original directory, not the working directory)
        logFileDest = os.path.join(self.directory, "AUTOGRADE.html")
        if os.path.exists(logFileDest):
            os.remove(logFileDest)
        shutil.move(self.logFile, logFileDest)
        if os.geteuid() == 0:
            os.chown(logFileDest, normalUid, normalGid)
        print("Score: %d" % self.logPointsTotal)
        print("Wrote: %s" % logFileDest)

        metadataFile = os.path.join(self.directory, "AUTOGRADE.json")
        metadata = {}
        if os.path.exists(metadataFile):
            with open(metadataFile, "r") as f:
                metadata = json.load(f)

        # Since we just generated a new AUTOGRADE.html file, we need to
        # make sure that we would email the new report the next time
        # students are emailed:
        metadata['emailSent'] = 0
        metadata['emailSubject'] = ""
        metadata['emailCtime'] = ""
        metadata['autograderScore'] = self.logPointsTotal
        metadata['autograderScorePreAdjustment'] = origScore

        # Dump the metadata back out to the file.
        with open(metadataFile, "w") as f:
            json.dump(metadata, f, indent=4)

        # Make metadata file be readable by the main user (not the temporary one we use to run submissions with).
        if switchUser and os.geteuid() == 0:
            os.chown(metadataFile, normalUid, normalGid)
            os.chown(logFileDest, normalUid, normalGid)

        shutil.rmtree(self.tempdir)
        self.tempdir = None
        self.workingDirectory = None


    def skip(self):
        """Same as cleanup() but discards any autograding that may have occured---leaves the submission directory unchanged."""
        os.chdir(self.origwd)
        shutil.rmtree(self.workingDirectory)
        shutil.rmtree(self.tempdir)
        if os.path.exists(self.logFile):
            os.remove(self.logFile)

    def isGraded(self):
        """Returns true if this submission needs to be autograded. A submission needs to be autograded if AUTOGRADE.json is missing, if AUTOGRADE.html is missing, or if the autograderScore is missing from AUTOGRADE.json"""
        metadataFile = os.path.join(self.directory, "AUTOGRADE.json")
        logFile = os.path.join(self.directory, "AUTOGRADE.html")

        if not os.path.exists(metadataFile) or not os.path.exists(logFile):
            return False

        metadata = {}
        with open(metadataFile, "r") as f:
            metadata = json.load(f)

        if 'autograderScore' not in metadata:
            return False

        return True


    def pristine(self, quiet=False):
        """Reset working directory to match the submission."""
        if os.path.exists(self.workingDirectory):
            if not quiet:
                self.log_addEntry("Restoring working directory to its original state (i.e., as the student submitted it.)")
            # Change into the original directory (and out of the working directory!)
            os.chdir(self.origwd)
            # Remove the existing working directory
            shutil.rmtree(self.workingDirectory)


        # Copy the original submission back into the working directory
        shutil.copytree(self.directory, self.workingDirectory)

        # Make sure both the autograder UID and root can access the
        # file. We'll make files owned by autograder and in the root
        # group. Both with read/write (+x for directories).
        if switchUser:
            os.chown(self.workingDirectory, autograderUid, 0)
            os.chmod(self.workingDirectory, 0o770)

            for path, dirs, files in os.walk(self.workingDirectory):
                os.chown(path, autograderUid, 0)
                os.chmod(path, 0o770)
                for f in files:
                    os.chown(os.path.join(path,f), autograderUid, 0)
                    os.chmod(os.path.join(path,f), stat.S_IREAD|stat.S_IWRITE|stat.S_IRGRP|stat.S_IWGRP)

        # Delete files we don't need in our working directory (and
        # files the students shouldn't see).
        self.delete(os.path.join(self.workingDirectory, "AUTOGRADE.html"), quiet=True)
        self.delete(os.path.join(self.workingDirectory, "AUTOGRADE.json"), quiet=True)

        # Change into the working directory again.
        os.chdir(self.workingDirectory)


    def chownDir(self, path, owner, group):
        if not os.path.exists(path):
            return
        for root, dirs, files in os.walk(path):
            for momo in dirs:
                os.chown(os.path.join(root, momo), owner, group)
            for momo in files:
                os.chown(os.path.join(root, momo), owner, group)
        os.chown(path, owner, group)


    def signal_to_string(self, signalNumber):
        if signalNumber < 0:
            signalNumber = signalNumber * -1

        if signalNumber == signal.SIGINT:
            return "SIGINT - Interrupt (Ctrl+C)"
        elif signalNumber == signal.SIGKILL:
            return "SIGKILL - Killed"
        elif signalNumber == signal.SIGTERM:
            return "SIGTERM - Terminated"
        elif signalNumber == signal.SIGSEGV:
            return "SIGSEGV - Segmentation fault"
        elif signalNumber == signal.SIGHUP:
            return "SIGHUP - Hang up"
        elif signalNumber == signal.SIGBUS:
            return "SIGBUS - Bus error"
        elif signalNumber == signal.SIGILL:
            return "SIGILL - Illegal instruction"
        elif signalNumber == signal.SIGFPE:
            return "SIGFPE - Floating point exception"
        elif signalNumber == signal.SIGPIPE:
            return "SIGPIPE - Broken pipe (write to pipe with no readers)"
        elif signalNumber == signal.SIGABRT:
            return "SIGABRT - Called abort()"
        elif signalNumber == signal.SIGXFSZ:
            return "SIGXFSZ - Process created files that were too big."
        elif signalNumber == signal.SIGXCPU:
            return "SIGXCPU - Process used too much CPU time."
        else:
            return "Unknown signal #" + str(signalNumber)


    def get_abbrv_string_from_file(self, filename):
        if not os.path.exists(filename):
            return "Can't read from " + filename + " because it doesn't exist."

        with open(filename, 'r', encoding="utf-8", errors='replace') as f:
            if os.path.getsize(filename) > 10000:
                retstring = f.read(4000)
                retstring += "\n\nSNIP SNIP SNIP (leaving out some of the output!)\n\n"
                # f.seek(-4000, os.SEEK_END)
                f.seek(os.path.getsize(filename)-4000)
                retstring += f.read(4000)
            else:
                retstring = f.read()

        return retstring


    # http://stackoverflow.com/questions/800197/
    def get_immediate_subdirectories(self):
        """Returns an alphabetical list of all the subdirectories in the current working directory (non-recursive)."""
        dir = os.getcwd()
        dirs = [name for name in os.listdir(dir) if os.path.isdir(os.path.join(dir, name))]
        dirs.sort()
        return dirs

    def get_immediate_files(self):
        """Returns an alphabetical list of all files in the current working directory (non-recursive)."""
        dir = os.getcwd()
        onlyfiles = [ f for f in os.listdir(dir) if os.path.isfile(os.path.join(dir,f)) ]
        onlyfiles.sort()
        return onlyfiles

    def get_immediate_executables(self):
        """Returns a list of strings of the files that are executable in the current directory. Returns "None" if there are no executable files."""
        dir = os.getcwd()
        onlyExec = [ f for f in os.listdir(dir) if (os.path.isfile(os.path.join(dir,f)) and os.access(os.path.join(dir,f), os.X_OK)) ]
        onlyExec.sort()
        return onlyExec

    def expect_file_all_of(self, filenames, deductPoints=0):
        """Returns true if all of the filenames in the list of files exists."""
        if isinstance(filenames, str):
            filenames = [ filenames ]
        returnVal = True

        self.log_addEntry("Expecting all of these files to exist: " + str(filenames))
        for f in filenames:
            if not glob.glob(f):
                self.log_addEntry("Missing a file that we expected: " + str(f), deductPoints)
                returnVal = False

        return returnVal

    def expect_file_one_of(self, filenames, deductPoints=0):
        """Return true if one of the files in the filenames list of files exists."""
        if isinstance(filenames, str):
            filenames = [ filenames ]

        self.log_addEntry("Expecting at least one of these files to exist: " + str(filenames))
        for f in filenames:
            if glob.glob(f):
                return True

        self.log_addEntry("Did not find one of the expected files.", deductPoints)
        return False

    def expect_file_none_of(self, filenames, deductPoints=0, delete=False):
        """Deduct points if one of the specified files is present"""
        self.log_addEntry("None of these files should be present: " + str(filenames))
        for f in filenames:
            for g in glob.glob(f):
                self.log_addEntry("This file should not exist (but it does!): " + str(g))
                if delete:
                    self.log_addEntry("Deleting file that should not have been present: " + str(g))
                    self.delete(g)
        return


    def expect_only_files(self, expected_files, deductPoints=0):
        """Identify files that the student submitted that are not in the expected_files list and deduct points for each one. Filenames can be regular expressions."""
        self.log_addEntry("Only the following files are allowed: " + str(expected_files))
        filesInDir = self.get_immediate_files()
        for f in expected_files:
            for g in glob.glob(f):
                filesInDir.remove(g)

        # If there are other files, deduct points for them.
        for f in filesInDir:
            filesize = self.humanSize(os.stat(f).st_size)
            self.log_addEntry("Unexpected file: %s (%s)" % (f, filesize), deductPoints)

    def incorrect_files(self, wrongFiles, deductPoints=0):
        """If any of the files in "files" exist, deduct points. Filenames can be regular expressions."""
        self.log_addEntry("These files should not be in the directory: " + str(wrongFiles))
        for f in wrongFiles:
            for g in glob.glob(f):
                self.log_addEntry("This file shouldn't exist: \"" + g + "\"", deductPoints)


    def find_unexpected_subdirectories(self, expected_dirs, deductPoints = 0):
        """Identify directories that the student submitted that are not in the expected_files list and deduct points for each one."""
        self.log_addEntry("Only these directories are allowed: " + str(expected_dirs))
        dirs = self.get_immediate_subdirectories()
        for f in expected_dirs:
            if f in dirs:
                dirs.remove(f)

        # If there are other files, deduct points for them.
        for f in dirs:
            self.log_addEntry("Unexpected directory: " + str(f), deductPoints)

    def log_pre(self, msg):
        """Prints a preformatted message to the autogarder log. Call log_addEntryRaw() if you wish to print a full line (line number, score, in table) with preformatting."""
        self.log("<div class='preformatcode'><pre>%s</pre></div>" % self.sanitize_string(msg))


    def log_lineNumber(self):
        """Prints a line number to the autogarder log."""
        self.log("<td>%d</td>" % self.lineNumber)
        self.lineNumber+=1


    def log(self, msg):
        """Prints a message to the autograder log."""
        # print(msg)
        with open(self.logFile, "a") as myfile:
            myfile.write(msg +'\n')

    def log_generic(self, msg, deductPoints=0, needSanitize=1, raw=0):
        if not msg:
            return

        with self.logLock:
            if needSanitize and raw==0:
                msg = self.sanitize_string(msg)

            if msg.startswith('==='):
                msg = msg.replace('===', '')
                msg = msg.strip()
                print(msg)
                self.log("<tr>")
                self.log_lineNumber()
                self.log("<td></td><td><h2>%s</h2></td></tr>" % msg)
                return

            # Make sure deductPoints is a negative number!
            if deductPoints > 0:
                deductPoints = -deductPoints

            scoreString = ""
            if deductPoints != 0:
                scoreString = "%s" % str(deductPoints)
                self.logPointsTotal = self.logPointsTotal + deductPoints
                # Print point deductions to console too.
                print("%d - %s" % (deductPoints, msg))

            self.log("<tr>")
            self.log_lineNumber()
            if raw:
                self.log("<td>%s</td><td>" % scoreString)
                self.log_pre(msg)
                self.log("</td></tr>")
            else:
                self.log("<td>%s</td><td>%s</td></tr>" % (scoreString, msg))


    def log_addEntry(self, msg, deductPoints=0):
        """Appends a entry into a log file. If pointsDeducted is set, points will be removed from the students grade and mentioned in the log file."""
        self.log_generic(msg, deductPoints=deductPoints, needSanitize=True)

    def log_addEntryRaw(self, msg, deductPoints=0):
        self.log_generic(msg, deductPoints=deductPoints, needSanitize=False, raw=1)



    def log_file_contents(self, filename):
        """Writes the contents of a file to the autograder log"""
        if not os.path.exists(filename):
            self.log_addEntry("File %s doesn't exist, can't display it." % filename)
            return

        msg = "File '%s' contains:" % filename
        msg += "<div class='preformatcode'><pre>%s</pre></div>" % self.sanitize_string(self.get_abbrv_string_from_file(filename))
        self.log_generic(msg, needSanitize=False)


    def find_first_matching_file(self, filenames):
        """Finds the first existing file that matches one of the filenames in the "filenames" list."""
        for f in filenames:
            if glob.glob(f):
                return f
        return None

    def delete(self, filename, quiet=False):
        """Deletes filename if it exists and prints an entry into the log about it."""
        if os.path.isfile(filename):
            filesize = "(" + self.humanSize(os.stat(filename).st_size) + ")"
            os.unlink(filename)
            if not quiet:
                self.log_addEntry("Deleted: " + filename + " " + filesize)

    def sanitize_string(self, instring, escape=True):
        """Show odd characters in hex. Performs HTML escaping"""
        if escape:
            if "escape" in dir(cgi):  # cgi.escape() is deprecated in python 3.8
                instring = cgi.escape(instring)
            else:
                instring = html.escape(instring)


        out=""
        for i in instring:
            if i == '‘':    #smart quote
                out += '‘'
            elif i == '’':  #smart quote
                out += '’'
            elif i == '\r':
                # Strip, should be followed with \n
                # Don't want to show two newline characters for lines with \r\n line endings.
                continue
            elif i == '\n':
                out += "&crarr;\n"
            #elif i == '\t':       # tab to right-arrow
            #    out += "&rarr;"   # messes up formatting too much.
            elif i in string.printable:
                # copy printable strings (digits, letters, punctuation, whitespace)
                out += i
            else:  # nonprintable ASCII.
                out += "\\{0x%02x}" % ord(i)  # print value in hex so it looks like: \{0x02}

        # We could strip whitespace, but we don't want to strip
        # whitespace from the strings that we are saying that we are
        # searching for.

        return out

    def run(self, exe, timeout=5, stdindata=None, deductTimeout=0, deductSegfault=0, quiet=False, workToDoWhileRunning=None):
        """Runs exe for up to timeout seconds. stdindata is sent to the process on stdin. deductTimeout points are deducted if the process does not finish before the timeout. deductSegfault points are deducted if the program segfaults."""
        cmd = Command(exe)
        (didRun, tooSlow, retcode, stdoutdata, stderrdata) = cmd.run(self, timeout=timeout, stdindata=stdindata, workToDoWhileRunning=workToDoWhileRunning)
        if quiet:
            return (didRun, tooSlow, retcode, stdoutdata, stderrdata)

        if not didRun:
            self.log_addEntry("%s: Command didn't run (missing exe?): %s" % (cmd.cmdShort, cmd.cmdSpaces))
            return (didRun, tooSlow, retcode, stdoutdata, stderrdata)

        # It should be mentioned earlier that the process had to be
        # killed with Ctrl+C. Only repeat the information if we are
        # deducting points because of it.
        if tooSlow and deductTimeout != 0:
            self.log_addEntry("%s: Command didn't finish within %d seconds (infinite loop?): %s" % (cmd.cmdShort, timeout, cmd.cmdSpaces), deductTimeout)

        # if retcode is negative, it contains the signal that
        # terminated the process. If positive, it is the process exit
        # value.
        #
        # Details about the signal causing the program to exit should
        # already be printed. Here, only print another line about it
        # if we are deducting points because of the segfault/exit due
        # to signal.
        if not tooSlow and retcode < 0 and deductSegfault != 0:
            self.log_addEntry("%s: Program exited due to a signal (segfault?)" % cmd.cmdShort, deductSegfault)

        if len(stdoutdata) == 0 and len(stderrdata) == 0:
            self.log_addEntry("%s: stdout and stderr were empty." % cmd.cmdShort)
        elif len(stdoutdata) > 0 and len(stderrdata) > 0:
            msg = "%s: stdout:" % cmd.cmdShort
            msg += "<div class='preformatcode'><pre>%s</pre></div>" % self.sanitize_string(stdoutdata)
            self.log_generic(msg, deductPoints=0, needSanitize=False)
            msg = "%s: stderr:" % cmd.cmdShort
            msg += "<div class='preformatcode'><pre>%s</pre></div>" % self.sanitize_string(stderrdata)
            self.log_generic(msg, deductPoints=0, needSanitize=False)

        elif len(stdoutdata) == 0 and len(stderrdata) > 0:
            msg = "%s: stdout was empty, stderr was:" % cmd.cmdShort
            msg += "<div class='preformatcode'><pre>%s</pre></div>" % self.sanitize_string(stderrdata)
            self.log_generic(msg, deductPoints=0, needSanitize=False)
        else:
            msg = "%s: stderr was empty, stdout was:" % cmd.cmdShort
            msg += "<div class='preformatcode'><pre>%s</pre></div>" % self.sanitize_string(stdoutdata)
            self.log_generic(msg, deductPoints=0, needSanitize=False)

        return (didRun, tooSlow, retcode, stdoutdata, stderrdata)



    def run_expectExitCode(self, exe, stdindata=None, timeout=5, expectExitCode = 0, deductTimeout=0, deductSegfault=0, deductWrongExit=0, workToDoWhileRunning=None, quiet=False):
        """Acts the same as run() but also deducts points if return code doesn't match expectRetExitCode."""
        (didRun, tooSlow, retcode, stdoutdata, stderrdata) = self.run(exe, stdindata=stdindata, deductTimeout=deductTimeout, deductSegfault=deductSegfault, timeout=timeout, quiet=quiet, workToDoWhileRunning=workToDoWhileRunning)
        # Don't deduct points for wrong exit code if we are already deducting points for segfault.
        if retcode < 0 and deductSegfault != 0 and deductWrongExit != 0:
            self.log_addEntry("%s: Won't deduct points for wrong exit code when we already deducted points for abnormal program exit." % exe[0])
            deductWrongExit = 0

        if retcode != expectExitCode:
            self.log_addEntry("%s: Expecting exit code %d but found %d" %
                              (exe[0], expectExitCode, retcode), deductWrongExit)
        else:
            self.log_addEntry("%s: Program exited as expected (with exit code %d)" %
                              (exe[0],expectExitCode))

        return (didRun, tooSlow, retcode, stdoutdata, stderrdata)

    def run_expectNotExitCode(self, exe, expectNotExitCode = 0, timeout=1, stdindata=None, deductTimeout=0, deductSegfault=0, deductWrongExit=0):
        """Acts the same as run() but also deducts points if return code matches expectNotExitCode. If you are running a program that should produce a non-zero exit code, set expectNotExitCode=0."""
        (didRun, tooSlow, retcode, stdoutdata, stderrdata) = self.run(exe, timeout, stdindata, deductTimeout, deductSegfault)
        if retcode < 0 and deductSegfault != 0 and deductWrongExit != 0:
            self.log_addEntry("%s: Won't deduct points for wrong exit code when we already deducted points for abnormal program exit." % exe[0])
            deductWrongExit = 0
        if retcode == expectNotExitCode:
            self.log_addEntry("%s: Expecting an exit code that is not %d but found %d" % (exe[0], expectNotExitCode, retcode), deductWrongExit)
        else:
            self.log_addEntry("%s: Program exited as we expected (with any exit code except %d)" % (exe[0], expectNotExitCode))
        return (didRun, tooSlow, retcode, stdoutdata, stderrdata)


    def expect_debugInfo(self, exe, deductNoDebug=0):
        cmd = subprocess.Popen("/usr/bin/readelf --debug-dump=info " + exe,
                               shell=True, stdout=subprocess.PIPE)
        (stdoutdata, stderrdata)  = cmd.communicate()
        if len(stdoutdata) < 10:
            self.log_addEntry("'" + exe + "' does not contain debugging information.", deductNoDebug)
        else:
	        self.log_addEntry("'" + exe + "' contains debugging information.", 0)

    def expect_md5(self, filename, expectMd5, deductMissingFile=0, deductWrongMd5=0):
        if not os.path.exists(filename):
            self.log_addEntry("md5sum: "+filename+" should have hash " + expectMd5 + " but it is MISSING.", deductMissingFile)
            return False

        # Read file in block by block so we don't have to read the
        # whole thing at once (this approach allows it to process
        # large files more easily)
        # http://joelverhagen.com/blog/2011/02/md5-hash-of-file-in-python/
        try:
            with open(filename, 'rb') as fh:
                m = hashlib.md5()
                while True:
                    data = fh.read(8192)
                    if not data:
                        break
                    m.update(data)
                filehash = m.hexdigest()

                filesize = "(size: " + self.humanSize(os.stat(filename).st_size) + ")"
                if filehash != expectMd5:
                    self.log_addEntry("md5sum: "+filename+" "+filesize+" should have hash " + expectMd5 + " but it has hash " + filehash, deductMissingFile)
                    return False
                else:
                    self.log_addEntry("md5sum: "+filename+" "+filesize+" has the correct hash " + expectMd5)
                    return True
        except PermissionError:
            self.log_addEntry("md5sum: "+filename+" could not be read. We should be able to read it and it should have md5sum "+expectMd5, deductMissingFile)
            return False

    def file_must_contain(self, filename, string, deductPoints=0):
        """The file "filename" should contain the string "string". If it doesn't, deduct points."""

        with open(filename, "r") as myfile:
            data = myfile.read()
            if string in data:
                msg = "File '%s' correctly contains:" % self.sanitize_string(filename)
                msg += "<div class='preformatcode'><pre>%s</pre></div>" % self.sanitize_string(string)
                self.log_generic(msg, deductPoints=0, needSanitize=False)
            else:
                msg = "File '%s' does not contain:" % self.sanitize_string(filename)
                msg += "<div class='preformatcode'><pre>%s</pre></div>" % self.sanitize_string(string)
                self.log_generic(msg, deductPoints=deductPoints, needSanitize=False)


    def stringMustContainRegex(self, haystack, needle, pts=0):
        if re.search(needle, haystack, re.IGNORECASE):
            self.log_addEntry("Output correctly contained: '" + needle + "' (regex)", 0)
            return True
        else:
            self.log_addEntry("Output did not contain '" + needle + "' (regex)", pts)
            return False

    def stringMustContain(self, haystack, needle, pts=0):
        """Search for a string within a string, deduct points if it isn't found."""
        with self.logLock:
            self.log("<tr>")
            self.log_lineNumber()

            found = False
            needlelow = needle.lower()
            haystacklow = haystack.lower()
            if needlelow not in haystacklow:
                if abs(pts) > 0:
                    self.log("<td>%d</td>" % -abs(pts))
                    self.logPointsTotal -= abs(pts)
                else:
                    self.log("<td></td>")

                self.log("<td>Did not find the following string (case insensitive):")
            else:
                self.log("<td></td>")
                self.log("<td>Correctly found the following string (case insensitive):")
                found = True

            self.log_pre(needle)
            self.log("</td></tr>")
            return found

    def stringMustNotContain(self, haystack, needle, pts):
        """Search for a string within a string, deduct points if it isn't found."""
        with self.logLock:
            self.log("<tr>")
            self.log_lineNumber()

            needlelow = needle.lower()
            haystacklow = haystack.lower()
            if needlelow not in haystacklow:
                self.log("<td></td>")
                self.log("<td>The string correctly lacked the following string (case insensitive):")
            else:
                if abs(pts) > 0:
                    self.log("<td>%d</td>" % -abs(pts))
                    self.logPointsTotal -= abs(pts)
                else:
                    self.log("<td></td>")
                self.log("<td>Found the following string that we should NOT find (case insensitive):")

            self.log_pre(needle)
            self.log("</td></tr>")

    def profanityCheck(self, filenameGlobs, deductPoints=1):
        """Checks for profanity in text files. Deducts points if found."""
        if isinstance(filenameGlobs, str):
            filenameGlobs = [ filenameGlobs ]

        profanityCount = 0
        for g in filenameGlobs:
            files = glob.glob(g)
            for f in files:
                if os.path.exists(f):
                    with open(f, "r") as fd:
                        fileContents = fd.read()
                        lines = fileContents.splitlines()
                        words = [ "fuck", " shit ", "bitch", "biatch", " cunt", "damn", " ass "]
                        for w in words:
                            for l in lines:
                                if re.search(w, l, re.IGNORECASE):
                                    self.log_addEntry("What the fuck is this shit? (It isn't professional to swear). File %s contains '%s'" % (f,l), -1)
                                    profanityCount += 1
        if profanityCount > 0:
            self.log_addEntry("This check can produce false positives. If we made a mistake, please let us know about the problem.")

        return profanityCount



    def humanSize(self, num):
        for x in ['bytes','KiB','MiB','GiB','TiB']:
            if num < 1024.0:
                return "%d %s" % (round(num), x)
            num /= 1024.0
