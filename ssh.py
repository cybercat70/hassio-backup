#!/usr/bin/env python3
'''Home Assistant host control over SSH (container stop/status, host reboot).'''

import paramiko
from diag import log
from vault import get_vault_credentials
from colorprint import C


def ssh_session():
  '''
  Opens an authenticated SSH session to the Home Assistant host.

  Parameters
  ----------
  None
    Credentials are fetched from Vault via get_vault_credentials("ssh").

  Returns
  -------
  paramiko.SSHClient
    A connected SSH client. The caller is responsible for closing it.

  Raises
  ------
  paramiko.SSHException
    If the SSH connection cannot be established.
  '''

  creds = get_vault_credentials("ssh")

  ssh = paramiko.SSHClient()

  try:
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname=creds['hassio_host'], username=creds['hassio_username'], password=creds['hassio_password'])
    return ssh
  except Exception:
    ssh.close()
    raise


def check_hassio_container():
  '''Returns the Docker container ID of the running Home Assistant core.

  Parameters
  ----------
  None

  Returns
  -------
  str
    The Home Assistant container ID, or an empty string if the container is not currently running.
  '''

  ssh = ssh_session()

  try:
    stdin, stdout, stderr = ssh.exec_command("docker ps --format \"{{.ID}} {{.Names}}\" | grep homeassistant | awk '{print $1}'")
    hassio_docker_id = stdout.read().decode()
    return hassio_docker_id.strip()
  finally:
    ssh.close()


def stop_hassio_core(hassio_docker_id):
  '''Requests a graceful stop of the Home Assistant core container.

  Parameters
  ----------
  hassio_docker_id : str
    The container ID being stopped (used only for logging).

  Returns
  -------
  None
    Runs "ha core stop" on the host over SSH.
  '''

  log(f"{C.GREEN}[Docker]{C.RESET} Container ID {hassio_docker_id} is stopping...")
  ssh = ssh_session()

  try:
    stdin, stdout, stderr = ssh.exec_command("ha core stop")
    stop_result = stdout.read().decode()
  finally:
    ssh.close()


def hassio_reboot():
  '''Reboots the Home Assistant host by running "init 6" over SSH.

  Parameters
  ----------
  None

  Returns
  -------
  None
  '''

  ssh = ssh_session()

  try:
    stdin, stdout, stderr = ssh.exec_command("init 6")
  finally:
    ssh.close()
