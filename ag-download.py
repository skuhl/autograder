#!/usr/bin/env python3
import sys,shutil,os
import canvas

if sys.hexversion < 0x030000F0:
    print("This script requires Python 3")
    sys.exit(1)

# Set these to None to prompt to course and assignment names:
courseName=None
assignmentName=None

if not courseName:
    print("Name of course (according to Canvas)")
    courseName = sys.stdin.readline().strip()

if not assignmentName:
    print("Name of assignment (according to Canvas)")
    assignmentName = sys.stdin.readline().strip()


print("Name of subdirectory to put submissions into?")
subdirName = sys.stdin.readline().strip()

if not os.path.exists(subdirName):
    os.mkdir(subdirName)

print("Any existing submissions in the \""+subdirName+"\" directory will be overwritten. Press Ctrl+C to exit, any other key to continue.")
yn = sys.stdin.readline()

# Download the assignments from Canvas.
c = canvas.Canvas()
c.downloadAssignment(courseName=courseName, assignmentName=assignmentName, subdirName=subdirName)

# Look for ELF executables the user might have submitted and remove them!
for dirpath, dnames, fnames in os.walk(subdirName):
    for f in fnames:            # for each file in tree
        f = os.path.join(dirpath, f)
        if os.path.isfile(f):   # check that it is a file
            with open(f, "rb") as fileBytes:  # open the file
                magic = fileBytes.read(4)     # read 4 bytes
                # print("".join("%02x" % b for b in magic))
                # check that the 4 bytes match first 4 bytes of an ELF executable
                if magic[0] == 0x7f and magic[1] == 0x45 and magic[2]==0x4c and magic[3]==0x46:
                        print(f + " is ELF executable, removing")
                        os.unlink(f)
