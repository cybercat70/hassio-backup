#!/usr/bin/env python3
'''Retrieves credentials from HashiCorp Vault using AppRole authentication.'''

import sys
import os
import hvac
from dotenv import load_dotenv
from colorprint import C


def get_vault_credentials(device):
  '''
  Returns the secrets for the requested device from Vault.

  Parameters
  ----------
  device : str
    Selects which subset of secrets to return ("pdu", "ssh", "unifi") 
    or acts as a Vault health check ("vault").

  Returns
  -------
  A dict with named credentials ("pdu", "ssh", "unifi")
    or None ("vault")

  Any Vault or .env file problem terminates the process.
  '''

  load_dotenv(override=True)

  conf_vars = {}

  for var in ("VAULT_ADDR", "CA_CERT", "VAULT_ROLE", "ID"):
    var_value = os.getenv(var)

    if not var_value:
      print (f"{C.RED}[Fatal]{C.RESET} {var} not set in .env, exiting.")
      sys.exit(1)

    conf_vars[var] = var_value

  client = hvac.Client(url=conf_vars["VAULT_ADDR"], verify=conf_vars["CA_CERT"])

  if client.sys.is_sealed():
    print(f"{C.RED}[Fatal]{C.RESET} Vault is sealed, unseal it first.")
    sys.exit(1)

  # AppRole auth
  try:
    client.auth.approle.login(role_id = conf_vars["VAULT_ROLE"], secret_id = conf_vars["ID"])

  except hvac.exceptions.InvalidRequest:
    print(f"{C.RED}[Fatal]{C.RESET} Invalid or expired Secret ID!")
    sys.exit(1)

  except hvac.exceptions.Forbidden:
    print(f"{C.RED}[Fatal]{C.RESET} Role is not allowed to authenticate.")
    sys.exit(1)

  except hvac.exceptions.VaultDown:
    print(f"{C.RED}[Fatal]{C.RESET} Vault is unavailable.")
    sys.exit(1)

  # Check if we authenticated
  if not client.is_authenticated():
    print (f"{C.RED}[Fatal]{C.RESET} Vault authentication failed.")
    sys.exit(1)

  # For KV v2 mount_point is mandatory
  secret = client.secrets.kv.v2.read_secret_version(path="secrets", mount_point="hassio", raise_on_deleted_version=True)
  data = secret["data"]["data"]

  match device:
    case "pdu":
      return {
        "pdu_host": data["pdu_host"],
        "snmp_user": data["snmp_user"],
        "snmp_password": data["snmp_password"],
      }

    case "ssh":
      return {
        "hassio_host": data["hassio_host"],
        "hassio_username": data["hassio_username"],
        "hassio_password": data["hassio_password"],
      }

    case "unifi":
      return {
        "unifi_url": data["unifi_url"],
        "unifi_username": data["unifi_username"],
        "unifi_password": data["unifi_password"],
        "ca_cert": conf_vars["CA_CERT"],
      }

    # Special case: get_vault_credentials will fail if Vault is inaccessible or .env is incorrect.
    case "vault":
      return
