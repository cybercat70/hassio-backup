#!/usr/bin/env python3

import pexpect
from vault import get_vault_credentials
from diag import log
from colorprint import C


def telnet_initial_sequence():
  ''' Get credentials from HashiCorp Vault '''
  creds = get_vault_credentials("pdu")

  pdu_username = creds["pdu_username"]
  pdu_password = creds["pdu_password"]
  pdu_host = creds["pdu_host"]
  pdu_port = creds["pdu_port"]

  session = pexpect.spawn(f"telnet {pdu_host} {pdu_port}", timeout=10)

  try:
    result = session.expect([
      "User Name :",
      pexpect.EOF,
      pexpect.TIMEOUT
    ])

    if result != 0:
      raise ConnectionError("[PDU] Telnet connection to PDU failed, exiting.")

    session.sendline(pdu_username)
    session.expect('Password  :')
    session.sendline(pdu_password)
    session.expect('>')
    session.sendline('1')				# Device manager
    session.expect('>')
    session.sendline('2')				# Outlet Management
    session.expect('>')
    session.sendline('1')				# Outlet Control/Configuration
    session.expect('>')
    session.sendline("\r")				# A trick to re-read outlets list
    session.expect('>')

    return session

  except (pexpect.EOF, pexpect.TIMEOUT) as e:
    session.close()
    raise ConnectionError(f"[PDU] Control sequence error: {e}") from e


def outlet_control(outlet, mode):
  if mode == "on":
    mode_number = "1"
    mode_color = C.GREEN
  else:
    mode_number = "2"
    mode_color = C.RED

  log(f"{C.GREEN}[PDU]{C.RESET} Managing HASSIO outlet (#{outlet})...")

  session = None

  try:
    session = telnet_initial_sequence()

    session.sendline(str(outlet))						# outlet index
    session.expect('>')
    session.sendline('1')							# Control Outlet
    session.expect('>')
    session.sendline(mode_number)						# mode - on/off
    session.expect("Enter 'YES' to continue or <ENTER> to cancel :")
    session.sendline('YES')							# YES - to confirm (ENTER to abort)
    session.expect('Press <ENTER> to continue...')
    session.sendline("\r")
    session.sendline('\x1b')							# ESC (back to Control)
    session.expect('>')
    session.sendline('\x1b')							# ESC (bak to device - outlet index)
    log(f"{C.GREEN}[PDU]{C.RESET} Outlet #{outlet} turned {mode_color}{mode}{C.RESET}.")

    return True

  except (pexpect.EOF, pexpect.TIMEOUT) as e:
    log(f"{C.RED}[PDU]{C.RESET} Control sequence error: {e}")
    return False

  except ConnectionError:
    log(f"{C.RED}[PDU]{C.RESET} Telnet connection to PDU failed, exiting.")
    return False

  finally:
    if session is not None:
      session.close()
