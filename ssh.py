#!/usr/bin/env python3

import paramiko
from diag import log
from vault import get_vault_credentials
from colorprint import C


def ssh_session():
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
  ssh = ssh_session()

  try:
    stdin, stdout, stderr = ssh.exec_command("docker ps --format \"{{.ID}} {{.Names}}\" | grep homeassistant | awk '{print $1}'")
    hassio_docker_id = stdout.read().decode()
    return hassio_docker_id.strip()
  finally:
    ssh.close()


def stop_hassio_core(hassio_docker_id):
  log(f"{C.GREEN}[Docker]{C.RESET} Container ID {hassio_docker_id} is stopping...")
  ssh = ssh_session()

  try:
    stdin, stdout, stderr = ssh.exec_command("ha core stop")
    stop_result = stdout.read().decode()
  finally:
    ssh.close()


''' is_hassio_stopped in not in use anymore '''
def is_hassio_stopped(HASSIO_LOG):
  ssh = ssh_session()

  try:
    log_exists = True
    while log_exists:
      log(f"{C.GREEN}[Docker]{C.RESET} Waiting until HASSIO container stopped...")
      stdin, stdout, stderr = ssh.exec_command(f"[ -f {HASSIO_LOG} ] && echo \"1\" || echo \"0\"")
      log_exists = int(stdout.read().decode())

      if log_exists:
        time.sleep(2)

    log(f"{C.GREEN}[Docker]{C.RESET} HASSIO container stopped.")

  finally:
    ssh.close()


def hassio_reboot():
  ssh = ssh_session()

  try:
    stdin, stdout, stderr = ssh.exec_command("init 6")
  finally:
    ssh.close()
