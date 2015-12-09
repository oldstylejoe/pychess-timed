from __future__ import print_function
from __future__ import absolute_import

import os
import sys
import time
import logging

from pychess.compat import PY3
from .prefix import addUserDataPrefix

from logging.handlers import TimedRotatingFileHandler

newName = time.strftime("%Y-%m-%d_%H-%M-%S") + ".log"
logformat = "%(asctime)s.%(msecs)03d %(task)s %(levelname)s: %(message)s"

# delay=True argument prevents creating empty .log files
encoding = "utf-8" if sys.platform == "win32" and PY3 else None
#fh = logging.FileHandler(addUserDataPrefix(newName), delay=True, encoding=encoding)
#fh.setFormatter(logging.Formatter(fmt=logformat, datefmt='%H:%M:%S'))

logger = logging.getLogger()
logger.setLevel(logging.INFO)
handler = TimedRotatingFileHandler("c:/DataLogs/chess/moves", when="h", interval=1, backupCount=0)
handler.setFormatter(logging.Formatter(fmt=logformat, datefmt='%H:%M:%S'))
logger.addHandler(handler)
#logger = logging.getLogger()
#logger.addHandler(fh)


class ExtraAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        kwargs["extra"] = kwargs.get("extra", {"task": "Default"})
        return msg, kwargs

log = ExtraAdapter(logger, {})

    
class LogPipe:
    def __init__ (self, to, flag=""):
        self.to = to
        self.flag = flag
        # Needed for blunders/arena with python3
        self.errors= to.errors
        self.encoding = to.encoding
    
    def write (self, data):
        try:
            self.to.write(data)
            self.flush()
        except IOError:
            if self.flag == "stdout":
                # Certainly hope we never end up here
                pass
            else:
                log.error("Could not write data '%s' to pipe '%s'" % (data, repr(self.to)))
        if log:
            for line in data.splitlines():
                if line:
                    log.debug (line, extra={"task": self.flag})
    
    def flush (self):
        self.to.flush()
    
    def fileno (self):
        return self.to.fileno()

###Accurately timed log
import ctypes

#wrapper class to get data from mswindows call
class FileTime(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", ctypes.c_uint),
        ("dwHighDateTime", ctypes.c_uint)]
#speed up a few calls
#global getTime
getTime = ctypes.windll.kernel32.GetSystemTimePreciseAsFileTime
#global getRef
getRef = ctypes.byref
import threading

#This writes to a file in a given root directory.
#The file is only locked during a write request.
#A new file is created every day, the rest of the time it is appended to.
#TODO: make this threadsafe
class safeFile():
    def __init__(self, base="c:/DataLogs/chess/log_", extension=".txt"):
        self.base = base
        self.extension = extension

        self.f = FileTime()
        self.fil = None
        self.fname = None
        self.curDay = None

        self.lock = threading.Lock()

        self.subjid = ""
        self.readSubjectID()

        #this is hacked in since the format should be fixed
        self.header = """#Timestamped data recorder for chess.
#All times are in seconds since the UTC epoch (1/1/1601 at 12am)
#Variability from the clock itself is about 1 microsecond (on ms surface pro 3).
#
#time localTime subject message\n"""
        
    def _openFile(self):
        #could be problems here if the day rolls over
        t = time.ctime().split()
        self.curDay = t[1]+"_"+t[2]+"_"+t[4]
        self.fname = self.base+"_"+self.subjid+"_"+self.curDay+self.extension
        if not os.path.isfile(self.fname):
            self.fil = open(self.fname, 'w')
            self.fil.write(self.header)
            self.fil.close()
        self.fil = open(self.fname, "a")

    def write(self, data):
        getTime(getRef(self.f))
        localTime  = time.ctime().replace(' ', '_')
        self.lock.acquire()
        try:
            self._openFile()
            #self.fil.write(("%20.19g "%(time.time())) + time.ctime().replace(' ', '_') + " " + self.subjid + " " + data + "\n")
            self.fil.write(("%d%.12g "%(self.f.dwHighDateTime, float(self.f.dwLowDateTime)*1e-7)) + localTime + " " + self.subjid + " " + data + "\n")
            self.fil.close()
        except IOError:
            return -1
        finally:
            self.lock.release()
        return 1

    def readSubjectID(self):
        try:
            fil = open("c:/public/subject_id.txt", 'r')
            for line in fil:
                self.subjid = line.strip()
        except IndexError:
            #print "Subject is empty"
            pass
        except IOError:
            #print "Unable to open subject file"
            pass

timedLog = safeFile()

