#!/usr/bin/env python3
'''Edits and restores the default menu entry in the iPXE boot script.'''

import os
from pathlib import Path
from diag import log
from colorprint import C


def check_boot_ipxe(BOOT_IPXE_FILE, BOOT_IPXE_BACKUP):
  '''Ensures the iPXE boot script defaults set to the "hassiobatch" menu entry.

  Parameters
  ----------
  BOOT_IPXE_FILE : str
    Path to the live "boot.ipxe" script to inspect and, if needed, rewrite.
  BOOT_IPXE_BACKUP : str
    Path where the original "boot.ipxe" is saved before any change.

  Returns
  -------
  None
    Returns early if the default is already correct. Otherwise it writes a
    backup of the original file and rewrites "boot.ipxe" so that the
    "hassiobatch" entry is the default (all other defaults commented out).
  '''

  with open(BOOT_IPXE_FILE, "r") as f:
    lines = f.readlines()

  fixed_boot_ipxe = []
  for line in lines:
    # Processing all default setting in boot.ipxe
    if ("choose --default" in line):

      # First, check if hassiobatch default is set - if so then just return
      if line.lstrip().startswith("choose --default hassiobatch"):
        log(f"{C.GREEN}[iPXE]{C.RESET} File boot.ipxe has default menuitem set correctly, no changes required.")
        return

      # If HASSIO backup menuitem commented out - we need to uncomment it
      if line.lstrip().startswith("# choose --default hassiobatch"):
        fixed_boot_ipxe.append(line.replace("# ", ""))
        continue

      # All other defaults should be commented out
      if not ("hassiobatch" in line) and not (line.lstrip().startswith("#")):
        fixed_boot_ipxe.append("# " + line)
        continue

    # The line doesn't contain "choose --default" so just append it as is
    fixed_boot_ipxe.append(line)

  # Creating a backup
  with open(BOOT_IPXE_BACKUP, "w") as f:
    f.writelines(lines)

  # Fixed boot.ipxe
  with open(BOOT_IPXE_FILE, "w") as f:
    f.writelines(fixed_boot_ipxe)

  log(f"{C.GREEN}[iPXE]{C.RESET} File boot.ipxe fixed, default menuitem changed.")
  return


def revert_boot_ipxe(BOOT_IPXE_FILE, BOOT_IPXE_BACKUP):
  '''Restores the original "boot.ipxe" from its backup, if one exists.

  Parameters
  ----------
  BOOT_IPXE_FILE : str
    Path to the live "boot.ipxe" script to be restored.
  BOOT_IPXE_BACKUP : str
    Path to the previously saved backup file.

  Returns
  -------
  None
    If the backup file exists it is renamed back over the live file -
    otherwise the function does nothing.
  '''

  if Path(BOOT_IPXE_BACKUP).exists():
    log(f"{C.GREEN}[Finish]{C.RESET} Restoring boot.ipxe file from backup.")
    os.rename(BOOT_IPXE_BACKUP, BOOT_IPXE_FILE)

