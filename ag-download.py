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
