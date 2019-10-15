#!/usr/bin/env python3
# Author: Scott Kuhl
import json, urllib.request, urllib.parse
import textwrap
import sys,shutil,os,stat,time,hashlib,re
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


class canvas():
    CANVAS_API = ""
    CANVAS_TOKEN = None
    courseId = 0;

    def __init__(self, token=None, api=None, courseId=None):
        canvasTokenFile = os.path.expanduser("~/.canvas-token")
        if token and api:
            self.CANVAS_TOKEN = str(token)
            self.CANVAS_API = str(api)
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

    def makeRequest(self,url):
        """Makes the given request (passes token as header)"""
        try:
            # Tack on http://.../ to the beginning of the url if needed
            if self.CANVAS_API not in url:
                urlString = self.CANVAS_API+url
            else:
                urlString = url
        
            #print("Requesting: " +urlString)
            request = urllib.request.Request(urlString)
            request.add_header("Authorization", "Bearer " + self.CANVAS_TOKEN);
            response = urllib.request.urlopen(request)
            json_string = response.read().decode('utf-8');
            retVal = json.loads(json_string)

            # Deal with pagination:
            # https://canvas.instructure.com/doc/api/file.pagination.html
            #
            # Load the next page if needed and tack the results onto
            # the end.
            response_headers = dict(response.info())
            if "Link" not in response_headers:
                return retVal
            link_header = response_headers['Link']
            link_header_split = link_header.split(",")
            for s in link_header_split:
                match = re.match('<(.*)>; rel="next"', s)
                if not match:
                    continue
                else:
                    retVal.extend(self.makeRequest(match.group(1)))

            return retVal
        except:
            e = sys.exc_info()[0]
            print(e)
            raise

    def makePut(self,url):
        """Puts data to Canvas (passes token as header)"""
        try:
            # Tack on http://.../ to the beginning of the url if needed
            if self.CANVAS_API not in url:
                urlString = self.CANVAS_API+url
            else:
                urlString = url
        
            print("Putting: " +urlString)
            request = urllib.request.Request(urlString, method='PUT')
            request.add_header("Authorization", "Bearer " + self.CANVAS_TOKEN);
            response = urllib.request.urlopen(request)
            json_string = response.read().decode('utf-8');
            retVal = dict(json.loads(json_string))
            #print (retVal)
            if(response.status == 200):
                return True
            else:
                return False
        except Exception as ex:
            print(ex)
            e = sys.exc_info()[0]
            print(e)
            raise


    def prettyPrint(self,data):
        print(json.dumps(data, sort_keys=True, indent=4))

    def getCourses(self):
        """Gets course objects"""
        allCourses = self.makeRequest("courses?"+
                                      urllib.parse.urlencode({"per_page":"100",
                                                              "page": "1"}))
        #self.prettyPrint(allCourses)

        # Some Canvas users have courses which do not appear to be
        # complete. Here, we ignore all courses which do not have a
        # name.
        validCourses = []
        for i in allCourses:
            if "name" in i:
                validCourses.append(i)

        #self.prettyPrint(validCourses)
        return validCourses

    def getTeachersAndGraders(self, courseId=None):
        # Get a listing of students (include student name, id, username, etc).
        teachers =  self.makeRequest("courses/"+str(courseId)+"/users?enrollment_type[]=teacher&"+
                                     urllib.parse.urlencode({"per_page":"100",
                                                             "page": "1"}))
        tas =  self.makeRequest("courses/"+str(courseId)+"/users?enrollment_type[]=ta&"+
                                     urllib.parse.urlencode({"per_page":"100",
                                                             "page": "1"}))
        return teachers+tas
        

    def getStudents(self, courseId=None):
        """Gets list of students in a course."""
        courseId = courseId or self.courseId
        if courseId == None:
            print("Can't getStudents without a courseId.")
            exit()

        # Get a listing of students (include student name, id, username, etc).
        students =  self.makeRequest("courses/"+str(courseId)+"/users?enrollment_type[]=student&"+
                                     urllib.parse.urlencode({"per_page":"100",
                                                             "page": "1"}))
        #self.prettyPrint(students)
        
        # Get a listing of sections (with students included in each section).
        sections =  self.makeRequest("courses/"+str(courseId)+"/sections?include[]=students&"+
                                     urllib.parse.urlencode({"per_page":"100",
                                                             "page": "1"}))
        #self.prettyPrint(sections)
        
        # Filter out students who are still "pending".  These
        # "pending" students do not have a login_id, which some of
        # this code relies on.
        nonPendingStudents = []
        for s in students:
            if 'login_id' in s:
                nonPendingStudents.append(s)
        students = nonPendingStudents
        
        # Filter out students who appear in the list twice. This can
        # happen if they are enrolled in two different sections.
        nonDupStudents = []
        studentIds = []
        for s in students:
            if s['id'] not in studentIds:
                studentIds.append(s['id'])
                nonDupStudents.append(s)
        students = nonDupStudents

        # Go through each student, find which sections they are in,
        # and add that as a piece of data in the data we
        # return. Typically students would only be in one section, but
        # this code should also work if students are in multiple
        # sections.
        for s in students:
            studentSections = [] # The names of the sections the student is in.

            # For each section in the class, go through the students
            # in that section and check if our student is in it. If
            # so, add the section name to our array.
            for sect in sections:
                if sect['students']:  # if section has students
                    for studentInSec in sect['students']:
                        if studentInSec['id'] == s['id']:
                            studentSections.append(sect['name'])

            s['kuhl_sections'] = ", ".join(map(str, studentSections))


        # Sort student list by username
        students = sorted(students, key=lambda k: k['login_id'])
            
        return students

    def getAssignments(self, courseId=None):
        """Gets list of assignments in a course."""
        courseId = courseId or self.courseId
        allAssignments = self.makeRequest("courses/"+str(courseId)+"/assignments?"+
                                          urllib.parse.urlencode({"per_page":"100",
                                                                  "page": "1"}))
        #self.prettyPrint(allAssignments)
        return allAssignments

    def commentOnSubmission(self, courseId, assignmentId, studentId, comment):
        courseId = courseId or self.courseId
        if type(courseId) != int:
            print("Can't get comment on submissions without a courseId.")
            exit(1)
        if type(assignmentId) != int or type(studentId) != int:
            printf("Can't comment on a submission without a assignment ID and a student ID.")
            exit(1)

        
        self.makePut("courses/"+str(courseId)+
                     "/assignments/"+str(assignmentId)+
                     "/submissions/"+str(studentId)+"?"+
                     urllib.parse.urlencode({"comment[text_comment]" : comment}))

    def gradeSubmission(self, courseId, assignmentId, studentId, grade):
        courseId = courseId or self.courseId
        if type(courseId) != int:
            print("Can't get comment on submissions without a courseId.")
            exit(1)
        if type(assignmentId) != int or type(studentId) != int:
            printf("Can't comment on a submission without a assignment ID and a student ID.")
            exit(1)

        
        self.makePut("courses/"+str(courseId)+
                     "/assignments/"+str(assignmentId)+
                     "/submissions/"+str(studentId)+"?"+
                     urllib.parse.urlencode({"submission[posted_grade]" : grade}))

        
    
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
        commonargs+="&"
        commonargs+=urllib.parse.urlencode({"per_page":"100",
                                            "page": "1"})


        if assignmentId == None:
            return self.makeRequest("courses/"+str(courseId)+"/students/submissions?"+commonargs)
        else:
            return self.makeRequest("courses/"+str(courseId)+"/students/submissions?assignment_ids[]="+str(assignmentId)+"&"+commonargs)

    def gradeableStudents(self, courseId=None, assignmentId=None):
        """Lists all gradeable students for this assignment. Since some assignments are only available to some students, we may not be able to grade."""
        courseId = courseId or self.courseId
        if courseId == None:
            print("Can't find courseId to retrieve list of gradeable students.")
            exit()
        print(str(assignmentId))
        if type(assignmentId) != int:
            print("assignmentId must be specified to retrieve list of gradeable students")
            exit()


        return self.makeRequest("courses/"+str(courseId)+"/assignments/"+str(assignmentId)+"/gradeable_students")

        
    def findStudent(self, students, searchString):
        """Returns a student object that matches the students name, username, or ID. The searchString must match one of the fields in the student object exactly!"""
        searchString = str(searchString).lower()
        #print("Looking for student " + searchString)
        #self.prettyPrint(students)
        #exit(1)
        for s in students:
            try:
                if s['name'].lower()          == searchString or \
                s['short_name'].lower()    == searchString or \
                s['sortable_name'].lower() == searchString or \
                s['login_id'].lower()      == searchString or \
                str(s['id']) == searchString:
                    return s
            except:
                print("ProblemStudent:"+s)

        # print("Failed to find student: " + searchString)
        return None

    def findAssignment(self, assignments, searchString):
        """Returns an assignment object that matches the assignment name out of a list of assignment objects."""
        searchString = searchString.lower()
        for a in assignments:
            try:
                if a['name'].lower() == searchString or \
                str(a['id']) == searchString:
                    return a
            except:
                pass
        return None

    def findCourse(self, courses, searchString):
        """Returns an course object that matches the course name out of a list of course objects."""
        searchString = searchString.lower()
        for c in courses:
            try:
                if c['name'].lower() == searchString or \
                str(c['id'])      == searchString:
                    return c
            except:
                pass
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

    def isSubmissionLate(self, submission):
        if submission['late']:
            return True
        else:
            return False

    def isSubmissionNewest(self, submission, submission_history):
        for s in submission_history:
            if s['attempt'] > submission['attempt']:
                return False
        return True

    def isSubmissionNewestNonLate(self, submission, submission_history):
        if submission['late']:
            return False

        # Look for a non-late submission in the history with a greater
        # attempt number.
        for s in submission_history:
            if s['late']:
                continue
            if s['attempt'] > submission['attempt']:
                return False
        return True
    
    def findSubmissionsToGrade(self, submissions, attempt=-1, acceptLate=False):
        """Returns newest non-late submissions. If attempt is set, only return the submissions with that attempt number."""
        goodSubmissions = []

        # submissions must be grouped by student and include submission history

        # For each student, get the student submission history.
        for studentSubmit in submissions:
            # self.prettyPrint(studentSubmit)
            allHistory = []
            if len(studentSubmit['submissions']) > 0:
                allHistory = studentSubmit['submissions'][0]['submission_history']

            toGrade = None
            for hist in allHistory:
                # hist['attempt'] is set to null if we have already
                # graded something that hasn't been submitted.
                if not hist['attempt']:
                    continue
                if attempt <= 0:
                    if acceptLate==True or self.isSubmissionNewestNonLate(hist, allHistory):
                        toGrade = hist
                else:
                    if attempt == hist['attempt']:
                        toGrade = hist

            # Add the submission for this student that we want to
            # grade to the list.
            if toGrade:
                goodSubmissions.append(toGrade)

        if len(goodSubmissions) == 0:
            print("WARNING: Unable to find any matching submissions.")
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

#            if 'login_id' not in student or 'name' not in student:
#                print("ERROR processing student: ")
#                self.prettyPrint(student)
#                return
                        
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


    @classmethod
    def prettyDate(obj, d, now):
        import datetime
        diff = now - d
        s = diff.seconds
        local = d.astimezone(None)
        localstring = local.strftime('%Y-%m-%d %I:%M%p')

        if diff.days > 200 or diff.days < -200:
            humanstring = ""
        elif d < now:
            if diff.days == 1:            
                humanstring = '1 day ago'
            elif diff.days > 1:
                humanstring = '{:d} days ago'.format(int(diff.days))
            elif s <= 1:
                humanstring = 'just now'
            elif s < 60:
                humanstring = '{:d} seconds ago'.format(int(s))
            elif s < 120:
                humanstring = '1 minute ago'
            elif s < 3600:
                humanstring = '{:d} minutes ago'.format(int(s/60))
            elif s < 7200:
                humanstring = '1 hour ago'
            else:
                humanstring = '{:d} hours ago'.format(int(s/3600))
        else:
            diff = d - now;
            s = diff.seconds
            if diff.days == 1:
                humanstring = '1 day from now'
            elif diff.days > 1:
                humanstring = '{:d} days from now'.format(int(diff.days))
            elif s <= 1:
                humanstring = 'moments from now'
            elif s < 60:
                humanstring = '{:d} seconds from now'.format(int(s))
            elif s < 120:
                humanstring = '1 minute from now'
            elif s < 3600:
                humanstring = '{:d} minutes from'.format(int(s/60))
            elif s < 7200:
                humanstring = '1 hour from now'
            else:
                humanstring = '{:d} hours from now'.format(int(s/3600))

        if len(humanstring) == 0:
            return localstring
        else:
            return "%s (%s)" % (localstring, humanstring)

    @classmethod
    def humanSize(self, num):
        for x in ['bytes','KiB','MiB','GiB','TiB']:
            if num < 1024.0:
                return "%d %s" % (round(num), x)
            num /= 1024.0


    def downloadSubmission(self, submission, student, directory, group_memberships={}):
        """Downloads a specific submission from a student into a directory."""

        #self.prettyPrint(submission)

        attachment = submission['attachments'][0]
        filename = attachment['filename']
        exten = os.path.splitext(filename)[1] # get filename extension
        import datetime
        utc_dt = datetime.datetime.strptime(submission['submitted_at'], '%Y-%m-%dT%H:%M:%SZ')
        utc_dt = utc_dt.replace(tzinfo=datetime.timezone.utc)

        # Create a new metadata record to save. 
        metadataNew = {
            # Put submission time in local time zone since everything
            # else is in UTC. This isn't used for anything other than
            # making it easy for someone to look at the file and
            # understand the submission time. tz=None to convert to
            # local time zone requires Python 3.3 or higher.
            "localSubmissionTime":str(utc_dt.astimezone(tz=None)),

            # Include the submission and student information:
            "canvasSubmission":submission,
            "canvasStudent":student }

        # Figure out if the name of the downloaded file/subdirectory
        # should be based on their username or group name (if there is
        # a set of groups associated with this assignment.)
        login = student['login_id']
        if student['login_id'] in group_memberships:
            (group, usersInGroup) = group_memberships[student['login_id']]
            metadataNew['canvasGroup'] = group
            metadataNew['canvasStudentsInGroup'] = usersInGroup
            login = group['name']

        # Look for an existing metadata file. When we just download
        # the submitted file (pre-extraction), We will have just the
        # submitted file and the login name with ".AUTOGRADE.json"
        # appended to it. After we extract, the submissions may go
        # into a directory.
        metadataFile = None;
        metadataFiles = [ os.path.join(directory,login+".AUTOGRADE.json"),
                          os.path.join(directory,login,"AUTOGRADE.json") ]
        for mdf in metadataFiles:
            if os.path.exists(mdf):
                metadataFile = mdf

        # Check if we need to download file based on metadata
        metadataCache = {}
        if metadataFile:
            with open(metadataFile,"r") as f:
                metadataCache = json.load(f)

        # Gather metadata and make assumptions if metadata file is missing:
        if "locked" not in metadataCache:
            print("%-12s Assuming cached copy is unlocked." % login)
        locked = metadataCache.get("locked", 0)

        if 'canvasSubmission' not in metadataCache or \
           'attempt' not in metadataCache['canvasSubmission']:
            print("%-12s Assuming cached submission is attempt 0" % login)
            cachedAttempt = 0
        else:
            cachedAttempt = metadataCache['canvasSubmission']['attempt']
        newAttempt = metadataNew['canvasSubmission']['attempt']
        isLate = metadataNew['canvasSubmission']['late']

        # Update our cached information to contain current grade
        # entered into Canvas. If we are getting a newer submission
        # than what we already have, then we'll update the metadata
        # when we get the new submission.
        if newAttempt == cachedAttempt and os.path.exists(metadataFile):
            metadataCache['canvasSubmission'] = metadataNew['canvasSubmission']
            with open(metadataFile, "w") as f:
                metadata_string = json.dump(metadataCache, f, indent=4)
        
        # Determine if we should download the submission or not
        if locked:
            print("%-12s skipping download because submission is locked to attempt %d." % (login, cachedAttempt))
            return
        if newAttempt == cachedAttempt:
            print("%-12s skipping download because we already have attempt %2d." % (login, newAttempt))
            return
        if newAttempt < cachedAttempt:
            print("%-12s WARNING: You requested attempt %2d; directory contains newer attempt %2d; SKIPPING DOWNLOAD. To force a download, erase the student directory and rerun. Or, rerun and request to dowload that students' specific attempt." % (login, newAttempt, cachedAttempt))
            return

        archiveFile  = os.path.join(directory,login+exten)

        # Delete existing archive if it exists.
        toDelete = metadataFiles
        toDelete.append(archiveFile)
        for f in toDelete:
            if os.path.exists(archiveFile):
                os.unlink(archiveFile)
        # Download the file
        print("%-12s downloading attempt %d submitted %s (replacing attempt %d)" % (login, newAttempt, 
              self.prettyDate(utc_dt, datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)), cachedAttempt))
        try:
            downloadFileName=directory+"/"+login+exten
            urllib.request.urlretrieve(attachment['url'], downloadFileName)
            print("%-12s submission size was %s" % (login, self.humanSize(os.stat(downloadFileName).st_size)))
        except:
            print("ERROR: Failed to download "+attachment['url'])
            import traceback
            traceback.print_exc()
            pass

        # Write the new metadata out to a file
        metadataNew['locked']=0
        with open(metadataFiles[0], "w") as f:
            metadata_string = json.dump(metadataNew, f, indent=4)
        
        

    def downloadSubmissions(self, submissions, students, dir=None, group_memberships={}):
        """Downloads submissions each of the students. Assumes that students submit one file (tgz.gz, zip, whatever is allowed). Files will be downloaded into the given subdirectory."""
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
                if student:
                    self.downloadSubmission(i, student, dir, group_memberships)


    def get_immediate_files(self, dir):
        """Returns an alphabetical list of all files in the current directory (non-recursive)."""
        onlyfiles = [ f for f in os.listdir(dir) if os.path.isfile(os.path.join(dir,f)) ]
        onlyfiles.sort()
        return onlyfiles

    def extractAllFiles(self, dir=".", newSubdir=False):
        print("Extracting all files into: " + dir)
        files = self.get_immediate_files(dir)
        # Here, we assume all files in the destination directory can
        # potentially be extracted. Usually, each file will be a zip
        # or tgz file from each student (with a corresponding
        # .AUTOGRADE.json) next to it.
        for f in files:
            if not f.endswith(".AUTOGRADE.json"):
                self.extractFile(dir+"/"+f, dir, newSubdir)

    def removeExecutables(self, subdirName):
        """Remove executable/ELF/EXE files anywhere in the subdirectory."""
        for dirpath, dnames, fnames in os.walk(subdirName):
            for f in fnames:            # for each file in tree
                fullpath = os.path.join(dirpath, f)
                if os.path.isfile(fullpath):   # check that it is a file
                    with open(fullpath, "rb") as fileBytes:  # open the file
                        magic = fileBytes.read(4)     # read 4 bytes
                        # print("".join("%02x" % b for b in magic))
                        # check that the 4 bytes match first 4 bytes of an ELF executable
                        if len(magic) >= 4 and magic[0] == 0x7f and magic[1] == 0x45 and magic[2]==0x4c and magic[3]==0x46:
                                print(fullpath + " is ELF executable, removing")
                                os.unlink(fullpath)
                        if len(magic) >= 4 and magic[0] == 0xcf and magic[1] == 0xfa and magic[2]==0xed and magic[3]==0xfe:
                                print(fullpath + " is Mach-O executable, removing")
                                os.unlink(fullpath)
                        if len(magic) >= 4 and magic[0] == 0xce and magic[1] == 0xfa and magic[2]==0xed and magic[3]==0xfe:
                                print(fullpath + " is Mach-O executable, removing")
                                os.unlink(fullpath)
                        if len(magic) >= 2 and magic[0] == 0x4d and magic[1] == 0x5a:
                                print(fullpath + " is Windows executable, removing")
                                os.unlink(fullpath)

    def fixShellScriptPerms(self, subdirName):
        """Finds files that look like shell scripts, makes them executable. Zip files lose permission bits"""
        for dirpath, dnames, fnames in os.walk(subdirName):
            for f in fnames:            # for each file in tree
                fullpath = os.path.join(dirpath, f)
                if os.path.isfile(fullpath):   # check that it is a file
                    with open(fullpath, "rb") as fileBytes:  # open the file
                        magic = fileBytes.read(3)
                        #print(fullpath + " " + str(magic))
                        if magic == b'#!/':
                            print(fullpath + " is apparently a shell script. Making executable.")
                            currentPerm = os.stat(fullpath).st_mode
                            os.chmod(fullpath, currentPerm | stat.S_IXUSR)
                                
                                
    def removeDSStore(self, subdirName):
        """Remove unnecessary Apple-related files anywhere in the subdirectory."""
        for dirpath, dnames, fnames in os.walk(subdirName):
            for f in fnames:
                fullpath = os.path.join(dirpath, f)
                if os.path.isfile(fullpath):
                    # https://en.wikipedia.org/wiki/.DS_Store
                    # https://apple.stackexchange.com/questions/14980/
                    if f == ".DS_Store" or f.startswith("._"):
                        print(fullpath + " is unnecessary Apple-related file, removing")
                        os.unlink(fullpath)
            for d in dnames:
                fullpath = os.path.join(dirpath, d)
                if os.path.isdir(fullpath) and d == "__MACOSX":
                    print(fullpath + " is a Apple related folder, removing")
                    shutil.rmtree(fullpath)
            for d in dnames:
                fullpath = os.path.join(dirpath, d)
                if os.path.isdir(fullpath) and d.endswith(".dSYM"):
                    print(fullpath + " is a Apple related folder, removing")
                    shutil.rmtree(fullpath)

    def removeSymLinks(self, subdirName):
        """Remove symbolic links anywhere in the subdirectory."""
        for dirpath, dnames, fnames in os.walk(subdirName):
            for f in fnames:
                fullpath = os.path.join(dirpath, f)
                if os.path.islink(fullpath):
                        print(fullpath + " is a symlink, removing")
                        os.unlink(fullpath)


    def removeBackupFiles(self, subdirName):
        """Remove unnecessary text-editor backup files anywhere in the subdirectory."""
        for dirpath, dnames, fnames in os.walk(subdirName):
            for f in fnames:
                fullpath = os.path.join(dirpath, f)
                if os.path.isfile(fullpath):
                    if (f.startswith("#") and f.endswith("#")) or \
                       f.endswith("~"):
                        print(fullpath + " is a text-editor backup file, removing")
                        os.unlink(fullpath)

    def removeVisualStudio(self, subdirName):
        """Remove unnecessary visual studio files found anywhere in the subdirectory."""
        for dirpath, dnames, fnames in os.walk(subdirName):
            for d in dnames:
                fullpath = os.path.join(dirpath, d)
                if os.path.isdir(fullpath):
                    if d == ".vs" or d == "Debug":
                        print(fullpath + " is a Visual Studio directory, removing")
                        shutil.rmtree(fullpath)
            for f in fnames:
                fullpath = os.path.join(dirpath, f)
                if os.path.isfile(fullpath):
                    if f.endswith(".ilk") or f.endswith(".pdb") or f.endswith(".lib"):
                        print(fullpath + " is a Visual Studio file, removing")
                        os.unlink(fullpath)


    def removeGit(self, subdirName):
        """Remove unnecessary git repos found anywhere in the subdirectory."""
        for dirpath, dnames, fnames in os.walk(subdirName):
            for d in dnames:
                fullpath = os.path.join(dirpath, d)
                if os.path.isdir(fullpath):
                    if d == ".git":
                        print(fullpath + " is a git repo, removing")
                        shutil.rmtree(fullpath)

    def removeAutograder(self, subdirName):
        """Removes any AUTOGRADE* files that the student might maliciously submit."""
        for dirpath, dnames, fnames in os.walk(subdirName):
            for f in fnames:
                fullpath = os.path.join(dirpath, f)
                if os.path.isfile(fullpath):
                    if f.startswith("AUTOGRADE"):
                        print(fullpath + " is an autograder file; clever students might try to maliciously submit these to mess with the autograder")
                        os.unlink(fullpath)

    def removeEndings(self, subdirName, extens):
        """Given a list of filename extensions, delete all of the files anywhere in the subdirectory.."""
        for dirpath, dnames, fnames in os.walk(subdirName):
            for f in fnames:
                fullpath = os.path.join(dirpath, f)
                if os.path.isfile(fullpath):
                    for e in extens:
                        if f.endswith(e):
                            print(fullpath + " is a "+e+" file, removing")
                            os.unlink(fullpath)

    def removeEmptyDirs(self, subdirName):
        """Remove empty folders anywhere in the subdirectory."""
        for dirpath, dnames, fnames in os.walk(subdirName, topdown=False):
            for d in dnames:
                try:
                    fullpath = os.path.join(dirpath, d)
                    os.rmdir(os.path.join(dirpath, d))
                    print(fullpath + " is an empty folder; removed.");
                except OSError:
                    pass
                
    def extractFile(self, filename, dir, newSubdir=False):
        """Extracts filename into dir. If newSubdir is set, create an additional subdirectory inside of dir to extract the files into."""

        if os.path.basename(filename).startswith("."):
            print("Assuming hidden file isn't a student submission: %s" % filename)
            return
        
        import tarfile,zipfile
        destDir = dir
        if newSubdir:
            # If using newSubdir, make a directory with the same
            # name as the file but without the extension.
            destDir = os.path.splitext(filename)[0]


        # Calculate md5sum
        md5sum = ""
        with open(filename, 'rb') as fh:
            m = hashlib.md5()
            while True:
                data = fh.read(8192)
                if not data:
                    break
                m.update(data)
            md5sum = m.hexdigest()

        if os.path.exists(destDir):
            shutil.rmtree(destDir)

        # Ensure destination directory exists. If a student submits an
        # empty tgz file, for example, the code below won't create the
        # empty directory.
        os.mkdir(destDir)
        try:
            # tarfile.is_tarfile() and zipfile.is_zipfile() functions
            # are available, but sometimes it misidentifies files (for
            # example .docx files are zip files).
            if filename.endswith(".tar") or \
               filename.endswith(".tar.gz") or  \
               filename.endswith(".tgz") or \
               filename.endswith(".tar.bz2") or \
               filename.endswith(".tbz") or \
               filename.endswith(".tbz2") or \
               filename.endswith(".tb2"):
                tar = tarfile.open(filename)
                tar.extractall(path=destDir)
                tar.close()
                os.remove(filename)
                print(destDir + ": Extracted " + filename + " into " + destDir);
            elif filename.endswith(".zip"):
                z = zipfile.ZipFile(filename)
                z.extractall(path=destDir)
                z.close()
                os.remove(filename)
                print(destDir + ": Extracted " + filename + " into " + destDir);
            else:
                # Comment out the following lines to prevent single
                # file submissions from getting put into
                # subdirectories. Removing this line may break a
                # variety of different elements of the autograder.
                print("Trying to move "+filename+" to "+destDir)
                shutil.move(filename, destDir)
                print(destDir + ": No need to extract " + filename);
        except:
            print(destDir + ": Failed to extract file: "+filename)

        # Get a copy of the metadata for this file
        metadataFile = destDir+".AUTOGRADE.json"
        metadata = {}
        if os.path.exists(metadataFile):
            with open(metadataFile, "r") as f:
                metadata = json.load(f)
        # add md5sum to metadata
        metadata['md5sum']=md5sum
        
        # If subdirectory wasn't created, overwrite existing metadata file
        if not os.path.exists(destDir):
            with open(metadataFile, "w") as f:
                json.dump(metadata, f, indent=4)
        else: # If we did extract files into a subdirectory
            # Remove files we don't need or want.
            self.removeSymLinks(destDir)
            self.removeExecutables(destDir)
            self.removeVisualStudio(destDir)
            self.removeDSStore(destDir)
            self.removeBackupFiles(destDir)
            self.removeGit(destDir)
            self.removeAutograder(destDir)
            self.removeEndings(destDir, [".zip", ".tgz", ".tar", ".tar.gz", ".a"])
            self.fixShellScriptPerms(destDir)
            # Do this last since deleting files above can create empty dirs:
            self.removeEmptyDirs(destDir)
            
            # Remove unnecessary subdirectories
            while True:
                onlyfiles = [ f for f in os.listdir(destDir) if os.path.isfile(os.path.join(destDir,f)) ]
                onlydirs = [ f for f in os.listdir(destDir) if os.path.isdir(os.path.join(destDir,f)) ]
                print(destDir + ": Contains %d file(s) and %d dir(s)"%(len(onlyfiles), len(onlydirs)))
                # If submission included all files in a subdirectory, remove the subdirectory
                if len(onlyfiles) == 0 and len(onlydirs) == 1:
                    print(destDir + ": Removing unnecessary subdirectory named '"+onlydirs[0]+"'")
                    # Delete previous temporary directory if it exists
                    shutil.rmtree("/tmp/autograder-tmp-dir", ignore_errors=True)
                    # Move subfolder into temporary directory
                    tmpDir = "/tmp/autograder-tmp-dir/"+onlydirs[0]
                    shutil.move(destDir+"/"+onlydirs[0], tmpDir)
                    # Move the files files in the temporary directory into the destination directory
                    for f in os.listdir(tmpDir):
                        #print("moving: "+tmpDir+"/"+f+" to "+destDir)
                        shutil.move(tmpDir+"/"+f, destDir)
                    # Remove temporary directory
                    shutil.rmtree("/tmp/autograder-tmp-dir", ignore_errors=True)
                else:
                    break; # done removing nested single directories

            # Remove original metadata file, write one out in the
            # subdirectory.
            metadataFileDestDir = os.path.join(destDir,"AUTOGRADE.json")
            os.remove(metadataFile)
            with open(metadataFileDestDir, "w") as f:
                json.dump(metadata, f, indent=4)

            # Don't allow others to read/write/execute files or directories
            for dirpath, dnames, fnames in os.walk(destDir):
                for path in dnames+fnames:
                    path = os.path.join(dirpath, path)
                    currentPerm = os.stat(path).st_mode
                    os.chmod(path, currentPerm & ~(stat.S_IROTH | stat.S_IWOTH | stat.S_IXOTH | stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP))
                currentPerm = os.stat(dirpath).st_mode
                os.chmod(dirpath, currentPerm & ~(stat.S_IROTH | stat.S_IWOTH | stat.S_IXOTH | stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP))

    def printCourseIds(self, courses):
        for i in courses:
            print("%10s \"%s\""%(str(i['id']), i['name']))

    def printAssignmentIds(self, assignments):
        for i in assignments:
            print("%10s %s"%(str(i['id']), i['name']))
  
    def printStudentIds(self, students):
        for i in students:
            #print(i)
            print("%10s %-10s %-25s %s"%(str(i['id']), i['login_id'], i['name'], i['kuhl_sections']))

    def setDefaultCourseId(self, courseId):
        if courseId == None:
            print("Warning: You are setting the default courseId to None.")
        self.courseId = courseId;

    def downloadAssignment(self, courseName, assignmentName, subdirName, userid=None, attempt=-1, acceptLate=False):
        # Find the course
        courses = self.getCourses()
        courseId = self.findCourseId(courses, courseName)
        if courseId == None:
            print("Failed to find course " + courseName);
            exit(1)

        # Get a list of assignments
        assignments = self.getAssignments(courseId=courseId)
        
        # Get a list of the students in the course
        students    = self.getStudents(courseId=courseId)
        # Filter that list down to the requested student
        if userid:
            students = [ student for student in students if userid==student['login_id']]
            if len(students) == 0:
                print("No matching student for userid %s" % userid)
                exit(1)

        #self.printCourseIds(courses)
        #self.printAssignmentIds(assignments)
        #self.printStudentIds(students)

        # Find the assignment in the list of assignments
        assignmentId = self.findAssignmentId(assignments, assignmentName)
        if assignmentId == None:
            self.printAssignmentIds(assignments)
            print("Failed to find assignment " + assignmentName);
            exit(1)

        # Crate a dictionary to map usernames to (group, usersInGroup)
        group_memberships = {}
        assignment = self.findAssignment(assignments, assignmentName)
        assignmentGroupCat = assignment['group_category_id']
        if assignmentGroupCat:
            assignmentGroups = self.makeRequest("group_categories/"+str(assignmentGroupCat)+"/groups")
            for g in assignmentGroups:
                usersInGroup = self.makeRequest("groups/"+str(g['id'])+"/users")
                for u in usersInGroup:
                    if 'login_id' in u: # Filter out pending students in a group
                        group_memberships[u['login_id']] = (g, usersInGroup);

        # Get the submissions for the assignment
        if userid:
            studentId = students[0]['id']
        else:
            studentId = None
        
        submissions = self.getSubmissions(courseId=courseId, assignmentId=assignmentId, studentId=studentId)

        # Filter out the submissions that we want to grade (newest, non-late submission)
        submissionsToGrade = self.findSubmissionsToGrade(submissions, attempt, acceptLate)

        # Download the submissions
        self.downloadSubmissions(submissionsToGrade, students, subdirName, group_memberships)

        # Assuming zip, tgz, or tar.gz files are submitted, extract
        # them into subdirectories named after the student usernames.
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


    canvas = canvas()
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

            canvas.prettyPrint(canvas.gradeableStudents(assignmentId=assignmentId))

        elif action == "assignmentDownload":
            canvas.downloadAssignment(args.course, args.assignment, "canvas-submissions")

        # elif action == "testCommenting":
        #     courseId = canvas.findCourseId(courses, args.course)
        #     canvas.setDefaultCourseId(courseId)

        #     assignments = canvas.getAssignments()
        #     students = canvas.getStudents()
        #     assignmentId = canvas.findAssignmentId(assignments, args.assignment)
        #     submissions = canvas.getSubmissions(assignmentId=assignmentId)

        #     canvas.commentOnSubmission(courseId=courseId, assignmentId=assignmentId, studentId=3924612, comment="hello world")
        #     canvas.gradeSubmission(courseId=courseId, assignmentId=assignmentId, studentId=3924612, grade=1)


            
        else:
            print("Unknown action: " + action)
            parser.print_help()
            exit(1)
