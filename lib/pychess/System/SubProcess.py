from __future__ import absolute_import
from __future__ import print_function

import os
import sys
import signal
import errno
import time
import traceback
import threading
from threading import currentThread, Thread

from gi.repository import GObject
from gi.repository import GLib

from pychess.Utils.const import *
from pychess.System import fident
from .Log import log
from .which import which

class SubProcessError (Exception): pass
class TimeOutError (Exception): pass

def searchPath (file, access=os.R_OK, altpath=None):
    if altpath and os.path.isfile(altpath):
        if not os.access (altpath, access):
            log.warning("Not enough permissions on %s" % altpath)
        else:
            return altpath

    return which(file, mode=access)

subprocesses = []
def finishAllSubprocesses ():
    for subprocess in subprocesses:
        if subprocess.subprocExitCode[0] == None:
            subprocess.gentleKill(0,0.3)
    for subprocess in subprocesses:
        subprocess.subprocFinishedEvent.wait()

class SubProcess (GObject.GObject):
    
    __gsignals__ = {
        "line": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "died": (GObject.SignalFlags.RUN_FIRST, None, ())
    }

    def __init__(self, path, args=[], warnwords=[], env=None, chdir="."):      
        GObject.GObject.__init__(self)
        
        self.path = path
        self.args = args
        self.warnwords = warnwords
        self.env = env or os.environ
        self.buffer = ""
        
        self.defname = os.path.split(path)[1]
        self.defname = self.defname[:1].upper() + self.defname[1:].lower()
        t = time.time()
        self.defname = (self.defname,
                        time.strftime("%H:%m:%%.3f",time.localtime(t)) % (t%60))
        log.debug(path, extra={"task":self.defname})
        
        argv = [str(u) for u in [self.path]+self.args]
        log.debug("SubProcess.__init__: spawning...",  extra={"task":self.defname})
        
        def do_spawn_async(event):
            self.pid, stdin, stdout, stderr = GObject.spawn_async(argv,
                    working_directory=chdir, child_setup=self.__setup,
                    standard_input=True, standard_output=True, standard_error=True,
                    flags=GObject.SPAWN_DO_NOT_REAP_CHILD|GObject.SPAWN_SEARCH_PATH)        
           
            log.debug("SubProcess.__init__: _initChannel...",  extra={"task":self.defname})
            self.__channelTags = []
            self.inChannel = self._initChannel(stdin, None, None, False)
            readFlags = GObject.IO_IN|GObject.IO_HUP#|GObject.IO_ERR
            self.outChannel = self._initChannel(stdout, readFlags, self.__io_cb, False)
            self.errChannel = self._initChannel(stderr, readFlags, self.__io_cb, True)
            
            log.debug("SubProcess.__init__: channelsClosed...",  extra={"task":self.defname})
            self.channelsClosed = False
            self.channelsClosedLock = threading.Lock()
            log.debug("SubProcess.__init__: child_watch_add...",  extra={"task":self.defname})
            GObject.child_watch_add(self.pid, self.__child_watch_callback, None)
            if event is not None:
                event.set()
        
        thread = currentThread()
        if thread.name == "MainThread":
            do_spawn_async(None)
        else:
            event = threading.Event()
            GLib.idle_add(do_spawn_async, event)
            event.wait()
        
        log.debug("SubProcess.__init__: subprocExitCode...",  extra={"task":self.defname})
        self.subprocExitCode = (None, None)
        self.subprocFinishedEvent = threading.Event()
        subprocesses.append(self)
        log.debug("SubProcess.__init__: finished",  extra={"task":self.defname})
    
    def _initChannel (self, filedesc, callbackflag, callback, isstderr):        
        channel = GLib.IOChannel(filedesc)
        channel.set_encoding(None)
        if sys.platform != "win32":
            channel.set_flags(GObject.IO_FLAG_NONBLOCK)
        if callback:
            tag = channel.add_watch(callbackflag, callback, isstderr)
            self.__channelTags.append(tag)
        return channel
    
    def _closeChannels (self):
        self.channelsClosedLock.acquire()
        try:
            if self.channelsClosed == True:
                return
            self.channelsClosed = True
        finally:
            self.channelsClosedLock.release()

        for tag in self.__channelTags:
            GObject.source_remove(tag)
        for channel in (self.inChannel, self.outChannel, self.errChannel):
            try:
                channel.close()
            except GObject.GError as error:
                pass
    
    def __setup (self):
        os.nice(15)
    
    def __child_watch_callback (self, pid, code, data):
        log.debug("SubProcess.__child_watch_callback: %s" % repr(code), 
                  extra={"task":self.defname})
        # Kill the engine on any signal but 'Resource temporarily unavailable'
        self.subprocExitCode = (code, os.strerror(code))
        if code != errno.EWOULDBLOCK:
            if isinstance(code, str):
                log.error(code, extra={"task":self.defname})
            else: log.error(os.strerror(code), extra={"task":self.defname})
            self.emit("died")
            self.gentleKill()
    
    def __io_cb (self, channel, condition, isstderr):
        line = ""
        if condition is GObject.IO_IN:
            line = channel.readline()
        elif condition is GObject.IO_IN|GObject.IO_HUP:
            return False
        # Some engines send author names in different encodinds (f.e. spike)
        if line.startswith("id author") or not line:
            return True
        if isstderr:
            log.error(line, extra={"task":self.defname})
        else:
            for word in self.warnwords:
                if word in line:
                    log.warning(line, extra={"task":self.defname})
                    return False
            else:
                log.debug(line.rstrip(), extra={"task":self.defname})
        
        self.emit("line", line)
        return True
            
    def write (self, data):
        if self.channelsClosed:
            log.warning("Chan closed for %r" % data, extra={"task":self.defname})
            return
        if data.rstrip():
            log.info(data, extra={"task":self.defname})
        self.inChannel.write(data)
        if data.endswith("\n"):
            try:
                self.inChannel.flush()
            except GObject.GError as e:
                log.error(str(e)+". Last line wasn't sent.", extra={"task":self.defname})

    def sendSignal (self, sign):
        try:
            if sys.platform != "win32":
                os.kill(self.pid, signal.SIGCONT)
            os.kill(self.pid, sign)
        except OSError as e:
            if e.errno in (errno.ESRCH, errno.EACCES, errno.EINVAL):
                #No such process, Permission denied, Invalid argument
                pass
            else:
                raise OSError(e.errno, os.strerror(e.errno))
    
    def gentleKill (self, first=1, second=1):
        t = Thread(target=self.__gentleKill_inner,
                   name=fident(self.__gentleKill_inner),
                   args=(first, second))
        t.daemon = True
        t.start()
    
    def __gentleKill_inner (self, first, second):
        self.resume()
        self._closeChannels()
        time.sleep(first)
        code, string = self.subprocExitCode
        if code == None:
            self.sigterm()
            time.sleep(second)
            code, string = self.subprocExitCode
            if code == None:
                self.sigkill()
                self.subprocFinishedEvent.set()
                return self.subprocExitCode[0]
            self.subprocFinishedEvent.set()
            return code
        self.subprocFinishedEvent.set()
        return code
    
    def pause (self):
        if sys.platform != "win32":
            self.sendSignal(signal.SIGSTOP)
    
    def resume (self):
        if sys.platform != "win32":
            self.sendSignal(signal.SIGCONT)
    
    def sigkill (self):
        if sys.platform == "win32":
            self.sendSignal(signal.SIGABRT)
        else:
            self.sendSignal(signal.SIGKILL)
        GLib.spawn_close_pid(self.pid)
    
    def sigterm (self):
        self.sendSignal(signal.SIGTERM)
    
    def sigint (self):
        self.sendSignal(signal.SIGINT)

if __name__ == "__main__":
    loop = GObject.MainLoop()
    paths = ("igang.dk", "google.com", "google.dk", "myspace.com", "yahoo.com")
    maxlen = max(len(p) for p in paths)
    def callback (subp, line, path):
        print("\t", path.ljust(maxlen), line.rstrip("\n"))
    for path in paths:
        subp = SubProcess("/bin/ping", [path])
        subp.connect("line", callback, path)
    loop.run()
