﻿#!/usr/bin/python

# PyChess startup script.
# This script is to check package requirements, and set up system/enviroment
# stuff, to make the PyChess Main class run smoothly.

# faulthandler will be in Python 3.3; for 2.x you can download it from pypi
from __future__ import print_function
try:
    import faulthandler
    faulthandler.enable()
except ImportError:
    pass

###############################################################################
# Check requirements

import argparse
import os, sys
if sys.version_info < (2, 7, 0):
    print('ERROR: PyChess requires Python >= 2.7')
    sys.exit(1)

import gi
gi.require_version("Gtk", "3.0")

try:
    from gi.repository import GtkSource
except ImportError:
    print('ERROR: Could not load the gtksourceview2 python module.')
    print('You need to install the gtksourceview2 python package which is ')
    print('called pygtksourceview in most distributions')
    sys.exit(1)


###############################################################################
# Fix environment

this_dir = os.path.dirname(os.path.abspath(__file__))
if os.path.isdir(os.path.join(this_dir, "lib/pychess")) and \
        os.path.join(this_dir, "lib") not in sys.path:
    sys.path = [os.path.join(this_dir, "lib")] + sys.path

###############################################################################
# Ensure access to data store

try:
    from pychess.System.prefix import addDataPrefix, getDataPrefix, isInstalled
except ImportError:
    print("ERROR: Could not import modules.")
    print("Please try to run pychess as stated in the INSTALL file")
    sys.exit(1)

# now we can import from compat module 
from pychess.compat import PY2

if PY2:
    # This hack fixes some UnicodDecode Errors caused pygi not making
    # magic hidden automatic unicode conversion pygtk did
    reload(sys)
    sys.setdefaultencoding("utf-8")

###############################################################################
# Set up translations

import gettext, locale

# http://stackoverflow.com/questions/3678174/python-gettext-doesnt-load-translations-on-windows
if sys.platform.startswith('win'):
    if os.getenv('LANG') is None:
        lang, enc = locale.getdefaultlocale()
        os.environ['LANG'] = lang

locale.setlocale(locale.LC_ALL, '')

domain = "pychess"
if isInstalled():
    locale_dir = os.path.join(os.path.dirname(getDataPrefix()), "locale")
    if PY2:
        gettext.install(domain, unicode=1, names=('ngettext',))
    else:
        gettext.install(domain, names=('ngettext',))
else:
    locale_dir = addDataPrefix("lang")
    if PY2:
        gettext.install(domain, localedir=locale_dir, unicode=1, names=('ngettext',))
    else:
        gettext.install(domain, localedir=locale_dir, names=('ngettext',))

# http://stackoverflow.com/questions/10094335/how-to-bind-a-text-domain-to-a-local-folder-for-gettext-under-gtk3
if sys.platform == "win32":
    from ctypes import cdll
    libintl = cdll.LoadLibrary("libintl-8")
    libintl.bindtextdomain(domain, locale_dir)
    libintl.bind_textdomain_codeset(domain, 'UTF-8')
else:
    locale.bindtextdomain(domain, locale_dir)

###############################################################################
# Parse command line arguments

import pychess
no_debug = False
no_idle_add_debug = False
no_thread_debug = False
log_viewer = True
chess_file = sys.argv[1] if len(sys.argv) > 1 else None
ics_host = None
ics_port = None

version = "%s (%s)" % (pychess.VERSION, pychess.VERSION_NAME)
description = "The PyChess chess client, version %s." % version

parser = argparse.ArgumentParser(description=description)
parser.add_argument('--version', action='version',
    version="%(prog)s" + " %s" % version)
parser.add_argument('--no-debug', action='store_true',
    help='turn off debugging output')
parser.add_argument('--no-idle-add-debug', action='store_true',
    help='turn off idle-add debugging output')
parser.add_argument('--no-thread-debug', action='store_true',
    help='turn off thread debugging output')
parser.add_argument('--log-viewer', action='store_false',
    help='disable Log Viewer menu')
parser.add_argument('--ics-host', action='store',
    help='the hostname of internet chess server (default is freechess.org)')
parser.add_argument('--ics-port', action='store', type=int,
    help='the connection port of internet chess server (default is 5000)')
parser.add_argument('chess_file', nargs='?', metavar='chessfile',
    help='a chess file in PGN, EPD, FEN, or HTML (Chess Alpha 2 Diagram) format')

args = parser.parse_args()
no_debug = args.no_debug
no_idle_add_debug = args.no_idle_add_debug
no_thread_debug = args.no_thread_debug
log_viewer = args.log_viewer
chess_file = args.chess_file
ics_host = args.ics_host
ics_port = args.ics_port
    
###############################################################################
# Let's rumble!

import pychess.Main
pychess.Main.run(no_debug, no_idle_add_debug, no_thread_debug, log_viewer,
                 chess_file, ics_host, ics_port)
