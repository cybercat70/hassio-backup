#!/usr/bin/env python3
'''APC PDU outlet power control over SNMP v3.'''

import subprocess
from vault import get_vault_credentials


def outlets_management(outlet_id, action):
  '''Powers a single PDU outlet on or off.

  Parameters
  ----------
  outlet_id : int
    Index number of the PDU outlet to control.
  mode : str
    Desired outlet state: "on" or "off".

  Returns
  -------
  list[str]
    Output of "snmpset" command

  Raises
  ------
  ValueError exception
    If input "action" is neither "on" nor "off"
  '''

  commands = {
    "on": "1",
    "off": "2",
  }

  creds = get_vault_credentials("pdu")

  try:
    op_code = commands[action]
  except KeyError:
    raise ValueError("Invalid action")

  snmp_query = [
    "snmpset",
    "-v3",
    "-l", "authNoPriv",
    "-u", creds["snmp_user"],
    "-a", "MD5",
    "-A", creds["snmp_password"],
    creds["pdu_host"],
    f"PowerNet-MIB::rPDUOutletControlOutletCommand.{outlet_id}",
    "i",
    op_code,
  ]

  result = subprocess.run(
    snmp_query,
    capture_output=True,
    text=True,
    check=True,
  )

  return result.stdout.splitlines()
