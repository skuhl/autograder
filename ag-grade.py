#!/usr/bin/env python3
import autograder, canvas
import subprocess
import shutil, os, stat, sys, re

if sys.hexversion < 0x030000F0:
    print("This script requires Python 3")
    sys.exit(1)


def compile_warning_errors(ag):
    (didRun, tooSlow, retcode, stdoutdata, stderrdata) = ag.run(['make'])

    for line in stderrdata.split('\n'):
        if " warning: " in line:
            ag.log_addEntry("Compiler warning: " + line, -2)
        if " error: " in line:
            ag.log_addEntry("Compiler error: " + line, -10)

def cppcheck(ag):
    cmd = subprocess.Popen("/usr/bin/cppcheck --std=c99 --quiet *.c",
                           shell=True, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)
    (stdoutdata, stderrdata)  = cmd.communicate()
    stderrdata = stderrdata.decode('utf-8','replace')
    for line in stderrdata.split('\n'):
        if "(error)" in line:
            ag.log_addEntry("cppcheck error: " + line, -1)

def stringMustContainRegex(ag, haystack, needle, pts):
    if re.search(needle, haystack, re.IGNORECASE):
        ag.log_addEntry("Output correctly contained '" + needle + "' (regex)", 0);
    else:
        ag.log_addEntry("Output did not contain '" + needle + "' (regex)", pts);

def stringMustContain(ag, haystack, needle, pts):
    needlelow = needle.lower()
    haystacklow = haystack.lower()
    if needlelow in haystacklow:
        ag.log_addEntry("Output correctly contained '" + needle + "'", 0);
    else:
        ag.log_addEntry("Output did not contain '" + needle + "'", pts);

def stringMustNotContain(ag, haystack, needle, pts):
    needlelow = needle.lower()
    haystacklow = haystack.lower()
    if needlelow not in haystacklow:
        ag.log_addEntry("Output correctly lacked '" + needle + "'.", 0);
    else:
        ag.log_addEntry("Output incorrectly contained '" + needle + "'.", pts);

config = autograder.config()
settings = config.get()
subdirName = settings['subdirName']


# Get a list of subdirectories (each student submission will be in its own subdirectory)
dirs = [name for name in os.listdir(subdirName) if os.path.isdir(os.path.join(subdirName, name))]
dirs.sort()
os.chdir(subdirName)

if len(sys.argv) > 1:
    dirs = sys.argv[1:]


# For each subdirectory (i.e., student)
for thisDir in dirs:
    # Skip submissions that do not need regrading. All AUTOGRADE.txt files should be deleted whenever the autograder tests are changed to ensure that the new tests are applied to any already-autograded.
    if os.path.exists(os.path.join(thisDir, "AUTOGRADE.txt")):
        print("SKIPPING %s because it has already been autograded." % thisDir);
        continue

    # Set up the autograder
    ag = autograder.autograder("AUTOGRADE.txt", thisDir)

    # Verify that the files are there that we are expecting and look for unexpected files.
    ag.expect_only_files(["makefile", "Makefile", "*.c", "*.cpp", "*.h", "README", "README.txt"], 1)
    ag.find_unexpected_subdirectories([], 1)
    ag.expect_file_one_of(["*.c", "*.C", "*.cpp"], 1)
    ag.expect_file_one_of(["makefile", "Makefile"], 5)

    exe=[ 'mtusort' ] # a list of executables we are expecting
    # Delete any executables the student might have submitted---we will compile them ourselves.
    for f in exe:
        ag.delete(f)
    # run 'make' in the students directory
    ag.run_expectExitCode(["make"], expectExitCode=0, deductWrongExit=5, timeout=30)
    ag.expect_file_all_of(exe, 5) # check that exe got created

    # Figure out if all executables are there.
    execsExist = ag.get_immediate_executables()
    allExecs = True
    for f in exe:
        if f not in execsExist:
            allExecs = False

    # If one or more executables are missing.
    if allExecs == False:
        # If there is only one executable for this assignment, and
        # there are executables in execsExist, consider setting exec
        # to that one!
        ag.log_addEntry("Can't find expected executables. Giving up.", 50)
        ag.cleanup()
        continue

    # Check if the executables contain debugging information in them:
    for e in exe:
        ag.expect_debugInfo(e, 0)

    ag.log_addEntry("=== Check that Makefile contains appropriate things. ===")
    mf = ag.find_first_matching_file(["makefile", "Makefile"])
    if mf:
        ag.file_must_contain(mf, "-Wall", 5)
        ag.file_must_contain(mf, "-std=c99", 5)

    # Run "make clean" and verify that files are erased
    ag.log_addEntry("=== Check that 'make clean' works. ===")
    ag.run_expectExitCode(["make", "clean"], expectExitCode=0, deductWrongExit=5, timeout=30)
    ag.incorrect_files(["*.o", "*.s", "*.so", "*.a"]+exe, -1)

    ag.log_addEntry("=== Looking for compilation warnings and errors. ===")
    compile_warning_errors(ag)
    ag.log_addEntry("=== Looking for cppcheck warnings and errors. ===")
    cppcheck(ag)

    ag.log_addEntry("=== Try running with incorrect arguments. ====")
    ag.pristine() # Reset the directory back to exactly as the student submitted it.
    ag.run(['make'], quiet=True, timeout=30)
    ag.run_expectNotExitCode(['./mtusort' ], stdindata=None, expectNotExitCode=0, deductTimeout=5, deductSegfault=5, deductWrongExit=1, timeout=5)
    ag.run_expectNotExitCode(['./mtusort', 'foobar'], stdindata=None, expectNotExitCode=0, deductTimeout=5, deductSegfault=5, deductWrongExit=1, timeout=30)
    ag.run_expectNotExitCode(['./mtusort', '/does/not/exist.in', '/does/not/exist.out'], stdindata=None, expectNotExitCode=0, deductTimeout=5, deductSegfault=5, deductWrongExit=1, timeout=30)

    # Insert additional tests here!


    ag.cleanup()
