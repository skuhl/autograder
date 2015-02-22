#!/usr/bin/env python3
import sys,shutil,os
import canvas

if sys.hexversion < 0x030000F0:
    print("This script requires Python 3")
    sys.exit(1)

# Set these to None to prompt to course and assignment names:
courseName=None
assignmentName=None
subdirName=None

CONFIG_FILE="ag-download.config"

# See if there is a file that contains the information we need so we
# don't need to prompt the user.
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE) as f:
        exec(f.read())

# Prompt the user or show the user what settings we are using.
if not courseName:
    print("Name of course (according to Canvas)")
    courseName = sys.stdin.readline().strip()
else:
    print("Using course: " + courseName + " (found in " + CONFIG_FILE + ")")

if not assignmentName:
    print("Name of assignment (according to Canvas)")
    assignmentName = sys.stdin.readline().strip()
else:
    print("Using assignment: " + assignmentName + " (found in " + CONFIG_FILE + ")")

if not subdirName:
    print("Name of subdirectory to put submissions into?")
    subdirName = sys.stdin.readline().strip()
else:
    print("Using directory: " + subdirName + " (found in " + CONFIG_FILE + ")")

# Write the settings we are using out to a file so the user doesn't
# have to type them in again next time.
with open(CONFIG_FILE, 'w') as f:
    f.write("courseName=\""+courseName+"\"\n")
    f.write("assignmentName=\""+assignmentName+"\"\n")
    f.write("subdirName=\""+subdirName+"\"\n")


if os.path.exists(subdirName):
    print("\n")
    print("Submissions in \""+subdirName+"\" will be overwritten.")
    print("Press Ctrl+C to exit, any other key to continue.")
    yn = sys.stdin.readline()
    shutil.rmtree(subdirName)

os.mkdir(subdirName);

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
                if len(magic) >= 4 and magic[0] == 0x7f and magic[1] == 0x45 and magic[2]==0x4c and magic[3]==0x46:
                        print(f + " is ELF executable, removing")
                        os.unlink(f)
