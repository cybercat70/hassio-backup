#!/usr/bin/env python3
'''Unattended bare-metal backup orchestrator for a Home Assistant host.'''

import sys
import os
import time
import configparser
from shutil import which
from datetime import datetime
from icmplib import ping
import unifi
import ipxe
import ssh
import pducontrol
from diag import log
from vault import get_vault_credentials
from colorprint import C


def check_interface_state(ip, stage, probe_count):
  '''Pinsg a host and report whether it is in the expected up/down state.

  Parameters
  ----------
  ip : str
    IP address to probe with ICMP echo requests.
  stage : str
    Current stage name. For "Clonezilla-finish" the logic is inverted
    (success means the host is *down*).
    For any other stage success means the host is *up*.
  probe_count : int
    Number of ICMP echo probes to send.

  Returns
  -------
  bool
    "True" when the host is in the state expected for "stage".
  '''

  result = ping (
    ip,
    count = probe_count,
    timeout = 2,
    privileged = False
  )

  if stage == "Clonezilla-finish":
    return not result.is_alive		# Waiting for the HASSIO iface to be down when backup finished
  else:
    return result.is_alive


def stage_waiting(stage, iface_state, ip, probe_count, timeout):
  '''Polls an interface until it reaches a target state or times out.

  Parameters
  ----------
  stage : str
    Stage name, used for logging and passed through to :func:"check_interface_state".
  iface_state : str
    Human-readable target state, "UP" or "DOWN" (affects logging color only).
  ip : str
    IP address of the interface to monitor.
  probe_count : int
    Number of ICMP echo probes to send.
  timeout : int
    Maximum time to wait, in seconds.

  Returns
  -------
  str
    "success" if the target state was reached, or "timeout" if the timeout elapsed first.
  '''

  stage_start = time.monotonic()
  log(f"{C.GREEN}[{stage}]{C.RESET} Waiting for {ip} to be {iface_state} (timeout = {timeout} sec)...")

  if iface_state == "UP":
    mode_color = C.GREEN
  else:
    mode_color = C.RED

  while True:
    if check_interface_state(ip, stage, probe_count):
      print()
      log(f"{C.GREEN}[{stage}]{C.RESET} Interface {ip} is {mode_color}{iface_state}{C.RESET}.")
      return("success")

    if time.monotonic() - stage_start >= timeout:
      print()
      log(f"{C.RED}[{stage}]{C.RESET} Timeout while waiting for {ip} interface to be {iface_state}.")
      return("timeout")


    elapsed = time.monotonic() - stage_start
    sleep_time = max(1, 10 - (elapsed % 10))
    time.sleep(sleep_time)
    print(f"\r{C.GREEN}[{stage}]{C.RESET} Waiting for {ip} to be {iface_state}: elapsed {int(elapsed)} sec.", end="")


def safety_delay(delay, msg):
  '''Sleeps for a fixed period while printing a live countdown.

  Parameters
  ----------
  delay : int
    Total delay in seconds (counted down in 5-second steps).
  msg : str
    Message prefix printed before the remaining-seconds counter.

  Returns
  -------
  None
  '''

  sdelay = delay
  while sdelay > 0:
    print(f"\r{msg} {sdelay} sec.", end="")
    sdelay -= 5
    time.sleep(5)
  print()


def main():
  '''Runs the full unattended bare-metal backup workflow.

  Parameters
  ----------
  None
    Configuration is read from "backup.cfg" and secrets from Vault.

  Returns
  -------
  None
    The function never returns normally, it calls "sys.exit(0)" on
    success and "sys.exit(1)' on any fatal error.
    Orchestrates: iPXE default fixup, stopping the HA container,
    rebooting the host, moving the switch port to the backup VLAN,
    waiting for Clonezilla to run, power-cycling the PDU outlet,
    restoring the operational VLAN, and waiting for Home Assistant to come back online.
  '''

  # Check if SNMP package installed
  if which("snmpset") is None:
    print(f"{C.RED}[Fatal]{C.RESET} SNMP package not installed, exiting.")
    sys.exit(1)

  # Check if Vault is accessible and .env is correct - if something wrong, get_vault_credentials will fail and exit.
  get_vault_credentials("vault")

  # Read the .cfg file and validate it
  if not os.path.exists("backup.cfg"):
    print(f"{C.RED}[Fatal]{C.RESET} File backup.cfg not found, exiting.")
    sys.exit(1)

  config = configparser.ConfigParser()
  config.read('backup.cfg')

  try:
    PDU_OUTLET = config.getint('pdu', 'PDU_OUTLET')
    SWITCHPORT = config.getint('network', 'SWITCHPORT')
    BACKUP_IP = config.get('network', 'BACKUP_IP')
    WORKING_IP = config.get('network', 'WORKING_IP')
    PROFILE_PREFIX = config.get('network', 'PROFILE_PREFIX')
    BOOT_IPXE_FILE = config.get('ipxe', 'BOOT_IPXE_FILE')
    BOOT_IPXE_BACKUP = config.get('ipxe', 'BOOT_IPXE_BACKUP')
    DHCP_DELAY = config.getint('timeouts', 'DHCP')
    CZ_START = config.getint('timeouts', 'CZ_START')
    CZ_FINISH = config.getint('timeouts', 'CZ_FINISH')
    PDU_OFF_DELAY = config.getint('timeouts', 'PDU_OFF_DELAY')
  except (configparser.NoSectionError, configparser.NoOptionError) as e:
    print(f"{C.RED}[Fatal]{C.RESET} Config error: {e}")
    sys.exit(1)


  # Clear the logfile on start
  with open("backup.log", "w") as backup_log:
    timestamp = datetime.now().strftime("%m-%d-%Y %H:%M:%S")
    print(f"[{timestamp}] HASSIO backup started.", file=backup_log)


  # Check of iPXE menudefault is "hassiobatch"
  ipxe.check_boot_ipxe(BOOT_IPXE_FILE, BOOT_IPXE_BACKUP)


  # Stop HASSIO Docker container
  hassio_docker_id = ssh.check_hassio_container()
  old_id = hassio_docker_id

  while hassio_docker_id:
    ssh.stop_hassio_core(hassio_docker_id)
    # Check if the container fully stopped
    hassio_docker_id = ssh.check_hassio_container()

  log(f"{C.GREEN}[Docker]{C.RESET} Container ID {old_id} stopped.")


  # Initiate HASSIO OS reboot
  log(f"{C.GREEN}[Reboot]{C.RESET}")
#  input("Press Enter for HASSIO reboot.")
  ssh.hassio_reboot()
  time.sleep(5)


  # Changing VLAN7 -> VLAN1 on the UniFi switchport (module "unifi.py")
  vlan_operation_result = unifi.set_port_vlan(PROFILE_PREFIX, SWITCHPORT, 1)


  # Wait DHCP_DELAY (backup.cfg) seconds - a safety delay because DHCP + Clonezilla manage backup IP back and forth
  safety_delay(DHCP_DELAY, f"{C.GREEN}[DHCP]{C.RESET} Taking a delay for DHCP + Clonezilla:")


  # Interfaces waiting stages (backup IP up -> clonezilla works -> backup IP down)
  stages = [
    {
      "stage": "Clonezilla-start",	# Waiting for 10.11.1.4 to be UP (Clonezilla started)
      "ip": BACKUP_IP,
      "ifstate": "UP",
      "probe_count": 3,
      "timeout": CZ_START
    },
    {
      "stage": "Clonezilla-finish",	# Waiting for 10.11.1.4 to be DOWN (Clonezilla finished)
      "ip": BACKUP_IP,
      "ifstate": "DOWN",
      "probe_count": 8,
      "timeout": CZ_FINISH
    }
  ]

  for stage in stages:
    stage_result = stage_waiting(
      stage["stage"],
      stage["ifstate"],
      stage["ip"],
      stage["probe_count"],
      stage["timeout"]
    )

    if stage_result != "success":
      log(f"{C.RED}[{stage["stage"]}]{C.RESET} Backup process failed with {C.RED}{stage_result.upper()}{C.RESET}, exiting.")

      # Restore boot.ipxe from backup
      ipxe.revert_boot_ipxe(BOOT_IPXE_FILE, BOOT_IPXE_BACKUP)
      sys.exit(1)


  # Turning HASSIO PDU outlet off
  safety_delay(PDU_OFF_DELAY, f"{C.GREEN}[PDU]{C.RESET} HASSIO box will be powered off in")
  pdu_reply = pducontrol.outlets_management(PDU_OUTLET, "off")

  if "immediateOff(2)" not in pdu_reply[0]:
    log(f"{C.RED}[PDU]{C.RESET} Backup process failed during turning HASSIO box off, please check manually.")
    # Restore boot.ipxe from backup
    ipxe.revert_boot_ipxe(BOOT_IPXE_FILE, BOOT_IPXE_BACKUP)
    sys.exit(1)


  # Changing VLAN1 -> VLAN7 on the UniFi switchport
  vlan_operation_result = unifi.set_port_vlan(PROFILE_PREFIX, SWITCHPORT, 7)
  time.sleep(5)


  # Turning HASSIO PDU outlet on
  log(f"{C.GREEN}[PDU]{C.RESET} Powering on HASSIO box.")
  pdu_reply = pducontrol.outlets_management(PDU_OUTLET, "on")

  if "immediateOn(1)" not in pdu_reply[0]:
    log(f"{C.RED}[PDU]{C.RESET} Backup process failed during turning HASSIO box on, please check manually.")
    # Restore boot.ipxe from backup
    ipxe.revert_boot_ipxe(BOOT_IPXE_FILE, BOOT_IPXE_BACKUP)
    sys.exit(1)


  # Waiting for HASSIO to boot
  stage_result = stage_waiting("Reboot", "UP", WORKING_IP, 5, 240)
  if stage_result != "success":
    log(f"{C.RED}[BOOT]{C.RESET} HASSIO boot failed, exiting.")
    log(f"{C.RED}[BOOT]{C.RESET} Please check the device manually.")

    # Restore boot.ipxe from backup
    ipxe.revert_boot_ipxe(BOOT_IPXE_FILE, BOOT_IPXE_BACKUP)

    sys.exit(1)


  # Check if HASSIO container started
  log(f"{C.GREEN}[Docker]{C.RESET} Waiting for HASSIO container start...")
  hassio_docker_id = ""
  counter = 1
  while hassio_docker_id == "":
    hassio_docker_id = ssh.check_hassio_container()
    print(f"\r{C.GREEN}[Docker]{C.RESET} Waiting for HASSIO container start: elapsed {counter} sec.")
    time.sleep(2)
    counter += 2

  log(f"{C.GREEN}[Docker]{C.RESET} Container ID {C.GREEN}{hassio_docker_id}{C.RESET} started.")


  # Restore boot.ipxe from backup
  ipxe.revert_boot_ipxe(BOOT_IPXE_FILE, BOOT_IPXE_BACKUP)


  # Verify the backup integrity (?)
  pass


  log("HASSIO backup finished.")
  sys.exit(0)


if __name__ == "__main__":
  main()
