import hashlib
import os
import subprocess, threading
import shutil
import glob
import stat
import string
import signal
import time

class bcolors:
    FAIL = '\033[91m\033[1m'  # red, bold
    WARN = '\033[93m\033[1m'  # yellow, bold
    ENDC = '\033[0m'          # reset colors back to normal
    BOLD = '\033[1m'


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
        resource.setrlimit(resource.RLIMIT_NPROC, (nproc,nproc)); # number of processes
        resource.setrlimit(resource.RLIMIT_AS, (data,data));
        resource.setrlimit(resource.RLIMIT_FSIZE, (fsize,fsize));


    def run(self, autogradeobj, timeout=5, stdindata=None):
        def target():
            os.environ["ULIMIT_NPROC"] = str(512)              # Maximum number of processes
            os.environ["ULIMIT_DATA"]  = str(1024*1024*1024*8)  # 8 GB of space memory
            os.environ["ULIMIT_FSIZE"] = str(1024*1024*1024*50) # 50 GB of space for files
            autogradeobj.log_addEntry('Process manager: Thread started: '+str(self.cmd))
            limitString  = "Process manager: Limits are "
            limitString += "time="  + str(timeout) + "sec "
            limitString += "nproc="  + os.environ["ULIMIT_NPROC"] + " "
            limitString += "memory=" + autogradeobj.humanSize(int(os.environ["ULIMIT_DATA"]))  + " "
            limitString += "fsize="  + autogradeobj.humanSize(int(os.environ["ULIMIT_FSIZE"])) + " "
            autogradeobj.log_addEntry(limitString)
            startTime = time.time()
            try:
            # write stderr/stdout to temp file in case students print tons of stuff out.
                with open("AUTOGRADE-STDOUT-TEMP-FILE.txt", 'w') as fo:
                    with open("AUTOGRADE-STDERR-TEMP-FILE.txt", 'w') as fe:
                        self.process = subprocess.Popen(self.cmd, stdin=subprocess.PIPE, stdout=fo, stderr=fe, preexec_fn=self.setProcessLimits)
                if stdindata:
                    autogradeobj.log_addEntry("Process manager: Data sent to stdin: "+str(stdindata))
                    self.process.stdin.write(str(stdindata))
                self.process.stdin.close()
                self.process.wait()

                self.stdoutdata = autogradeobj.get_abbrv_string_from_file("AUTOGRADE-STDOUT-TEMP-FILE.txt")
                os.unlink("AUTOGRADE-STDOUT-TEMP-FILE.txt")
                self.stderrdata = autogradeobj.get_abbrv_string_from_file("AUTOGRADE-STDERR-TEMP-FILE.txt")
                os.unlink("AUTOGRADE-STDERR-TEMP-FILE.txt")

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

        thread = threading.Thread(target=target)
        thread.start()

        try:
            thread.join(timeout)
        # Without this, Ctrl+C will cause python to exit---but we will
        # be forced to wait until the process we are running times out
        # too. With this, we try to exit gracefully.
        except KeyboardInterrupt as e:
            os.killpg(self.process.pid, signal.SIGKILL)
            raise

        if thread.is_alive():
            autogradeobj.log_addEntry('Process manager: Ran for more than ' + str(timeout) + ' seconds. Terminating process')
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
    def __init__(self, logFile, directory, totalPoints=100):
        self.origwd = os.getcwd()
        self.logPointsTotal = 100
        self.logFile = self.origwd + "/" + logFile
        self.directory = directory
        self.pristineDirectory = "/tmp/autograde-" + directory

        # delete autograde file in the directory
        toDelete = [ self.logFile,
                     self.directory + "/" + logFile, 
                     self.directory + "/" + "AUTOGRADE-STDOUT-TEMP-FILE.txt",
                     self.directory + "/" + "AUTOGRADE-STDERR-TEMP-FILE.txt" ]
        for f in toDelete:
            if os.path.exists(f):
                os.unlink(f)

        # Make a pristine copy of the code
        if os.path.exists(self.pristineDirectory):
            shutil.rmtree(self.pristineDirectory)
        shutil.copytree(self.directory, self.pristineDirectory)

        # Appends a new entry into the log file indicating that we went into a subdirectory.
        os.chdir(directory)
        with open(self.logFile, "a") as myfile:
            msg = "=== " + directory + "\n"
            myfile.write("\n\n\n"+msg)
            print(bcolors.BOLD + msg + bcolors.ENDC)
            myfile.close()

    def cleanup(self):
        self.pristine()
        shutil.rmtree(self.pristineDirectory)
        os.chdir(self.origwd)
        # Appends the student's total score to the log file.
        msg = "TOTAL (instructor/TA/grader may adjust it!): " + str(self.logPointsTotal) + "\n"
        with open(self.logFile, "a") as myfile:
            myfile.write(msg)
            myfile.close()
        print(bcolors.BOLD + msg + bcolors.ENDC);
        # move autograde file to its final destination
        shutil.move(self.logFile, self.directory)

    def pristine(self):
        """Restores the directory that we are grading back to it's original pristine state (without deleting the pristine copy---so we can use it again if needed!)"""
        if os.path.exists(self.pristineDirectory):
            self.log_addEntry("Restoring directory to is original state (i.e., as the student submitted it.)")
            os.chdir(self.origwd)
            shutil.rmtree(self.directory)
            shutil.copytree(self.pristineDirectory, self.directory)
            os.chdir(self.directory)
        else:
            print("Can't restore pristine directory because it doesn't exist.")
            exit(1)

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

        with open(filename, 'r') as f:
            if os.path.getsize(filename) > 10000:
                retstring = f.read(4000)
                retstring += "\n\nSNIP SNIP SNIP\n\n"
                f.seek(-4000, os.SEEK_END)
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
            self.log_addEntry("Unexpected file: "+str(f)+" "+filesize, deductPoints)

    def incorrect_files(self, wrongFiles, deductPoints=0):
        """If any of the files in "files" exist, deduct points. Filenames can be regular expressions."""
        self.log_addEntry("There shouldn't be any of these files in the directory: " + str(wrongFiles))
        for f in wrongFiles:
            for g in glob.glob(f):
                self.log_addEntry("This file shouldn't exist now: " + g, deductPoints)
        

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


    def run(self, exe, timeout=5, stdindata=None, deductTimeout=0, deductSegfault=0, quiet=False):
        """Runs exe for up to timeout seconds. stdindata is sent to the process on stdin. deductTimeout points are deducted if the process does not finish before the timeout. deductSegfault points are deducted if the program segfaults."""
        cmd = Command(exe)
        (didRun, tooSlow, retcode, stdoutdata, stderrdata) = cmd.run(self, timeout=timeout, stdindata=stdindata)
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



    def run_expectExitCode(self, exe, stdindata=None, timeout=5, expectExitCode = 0, deductTimeout=0, deductSegfault=0, deductWrongExit=0):
        """Acts the same as run() but also deducts points if return code doesn't match expectRetExitCode."""
        (didRun, tooSlow, retcode, stdoutdata, stderrdata) = self.run(exe, stdindata=stdindata, deductTimeout=deductTimeout, deductSegfault=deductSegfault, timeout=timeout)
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


    def file_must_contain(self, filename, string, deductPoints):
        """The file "filename" should contain the string "string". If it doesn't, deduct points."""
        self.log_addEntry("Checking that '" + str(string) + "' is somewhere in '" + filename + "'.")
        with open(filename, "r") as myfile:
            data = myfile.read()
            if string not in data:
                self.log_addEntry("The string " + str(string) + " is not in " + str(filename), -5)

    def humanSize(self, num):
        for x in ['bytes','KiB','MiB','GiB','TiB']:
            if num < 1024.0:
                return "%d%s" % (round(num), x)
            num /= 1024.0


