#!/usr/bin/env python3
'''Logging helper: echo to the console and mirror plain text to backup.log.'''

from datetime import datetime
from colorprint import C

def log(msg):
  '''Prints "msg" to stdout and appends a timestamped, ANSI-stripped copy.

  Parameters
  ----------
  msg : str
    Message to be echoed and mirrored to the logfile.

  Returns
  -------
  None
  '''

  with open(f"backup.log", "a") as backup_log:
    print(f"{msg}")

    # Remove coloring ANSI sequences before putting to logfile
    for ansi_code in (C.GREEN, C.RED, C.RESET, "\r"):
      msg = msg.replace(ansi_code, "")

    timestamp = datetime.now().strftime("%m-%d-%Y %H:%M:%S")
    print(f"[{timestamp}] {msg}", file=backup_log)
