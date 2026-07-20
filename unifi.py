#!/usr/bin/env python3
'''UniFi controller REST client for swapping switch port VLAN profiles.'''

import requests
import json
from diag import log
from vault import get_vault_credentials
from colorprint import C


def unifi_auth():
  '''Authenticates against the UniFi controller and return a session.

  Parameters
  ----------
  None
    Credentials are fetched from Vault via get_vault_credentials("unifi").

  Returns
  -------
  tuple(requests.Session, dict)
    A tuple of the logged-in "requests.Session" and the credentials dict
    (containing "unifi_url", "unifi_username", "unifi_password", "ca_cert").

  Raises
  ------
  requests.HTTPError
    If the login request returns a non-success status code.
  '''

  creds = get_vault_credentials("unifi")

  session = requests.Session()
  session.verify = creds['ca_cert']
  unifi_response = session.post(
    f"{creds['unifi_url']}/api/login",
    json={
      "username": creds['unifi_username'],
      "password": creds['unifi_password']
    },
    headers={"Content-Type": "application/json"}
  )
  unifi_response.raise_for_status()

  return session, creds


def get_switch_device_id(session, creds):
  '''Returns the UniFi "_id" of the first switch device (type "usw").

  Parameters
  ----------
  session : requests.Session
    Authenticated UniFi controller session.
  creds : dict
    Credentials dict.

  Returns
  -------
  str or None
    The switch device "_id", or "None" if no switch is found.
  '''

  device = session.get(f"{creds['unifi_url']}/api/s/default/stat/device", timeout=10)
  device.raise_for_status()

  device_json = device.json()

  for json_item in device_json.get("data", []):
    if json_item.get("type") == "usw":  		# Switch only, no APs or anything else!
      return json_item.get("_id")


def get_port_profiles(session, creds):
  '''Returns the list of configured switch port profiles.

  Parameters
  ----------
  session : requests.Session
    Authenticated UniFi controller session.
  creds : dict
    Credentials dict.

  Returns
  -------
  list[dict]
    A list of "{"name": str, "_id": str}" dicts, one per port profile.
  '''

  profiles = session.get(f"{creds['unifi_url']}/api/s/default/rest/portconf", timeout=10)
  profiles.raise_for_status()

  profiles_json = profiles.json()
  return [
    {
      "name": json_item.get("name"),
      "_id": json_item.get("_id")
    }
    for json_item in profiles_json.get("data", [])
  ]


def get_portconf_id(profile_prefix, port_profiles, vlan):
  '''Looks up the port-profile "_id" matching a prefix and VLAN.

  Parameters
  ----------
  profile_prefix : str
    Profile name prefix (e.g. "HASSIO-VLAN") from "backup.cfg".
  port_profiles : list[dict]
    Port profiles as returned by "get_port_profiles".
  vlan : int
    VLAN number appended to "profile_prefix" to form the profile name.

  Returns
  -------
  str
    The "_id" of the matching port profile.

  Raises
  ------
  RuntimeError
    If no profile named "{profile_prefix}{vlan}" exists.
  '''

  # We have just 2 profiles for HASSIO: HASSIO-VLAN1 and HASSIO-VLAN7
  #    (now the prefix is configurable in .cfg).
  # Getting _id parameters for all port profiles.

  profile_name = f"{profile_prefix}{vlan}"

  profile = next(
    (p for p in port_profiles if p.get("name") == profile_name),
    None
  )

  if not profile:
    log(f"{C.RED}[UniFi]{C.RESET} Port profile {C.RED}{profile_name}{C.RESET} not found.")
    raise RuntimeError(f"\t {C.RED}[UniFi]{C.RESET} Port profile {C.RED}{profile_name}{C.RESET} not found.")

  return profile["_id"]


def set_port_vlan(profile_prefix, port_idx, vlan):
  '''Assigns a VLAN port profile to a specific switch port.

  Parameters
  ----------
  profile_prefix : str
    Profile name prefix (e.g. "HASSIO-VLAN") from "backup.cfg".
  port_idx : int
    Index of the switch port to reconfigure.
  vlan : int
    Target VLAN number combined with "profile_prefix" to select the
    port profile to apply.

  Returns
  -------
  bool
    "True" if the port override was updated successfully, 
    "False" if the controller rejected the update (HTTP error).

  Raises
  ------
  RuntimeError
    If the matching port profile or the target port is not found.
  '''

  log(f"{C.GREEN}[UniFi]{C.RESET} Setting VLAN {vlan} on port {port_idx}...")

  session, creds = unifi_auth()

  # Get switch ID
  switch_id = get_switch_device_id(session, creds)

  # Get all Unifi controller data
  url = f"{creds['unifi_url']}/api/s/default/stat/device"
  response = session.get(url, timeout=10)
  response.raise_for_status()
  all_devices = response.json()

  devices = all_devices.get("data", [])

  # We have 4 Ubiquity devices in {devices}, let's found the switch's chapter and get Eth port overrides
  for d in devices:
    if d.get("_id") == switch_id:
      port_overrides = d.get("port_overrides", [])

  # Get port profiles: we can't work directly with VLAN assingnments 
  #   so we just need to replace port profile parameters in port_overrides JSON section.
  port_profiles = get_port_profiles(session, creds)

  portconf_id = get_portconf_id(profile_prefix, port_profiles, vlan)

  port_found = False

  # Rewriting portconf_id for port_idx (HASSIO_SWITCHPORT)
  for p in port_overrides:
    if p.get("port_idx") == port_idx:
      p["portconf_id"] = portconf_id
      p["setting_preference"] = "manual"
      port_found = True
      break

  if not port_found:
    log(f"{C.RED}[UniFi]{C.RESET} Port {C.RED}{port_idx}{C.RESET} not found in port_overrides.")
    raise RuntimeError(f"\t {C.RED}[UniFi]{C.RESET} Port {C.RED}{port_idx}{C.RESET} not found in port_overrides.")

  # Putting new port overrides to the switch
  url = f"{creds['unifi_url']}/api/s/default/rest/device/{switch_id}"
  payload = {
    "port_overrides": port_overrides
  }

  response = session.put(
    url,
    json=payload,
    headers={"Content-Type": "application/json"}
  )

  try:
    response.raise_for_status()
  except requests.HTTPError:
    log(f"{C.RED}[UniFi]{C.RESET} Error while setting VLAN {vlan} on port {port_idx}: {response.text}")
    return False

  log(f"{C.GREEN}[UniFi]{C.RESET} VLAN {vlan} is set on port {port_idx}.")
  return True
