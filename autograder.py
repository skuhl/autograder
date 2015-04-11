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

class bcolors:
    FAIL = '\033[91m\033[1m'  # red, bold
    WARN = '\033[93m\033[1m'  # yellow, bold
    ENDC = '\033[0m'          # reset colors back to normal
    BOLD = '\033[1m'


class config():
    configfile = ""
    settings = {};

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
        self.process = None

        self.timeout = 1

        self.stdoutdata = ""
        self.stderrdata = ""
        self.retcode = 0
        self.didRun = False
        self.tooSlow = False

    def setProcessLimits(x):
        # This is called after fork and before exec:
        os.setpgrp()  # put all processes in the same process group so we can kill it and all children it creates.
        import resource
        nproc = int(os.environ["ULIMIT_NPROC"])
        data = int(os.environ["ULIMIT_DATA"])
        fsize = int(os.environ["ULIMIT_FSIZE"])
        resource.setrlimit(resource.RLIMIT_NPROC, (nproc,nproc));
        resource.setrlimit(resource.RLIMIT_AS, (data,data));
        resource.setrlimit(resource.RLIMIT_FSIZE, (fsize,fsize));


    def run(self, autogradeobj, timeout=5, stdindata=None, workToDoWhileRunning=None):
        def target():
            # To print current number of used processes, run: ps -eLF | grep $USER | wc -l
            os.environ["ULIMIT_NPROC"] = str(1024*4)            # Maximum number of processes
            os.environ["ULIMIT_DATA"]  = str(1024*1024*1024*8)  # 8 GB of memory
            os.environ["ULIMIT_FSIZE"] = str(1024*1024*1024*50) # 50 GB of space for files
            autogradeobj.log_addEntry('Process manager: Thread started: '+str(self.cmd))
            limitString  = "Process manager: Limits are "
            limitString += "time="  + str(timeout) + "sec "
            limitString += "memory=" + autogradeobj.humanSize(int(os.environ["ULIMIT_DATA"]))  + " "
            limitString += "fsize="  + autogradeobj.humanSize(int(os.environ["ULIMIT_FSIZE"])) + " "
            autogradeobj.log_addEntry(limitString)
            startTime = time.time()
            
            try:
            # write stderr/stdout to temp file in case students print tons of stuff out.
                stdoutFile = tempfile.mkstemp("ag-stdout-")
                stderrFile = tempfile.mkstemp("ag-stderr-")
                self.process = subprocess.Popen(self.cmd, stdin=subprocess.PIPE, stdout=stdoutFile[0], stderr=stderrFile[0], preexec_fn=self.setProcessLimits)
                if stdindata:
                    autogradeobj.log_addEntry("Process manager: Data sent to stdin: "+str(stdindata))
                    self.process.stdin.write(str(stdindata))
                self.process.stdin.close()
                self.process.wait()

                self.stdoutdata = autogradeobj.get_abbrv_string_from_file(stdoutFile[1])
                os.unlink(stdoutFile[1])
                self.stderrdata = autogradeobj.get_abbrv_string_from_file(stderrFile[1])
                os.unlink(stderrFile[1])

                self.retcode = self.process.returncode
                self.didRun = True
            except OSError as e:
                autogradeobj.log_addEntry("Process manager: Unable to start process: " + str(e))
                self.didRun = False
            elapsedTime = "%0.2fsec" % (time.time()-startTime)
            if self.retcode < 0:
                autogradeobj.log_addEntry('Process manager: Process exited after ' + elapsedTime + ' due to signal ' + str(-self.retcode) + " " + autogradeobj.signal_to_string(-self.retcode))
            else:
                autogradeobj.log_addEntry('Process manager: Process exited after ' + elapsedTime + ' with return code ' + str(self.retcode))


        try:
            thread = threading.Thread(target=target)
            thread.start()
            time.sleep(.5)
            if workToDoWhileRunning:
                workToDoWhileRunning()
            thread.join(timeout)

        # Without this, Ctrl+C will cause python to exit---but we will
        # be forced to wait until the process we are running times out
        # too. With this, we try to exit gracefully.
        except KeyboardInterrupt as e:
            os.killpg(self.process.pid, signal.SIGKILL)
            raise

        if thread.is_alive():
            autogradeobj.log_addEntry('Process manager: Ran for more than ' + str(timeout) + ' seconds. Terminating process...')
            self.tooSlow = True
            while thread.isAlive() and self.process != None:
                try:
                    os.killpg(self.process.pid, signal.SIGINT) # send Ctrl+C to process group
                    # self.process.send_signal(signal.SIGINT)    # send Ctrl+C to the parent process
                    time.sleep(.5)  # give process a chance to cleanup (for example valgrind printing its final summary)
                    os.killpg(self.process.pid, signal.SIGKILL) # kill the process group
                except:
                    # This should only happen if we try to kill something that doesn't exist anymore.
                    pass
                thread.join(.5)

        else:
            self.tooSlow = False

        return (self.didRun, self.tooSlow, self.retcode, self.stdoutdata, self.stderrdata)


class autograder():
    def __init__(self, logFile, username, totalPoints=100):
        self.logPointsTotal = totalPoints

        # Location of the AUTOGRADE.txt file. This file is neither in
        # the working directory nor in the actual submission
        # directory. It will be moved to the student submission
        # directory when the autograder is complete (i.e., cleanup()
        # is called).
        self.logFile = tempfile.mkstemp(prefix="ag-"+username+"-report-")[1]
        
        # Absolute path that we need to chdir back to when finished
        self.origwd = os.getcwd() 

        # Absolute path to the folder containing the student
        # submission.
        self.directory = os.path.join(self.origwd, username)

        # The name that the final log file should have. Typically:
        # /something/username/AUTOGRADE.txt
        self.logFileFinal = os.path.join(self.directory, logFile)

        # The autograder will do its work in a working directory
        self.workingDirectory = tempfile.mkdtemp(prefix="ag-"+username+"-working-")

        # Copy the student's submission into the working
        # directory. The only thing that needs to be copied back to
        # the original submission is the AUTOGRADE.txt file.
        shutil.rmtree(self.workingDirectory) # destination can't exist if we use copytree()
        shutil.copytree(self.directory, self.workingDirectory)

        # Change into working directory
        os.chdir(self.workingDirectory)
        
        # Print a header for this student to the console and log file.
        with open(self.logFile, "a") as myfile:
            msg = "=== " + username
            myfile.write(msg + "\n")
            print("#######################################")
            print("#######################################")
            print("#######################################")
            print(bcolors.BOLD + msg + bcolors.ENDC)
            myfile.close()

        self.log_addEntry("Autograder created this report at: %s" % str(datetime.datetime.now().ctime()))

            
        # Add some basic information to AUTOGRADE.txt so that students
        # can figure out exactly which submission the autograder
        # graded. This data is retrieved from the AUTOGRADE.json
        # metadata file.
        metadataFile = os.path.join(self.workingDirectory, "AUTOGRADE.json")
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
                self.log_addEntry("This is attempt %d (if this is the first submission you made for this assignment, this number will be 1)" % cs['attempt'])
            if 'attachments' in cs and cs['attachments'][0] and 'filename' in cs['attachments'][0]:
                self.log_addEntry("The file that you submitted was named: %s" % cs['attachments'][0]['filename'])
        if 'md5sum' in metadata:
            self.log_addEntry("The submitted file had md5sum: " + metadata['md5sum'])

        # Put submitter's name or group name in report
        if 'canvasGroup' in metadata and \
           'name' in metadata['canvasGroup']:
            self.log_addEntry("Your group name: " + metadata['canvasGroup']['name'])
        else: # if not a group assignment
            if 'canvasStudent' in metadata and \
               'short_name' in metadata['canvasStudent']:
                self.log_addEntry("Your name: " + metadata['canvasStudent']['short_name'])

        # Adjust grade based on the contents of AUTOGRADE-MANUAL.txt
        # that the teacher may have added to the directory. This file
        # will contain the number of points to deduct, a space, and
        # then a description of what to deduct.
        manAgFile = "AUTOGRADE-MANUAL.txt"
        if os.path.exists(manAgFile):
            with open(manAgFile, "r") as manFile:
                manFileContents = manFile.read()
                manualScore = int(manFileContents.split(' ')[0])
                manualLabel = ' '.join(manFileContents.split(' ')[1:])
                self.log_addEntry(manualLabel.strip(), manualScore)

    def cleanup(self):
        """Remove the working directory and copy the autograde score to the original directory."""
        os.chdir(self.origwd)
        shutil.rmtree(self.workingDirectory)
        # Appends the student's total score to the log file.
        msg = "TOTAL (instructor/TA/grader may adjust it!): " + str(self.logPointsTotal) + "\n"
        if self.logPointsTotal < 0:
            msg = msg + "Ouch! That score is less than 0! This can happen because the autograder starts by giving everybody 100 points and then deducts points for any problem it sees (this approach is not perfect). We won't give you a score less than 0. If there is a simple change that makes your program work correctly, the instructor/TA/grader might give you a much, much higher score.\n"
        with open(self.logFile, "a") as myfile:
            myfile.write(msg)
            myfile.close()
        print(bcolors.BOLD + msg + bcolors.ENDC);

        # move autograde file to its final destination (in the
        # original directory, not the working directory)
        if os.path.exists(self.logFileFinal):
            os.remove(self.logFileFinal)
        shutil.move(self.logFile, self.logFileFinal)
        print("Wrote: %s" % self.logFileFinal)

        metadataFile = os.path.join(self.directory, "AUTOGRADE.json")
        metadata = {}
        if os.path.exists(metadataFile):
            with open(metadataFile, "r") as f:
                metadata = json.load(f)

        # Since we just generated a new AUTOGRADE.txt file, we need to
        # make sure that we would email the new report the next time
        # students are emailed:
        metadata['emailSent'] = 0
        metadata['emailSubject'] = ""
        metadata['emailCtime'] = ""
        with open(metadataFile, "w") as f:
            json.dump(metadata, f, indent=4)


    def pristine(self):
        """Reset working directory to match the submission."""
        if os.path.exists(self.workingDirectory):
            self.log_addEntry("Restoring working directory to its original state (i.e., as the student submitted it.)")
            # Change into the original directory (and out of the working directory!)
            os.chdir(self.origwd)
            # Remove the existing working directory
            shutil.rmtree(self.workingDirectory)
            # Copy the  original submission back into the working directory
            shutil.copytree(self.directory, self.workingDirectory)
            # Change into the working directory again.
            os.chdir(self.workingDirectory)


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

        with open(filename, 'r', encoding="ascii", errors='replace') as f:
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
        return onlyExec;

    def expect_file_all_of(self, filenames, deductPoints=0):
        """Returns true if all of the filenames in the list of files exists."""
        if isinstance(filenames, str):
            filenames = [ filenames ]
        returnVal = True;
        for f in filenames:
            if self.expect_file_one_of([ f ], deductPoints) == False:
                returnVal = False;
        return returnVal;

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

    def expect_only_files(self, expected_files, deductPoints=0):
        """Identify files that the student submitted that are not in the expected_files list and deduct points for each one. Filenames can be regular expressions."""
        self.log_addEntry("Expecting no other files except for: " + str(expected_files))
        filesInDir = self.get_immediate_files()
        for f in expected_files:
            for g in glob.glob(f):
                filesInDir.remove(g)

        # If there are other files, deduct points for them.
        for f in filesInDir:
            filesize = "(" + self.humanSize(os.stat(f).st_size) + ")"
            self.log_addEntry("Unexpected file: \""+str(f)+"\" "+filesize, deductPoints)

    def incorrect_files(self, wrongFiles, deductPoints=0):
        """If any of the files in "files" exist, deduct points. Filenames can be regular expressions."""
        self.log_addEntry("There shouldn't be any of these files in the directory: " + str(wrongFiles))
        for f in wrongFiles:
            for g in glob.glob(f):
                self.log_addEntry("This file shouldn't exist: \"" + g + "\"", deductPoints)
        

    def find_unexpected_subdirectories(self, expected_dirs, deductPoints = 0):
        """Identify directories that the student submitted that are not in the expected_files list and deduct points for each one."""
        self.log_addEntry("Expecting no other directories besides: " + str(expected_dirs))
        dirs = self.get_immediate_subdirectories()
        for f in expected_dirs:
            if f in dirs:
                dirs.remove(f)

        # If there are other files, deduct points for them.
        for f in dirs:
            self.log_addEntry("Unexpected directory: " + str(f), deductPoints)
        

    def log_and_print(self, msg):
        """Prints a message to the console and to the log file."""
        print(msg)
        with open(self.logFile, "a") as myfile:
            myfile.write(msg +'\n')
            myfile.close()


    def log_addEntry(self, msg, pointsDeducted=0):
        """Appends a entry into a log file. If pointsDeducted is set, points will be removed from the students grade and mentioned in the log file."""
        # Make sure pointsDeducted is a negative number!
        if msg.startswith('==='):
            self.log_and_print("=================================================================")
            msg = msg.replace('===', '')
            self.log_and_print(msg)
            self.log_and_print("=================================================================")
            return
        msg = self.asciistring(msg)
        if pointsDeducted > 0:
            pointsDeducted = -pointsDeducted
        if pointsDeducted != 0:
            msg = "(" + ("%3d" % pointsDeducted) + ") " + msg
            self.log_and_print(msg)
            self.logPointsTotal = self.logPointsTotal + pointsDeducted
        else:
            self.log_and_print("(   ) " + msg)

    def find_first_matching_file(self, filenames):
        """Finds the first existing file that matches one of the filenames in the "filenames" list."""
        for f in filenames:
            if glob.glob(f):
                return f
        return None

    def delete(self, filename):
        """Deletes filename if it exists and prints an entry into the log about it."""
        if os.path.exists(filename):
            filesize = "(" + self.humanSize(os.stat(filename).st_size) + ")"
            os.unlink(filename)
            self.log_addEntry("Deleted: " + filename + " " + filesize)

    def asciistring(self, input):
        """Removes non-printable characters (including Unicode!) from the string."""
        newstr = ''.join(filter(lambda x: x in string.printable, input))
        # Just remove carriage returns. Windows uses \r\n for newlines
        return newstr.replace('\r', '');


    def run(self, exe, timeout=5, stdindata=None, deductTimeout=0, deductSegfault=0, quiet=False, workToDoWhileRunning=None):
        """Runs exe for up to timeout seconds. stdindata is sent to the process on stdin. deductTimeout points are deducted if the process does not finish before the timeout. deductSegfault points are deducted if the program segfaults."""
        cmd = Command(exe)
        (didRun, tooSlow, retcode, stdoutdata, stderrdata) = cmd.run(self, timeout=timeout, stdindata=stdindata, workToDoWhileRunning=workToDoWhileRunning)
        if quiet:
            return (didRun, tooSlow, retcode, stdoutdata, stderrdata)

        if not didRun:
            self.log_addEntry("Command " + str(exe) + " didn't run (missing exe?).")
            return (didRun, tooSlow, retcode, stdoutdata, stderrdata)

        if len(stdoutdata) == 0 and len(stderrdata) == 0:
            self.log_addEntry("Program output: stdout and stderr were empty.")
        else:
            if len(stdoutdata) == 0:
                self.log_addEntry("Program output: No stdout output.")
            else:
                self.log_addEntry("Program output: stdout:\n" + stdoutdata.rstrip())

            if len(stderrdata) == 0:
                self.log_addEntry("Program output: No stderr output.")
            else:
                self.log_addEntry("Program output: stderr:\n" + stderrdata.rstrip())

        if tooSlow:
            self.log_addEntry("Command " + str(exe) + " didn't finish within " + str(timeout) + " seconds. (infinite loop?).", deductTimeout)

        # if retcode is negative, it contains the signal that
        # terminated the process. If positive, it is the process exit
        # value.
        if not tooSlow and retcode < 0:
            self.log_addEntry("Exit status: Program exited due to a signal (segfault?)", deductSegfault);

        return (didRun, tooSlow, retcode, stdoutdata, stderrdata)



    def run_expectExitCode(self, exe, stdindata=None, timeout=5, expectExitCode = 0, deductTimeout=0, deductSegfault=0, deductWrongExit=0, workToDoWhileRunning=None):
        """Acts the same as run() but also deducts points if return code doesn't match expectRetExitCode."""
        (didRun, tooSlow, retcode, stdoutdata, stderrdata) = self.run(exe, stdindata=stdindata, deductTimeout=deductTimeout, deductSegfault=deductSegfault, timeout=timeout, workToDoWhileRunning=workToDoWhileRunning)
        # Don't deduct points for wrong exit code if we are already deducting points for segfault.
        if retcode < 0 and deductSegfault != 0:
            self.log_addEntry("Exit status: Won't deduct points for wrong exit code when we already deducted points for abnormal program exit.")
            deductWrongExit = 0;
        if retcode != expectExitCode:
            self.log_addEntry("Exit status: Expecting exit code " + str(expectExitCode) + " but found " + str(retcode), deductWrongExit)
        else:
            self.log_addEntry("Exit status: Program exited as expected (with exit code " + str(expectExitCode) + ")")
        return (didRun, tooSlow, retcode, stdoutdata, stderrdata)

    def run_expectNotExitCode(self, exe, expectNotExitCode = 0, timeout=1, stdindata=None, deductTimeout=0, deductSegfault=0, deductWrongExit=0):
        """Acts the same as run() but also deducts points if return code matches expectNotExitCode. If you are running a program that should produce a non-zero exit code, set expectNotExitCode=0."""
        (didRun, tooSlow, retcode, stdoutdata, stderrdata) = self.run(exe, timeout, stdindata, deductTimeout, deductSegfault)
        if retcode < 0 and deductSegfault != 0:
            self.log_addEntry("Exit status: Won't deduct points for wrong exit code when we already deducted points for abnormal program exit.")
            deductWrongExit = 0;
        if retcode == expectNotExitCode:
            self.log_addEntry("Exit status: Expecting an exit code that is not " + str(expectNotExitCode) + " but found " + str(retcode), deductWrongExit)
        else:
            self.log_addEntry("Exit status: Program exited as we expected (with any exit code except " + str(expectNotExitCode) + ")")
        return (didRun, tooSlow, retcode, stdoutdata, stderrdata)


    def expect_debugInfo(self, exe, deductNoDebug=0):
        cmd = subprocess.Popen("/usr/bin/readelf --debug-dump=info " + exe,
                               shell=True, stdout=subprocess.PIPE)
        (stdoutdata, stderrdata)  = cmd.communicate()
        if len(stdoutdata) < 10:
            self.log_addEntry(exe + " does not contain debugging information.", deductNoDebug)
        else:
	        self.log_addEntry(exe + " contains debugging information.", 0)

    def expect_md5(self, filename, expectMd5, deductMissingFile=0, deductWrongMd5=0):
        if not os.path.exists(filename):
            self.log_addEntry("md5sum: "+filename+" should have hash " + expectMd5 + " but it is MISSING.", deductMissingFile)
            return False

        # Read file in block by block so we don't have to read the
        # whole thing at once (this approach allows it to process
        # large files more easily)
        # http://joelverhagen.com/blog/2011/02/md5-hash-of-file-in-python/
        with open(filename, 'rb') as fh:
            m = hashlib.md5()
            while True:
                data = fh.read(8192)
                if not data:
                    break
                m.update(data)
            filehash = m.hexdigest()

            filesize = "(your filesize: " + self.humanSize(os.stat(filename).st_size) + ")"
            if filehash != expectMd5:
                self.log_addEntry("md5sum: "+filename+" should have hash " + expectMd5 + " but it has hash " + filehash + " " + filesize, deductMissingFile)
                return False
            else:
                self.log_addEntry("md5sum: "+filename+" has the correct hash " + expectMd5 + " " + filesize)
                return True


    def file_must_contain(self, filename, string, deductPoints=0):
        """The file "filename" should contain the string "string". If it doesn't, deduct points."""
        self.log_addEntry("Checking that '" + str(string) + "' is somewhere in '" + filename + "'.")
        with open(filename, "r") as myfile:
            data = myfile.read()
            if string not in data:
                self.log_addEntry("The string " + str(string) + " is not in " + str(filename), deductPoints)

    def humanSize(self, num):
        for x in ['bytes','KiB','MiB','GiB','TiB']:
            if num < 1024.0:
                return "%d%s" % (round(num), x)
            num /= 1024.0


