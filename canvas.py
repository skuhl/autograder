#!/usr/bin/env python3
# Author: Scott Kuhl
import json, urllib.request
import textwrap
import sys,shutil,os
from pprint import pprint
import argparse


# To use this Python class, you should create a file named
# .canvas-token in your home directory. It should contain the lines:
#
# self.CANVAS_API="https://canvas.instructure.com/api/v1/"
# self.CANVAS_TOKEN="token-generated-in-canvas"
#
# The first line should be the URL for the Canvas API. For Michigan
# Tech, for example, this URL should be
# "https://mtu.instructure.com/api/v1". The second line should contain
# a token that you must generate in Canvas and will be a string of
# characters and numbers. To generate one, login to Canvas, go to
# "Settings" and click on the "New Access Token" button.


# The canvas object will remember the courseId you use in the
# constructor and use that if you don't provide a courseId to the
# other functions that you call. Or, you can manually override the
# courseId in your calls to specific functions.


class Canvas():
    CANVAS_API = ""
    CANVAS_TOKEN = None
    courseId = 0;

    def __init__(self, token=None, courseId=None):
        canvasTokenFile = os.path.expanduser("~/.canvas-token")
        if token:
            self.CANVAS_TOKEN = str(token)
        else:
            with open(canvasTokenFile) as f:
                exec(f.read())

        if not self.CANVAS_TOKEN:
            print("Canvas token not found.")
            exit()
        if not self.CANVAS_API:
            print("URL for Canvas API not found.")
            exit()
        self.courseId = courseId

    def makeRequest(self,request):
        """Makes the given request (passes token as header)"""
        try:
            requestString = self.CANVAS_API+request
            print("Sending request: " +requestString)
            request = urllib.request.Request(requestString)
            request.add_header("Authorization", "Bearer " + self.CANVAS_TOKEN);
            json_string = urllib.request.urlopen(request).readall().decode('utf-8');
            return json.loads(json_string)
        except:
            e = sys.exc_info()[0]
            print(e)
            raise

    def prettyPrint(self,data):
        print(json.dumps(data, sort_keys=True, indent=4))

    def getCourses(self):
        """Gets course objects"""
        return self.makeRequest("courses")

    def getStudents(self, courseId=None):
        """Gets list of students in a course."""
        courseId = courseId or self.courseId
        if courseId == None:
            print("Can't getStudents without a courseId.")
            exit()
        return self.makeRequest("courses/"+str(courseId)+"/students")

    def getAssignments(self, courseId=None):
        """Gets list of assignments in a course."""
        courseId = courseId or self.courseId
        if courseId == None:
            print("Can't getAssignments without a courseId.")
            exit()
        return self.makeRequest("courses/"+str(courseId)+"/assignments")

    def getSubmissions(self, courseId=None, assignmentId=None, studentId=None):
        """Gets all submissions for a course, all submissions for a student in a course, or all submissions for a specific assignment+student combination."""
        courseId = courseId or self.courseId
        if courseId == None:
            print("Can't get submissions without a courseId.")
            exit()
        commonargs="grouped=true&include[]=submission_history"
        if studentId == None:
            commonargs+="&student_ids[]=all"
        else:
            commonargs+="&student_ids[]="+str(studentId)

        if assignmentId == None:
            return self.makeRequest("courses/"+str(courseId)+"/students/submissions?"+commonargs)
        else:
            return self.makeRequest("courses/"+str(courseId)+"/students/submissions?assignment_ids[]="+str(assignmentId)+"&"+commonargs)

    
    def findStudent(self, students, searchString):
        """Returns a student object that matches the students name, username, or ID. The searchString must match one of the fields in the student object exactly!"""
        searchString = str(searchString).lower()
        for s in students:
            if s['name'].lower()          == searchString or \
               s['short_name'].lower()    == searchString or \
               s['sortable_name'].lower() == searchString or \
               s['login_id'].lower()      == searchString or \
               str(s['id']) == searchString:
                return s
        return None

    def findAssignment(self, assignments, searchString):
        """Returns an assignment object that matches the assignment name out of a list of assignment objects."""
        searchString = searchString.lower()
        for a in assignments:
            if a['name'].lower() == searchString or \
               str(a['id']) == searchString:
                return a
        return None

    def findCourse(self, courses, searchString):
        """Returns an course object that matches the course name out of a list of course objects."""
        searchString = searchString.lower()
        for c in courses:
            if c['name'].lower() == searchString or \
               str(c['id'])      == searchString:
                return c
        return None

    def findStudentId(self, students, searchString):
        """Returns the ID of the student by looking for a match in the list of students."""
        if type(searchString) == int: # assume that this is a correct id they are looking for
            return searchString
        student = self.findStudent(students, searchString)
        if student:
            return int(student['id'])
        return None

    def findAssignmentId(self, assignments, searchString):
        """Returns the ID of the assignment by looking for a match in the list of assignments."""
        if type(searchString) == int: # assume that this is a correct id they are looking for
            return searchString
        assignment = self.findAssignment(assignments, searchString)
        if assignment:
            return int(assignment['id'])
        return None

    def findCourseId(self, courses, searchString):
        """Returns the ID of the course by looking through a list of courses."""
        if type(searchString) == int: # assume that this is a correct id they are looking for
            return searchString
        course = self.findCourse(courses, searchString)
        if course:
            return int(course['id'])
        return None

    def findSubmissionsToGrade(self, submissions):
        """Returns the newest non-late submission."""
        goodSubmissions = []

        # submissions must be grouped by student and include submission history
        for studentSubmit in submissions:
            newestOnTimeAttempt = 0
            newestOnTimeSubmission = None
            if len(studentSubmit['submissions']) > 0:
                allHistory = studentSubmit['submissions'][0]['submission_history']
            else:
                allHistory = []
            

            for hist in allHistory:
                # hist['attempt'] is actually set to null if we have already
                # graded something that hasn't been submitted.
                if not hist['late'] and hist['attempt'] and hist['attempt'] > newestOnTimeAttempt:
                    newestOnTimeAttempt = hist['attempt']
                    newestOnTimeSubmission = hist

            # If no on-time submission, just accept the late
            # submission
#            if not newestOnTimeSubmission:
#                for hist in allHistory:
#                    if hist['attempt'] and hist['attempt'] > newestOnTimeAttempt:
#                        newestOnTimeAttempt = hist['attempt']
#                        newestOnTimeSubmission = hist

            # If there was no submission, a submission object for the
            # student will be returned that has 'attempt: null'.
            if not newestOnTimeSubmission and len(allHistory) > 0:
                newestOnTimeSubmission = allHistory[0]
            goodSubmissions.append(newestOnTimeSubmission)
        return goodSubmissions

    def printSubmissionSummary(self, submissions, students):
        """Prints a summary of all of the submissions."""
        fmtStr = "%4s %5s %4s %12s %s"
        print(fmtStr%("pts", "late", "atmpt", "login", "name"))
        for student in students:
            studentSubmissionHist = []
            for submission in submissions:
                if submission['user_id'] == student['id']:
                    if 'submissions' in submission:
                        if len(submission['submissions']) > 0:
                            # Assuming submissions is what canvas.getSubmissions() returns
                            studentSubmissionHist = submission['submissions'][0]['submission_history']
                    else: # Assuming submissions is what canvas.findSubmissionsToGrade() returns
                        studentSubmissionHist = [ submission ]

            if len(studentSubmissionHist) == 0:
                print(fmtStr%("", " none", 0, str(student['login_id']), student['name']))
            for hist in studentSubmissionHist:
                late = ""
                graded = ""
                if hist['late']:
                    late = " late"
                if hist['grade']:
                    graded = str(hist['grade'])
                print(fmtStr%(graded, late, str(hist['attempt']), str(student['login_id']), student['name']))

    def downloadSubmissions(self, submissions, students, dir="None"):
        """Assumes that students submit one file (tgz.gz, zip, whatever is allowed) and downloads it into the given subdirectory."""
        if not dir:
            dir = "."
        if not os.path.exists(dir):
            os.makedirs(dir)
        # require one attachment
        for i in submissions:
            if i != None and \
               'attachments' in i and \
               len(i['attachments']) == 1 and \
               i['attachments'][0]['url'] and \
               i['attachments'][0]['filename']:
                student = self.findStudent(students, i['user_id'])
                attachment = i['attachments'][0]
                filename = attachment['filename']
                exten = os.path.splitext(filename)[1] # get filename extension
                message = student['name'] + " ("+student['login_id']+")"

                archiveFile  = dir+"/"+student['login_id']+exten
                subdirName   = dir+"/"+student['login_id']
                # Always delete existing stuff.
                if os.path.exists(archiveFile):
                    os.unlink(archiveFile)
                if os.path.exists(subdirName):
                    shutil.rmtree(subdirName)

                print("Downloading file for " + message)
                urllib.request.urlretrieve(attachment['url'], dir+"/"+student['login_id']+exten)


    def get_immediate_files(self, dir):
        """Returns an alphabetical list of all files in the current directory (non-recursive)."""
        onlyfiles = [ f for f in os.listdir(dir) if os.path.isfile(os.path.join(dir,f)) ]
        onlyfiles.sort()
        return onlyfiles

    def extractAllFiles(self, dir=".", newSubdir=False):
        print("Extracting all files into: " + dir)
        files = self.get_immediate_files(dir)
        for f in files:
            self.extractFile(dir+"/"+f, dir, newSubdir)

    def extractFile(self, filename, dir, newSubdir=False):
        """Extracts filename into dir. If newSubdir is set, create an additional subdirectory inside of dir to extract the files into."""
        import tarfile
        destDir = dir
        if newSubdir:
            # If using newSubdir, make a directory with the same
            # name as the file but without the extension.
            destDir = os.path.splitext(filename)[0]
        print("Extracting " + filename + " into " + destDir);

        if tarfile.is_tarfile(filename):
            tar = tarfile.open(filename)
            tar.extractall(path=destDir)
            tar.close()
            os.remove(filename)
        import zipfile
        if zipfile.is_zipfile(filename):
            zip = zipfile.open(filename)
            zip.extractall(path=destDir)
            zip.close()
            os.remove(filename)
        # Look at extracted files:
        onlyfiles = [ f for f in os.listdir(destDir) if os.path.isfile(os.path.join(destDir,f)) ]
        onlydirs = [ f for f in os.listdir(destDir) if os.path.isdir(os.path.join(destDir,f)) ]
        print("Submissions contained %d files and %d dirs"%(len(onlyfiles), len(onlydirs)))
        # If submission included all files in a subdirectory, remove the subdirectory
        if len(onlyfiles) == 0 and len(onlydirs) == 1:
            print("Getting rid of subdirectory...")
            shutil.rmtree("/tmp/autograder-tmp-dir", ignore_errors=True)
            tmpDir = "/tmp/autograder-tmp-dir/"+onlydirs[0]
            shutil.move(destDir+"/"+onlydirs[0], tmpDir)
            for f in os.listdir(tmpDir):
                shutil.move(tmpDir+"/"+f, destDir)
            shutil.rmtree(tmpDir)
            

    def printCourseIds(self, courses):
        for i in courses:
            print("%10s %s"%(str(i['id']), i['name']))

    def printAssignmentIds(self, assignments):
        for i in assignments:
            print("%10s %s"%(str(i['id']), i['name']))
  
    def printStudentIds(self, students):
        for i in students:
            print("%10s %10s %s"%(str(i['id']), i['login_id'], i['name']))

    def setDefaultCourseId(self, courseId):
        if courseId == None:
            print("Warning: You are setting the default courseId to None.")
        self.courseId = courseId;

    def downloadAssignment(self, courseName, assignmentName, subdirName):
        courses = self.getCourses()
        courseId = self.findCourseId(courses, courseName)
        assignments = self.getAssignments(courseId=courseId)
        students    = self.getStudents(courseId=courseId)
        # Print that information
        #self.printCourseIds(courses)
        #self.printAssignmentIds(assignments)
        #self.printStudentIds(students)
        assignmentId = self.findAssignmentId(assignments, assignmentName)
        submissions = self.getSubmissions(courseId=courseId, assignmentId=assignmentId)
        submissionsToGrade = self.findSubmissionsToGrade(submissions)
        print(submissionsToGrade)
        self.downloadSubmissions(submissionsToGrade, students, dir=subdirName)
        if subdirName:
            self.extractAllFiles(dir=subdirName,newSubdir=True)
        else:
            self.extractAllFiles()



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Download assignments from Canvas')
    parser.add_argument('action', type=str, metavar="ACTION", nargs=1, help="assignmentStatus, assignmentDownload, studentList, assignmentList, courseList")
    parser.add_argument('-c', '--course', required=False, help="Name of course on Canvas.")
    parser.add_argument('-a', '--assignment', required=False, help="Name of assignment on Canvas.")
    args = parser.parse_args()


    canvas = Canvas()
    courses = canvas.getCourses()

    for action in args.action:

        if action == "download" and not args.assignment:
            print("Assignment name required when downloading an assignment.")
            parser.print_help()
            exit(1)

        if action != "courseList" and not args.course:
            print("Course name required (unless using courseList action)")
            parser.print_help()
            exit(1)


        if action == "assignmentList":
            courseId = canvas.findCourseId(courses, args.course)
            canvas.setDefaultCourseId(courseId)

            assignments = canvas.getAssignments()
            canvas.printAssignmentIds(assignments)

        elif action == "courseList":
            canvas.printCourseIds(courses)

        elif action == "studentList":
            courseId = canvas.findCourseId(courses, args.course)
            canvas.setDefaultCourseId(courseId)

            students = canvas.getStudents()
            canvas.printStudentIds(students)

        elif action == "assignmentStatus":
            courseId = canvas.findCourseId(courses, args.course)
            canvas.setDefaultCourseId(courseId)

            assignments = canvas.getAssignments()
            students = canvas.getStudents()
            assignmentId = canvas.findAssignmentId(assignments, args.assignment)
            submissions = canvas.getSubmissions(assignmentId=assignmentId)
            canvas.printSubmissionSummary(submissions, students)
    #        submissionsToGrade = canvas.findSubmissionsToGrade(submissions)
    #        canvas.printSubmissionSummary(submissionsToGrade, students)


        elif action == "assignmentDownload":
            courseId = canvas.findCourseId(courses, args.course)
            canvas.setDefaultCourseId(courseId)

            assignments = canvas.getAssignments()
            students = canvas.getStudents()

            submissions = canvas.getSubmissions(assignmentId=assignmentId)
            submissionsToGrade = canvas.findSubmissionsToGrade(submissions)
            subdir="canvas-submissions"
            canvas.downloadSubmissions(submissionsToGrade, students, dir=subdir)
            canvas.extractAllFiles(dir=subdir,newSubdir=True)

        else:
            print("Unknown action: " + action)
            parser.print_help()
            exit(1)
