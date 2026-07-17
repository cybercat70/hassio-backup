# hassio-backup

Unattended, network-booted bare-metal backup orchestrator for a Home Assistant host.

`hassio-backup` automates a full disk image backup of a headless Home Assistant
box that has **no out-of-band management** (no IPMI/Redfish). It coordinates
Home Assistant, a UniFi switch, an APC PDU, an iPXE/Clonezilla network-boot
environment, and HashiCorp Vault to perform the whole cycle without human
intervention.

---

## Where it works

The script-based backup setup works with a bare-metal box (Intel NUC5i3RYH) running Home Assistant. 

The purpose of the setup is to back up the **entire contents of the box's storage** in unattended mode: 
the box is located in a very hard-to-reach place and does not have standard server remote management features, 
such as IPMI or RedFish.

Clonezilla 3.3+ is used as the main backup tool, booted over the network via DHCP + TFTD + iPXE.

The network is provided by a Ubiquity USW Pro Max 16 switch, and power is supplied to the box 
via a PoE+ injector connected to an APC AP7902 PDU. 

The home infra includes a HashiCorp Vault instance, an ISC DHCP server, and NGINX, which handles 
HTTPS connections to the Vault instance and to the UniFi controller, as well as HTTP requests for iPXE. 

The PDU is managed via SNMPv3 protocol.

## How it works

The backup setup works as follows, step by step:

1. On the host running Home Assistant, the "homeassistant" Docker container is stopped.

2. The host is rebooted.

3. During the reboot, the network port profile of the UniFi switch changes from "HASSIO-VLANx" 
   to "HASSIO-VLANy", where x is the Home Assistant's operational VLAN, and y is the VLAN 
   in which a DHCP server runs, assigning the host a temporary IP address for working with iPXE and Clonezilla 
   (the HASSIO-VLANx and HASSIO-VLANy profiles should be prepared in advance using standard UniFi management tools).
   Profile prefix name ("HASSIO-VLAN") is not hardcoded and can be configured, please refer to backup.cfg.example.

4. The host receives a temporary backup IP (see backup.cfg.example), Clonezilla is downloaded 
   from an iPXE-capable HTTP server and begins the backup according to the script specified in boot.ipxe.

5. Upon completion of the backup process, when Clonezilla has shut down the host 
   (and the temporary IP is no longer pingable), the host is powered off via PDU outlet control.

6. The Home Assistant network port profile is changed back to "HASSIO-VLANx".

7. The host is powered on via the PDU.

8. The tools verify that the host is once again operating on its regular IP address 
   and that the Home Assistant Docker container has started.


## Arcitecture

```
                         backup.py (orchestrator)
                                  |
   +-----------+-----------+------+------+-----------+-----------+
   |           |           |             |           |           |
 vault.py    ssh.py    unifi.py    pducontrol.py   ipxe.py    icmplib
   |           |           |             |           |         (ping)
  Vault    HA host     UniFi ctrl     APC PDU     boot.ipxe
(AppRole)   (SSH)     (HTTPS/REST)   (SNMPv3)    (local file)
```

Shared helpers: [`diag.py`](diag.py) (timestamped file + console logging) and
[`colorprint.py`](colorprint.py) (ANSI color constants).


## Requirements

- Python 3.12+
- The Python packages in [`requirements.txt`](requirements.txt)
- "snmp" (Debian/Ubuntu) or "net-snmp-utils" (RHEL/Centos) package installed.
- A reachable HashiCorp Vault, UniFi controller, APC PDU, and iPXE/Clonezilla boot server.


## Installation

```bash
git clone https://github.com/cybercat70/hassio-backup.git
cd hassio-backup

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp backup.cfg.example backup.cfg   # then edit
cp .env.example .env               # then edit, chmod 600
```


## Configuration

### Environment (`.env`)

A .env must exist in the working directory. Start from [`.env.example`](.env.example):

```dotenv
VAULT_ADDR=https://vault.example
CA_CERT=/path/to/cert/example-ca.crt
VAULT_ROLE=aaaabbbb-...
ID=ccccdddd-...
```

Refer to HashiCorp Vault docs for AppRole configuration details.

> **The `.env` file must be `chmod 600`.** 
> It is already listed in `.gitignore` and must never be committed.

### Vault secrets

Vault must expose the KV v2 path `hassio/secrets` (API path `/v1/hassio/data/secrets`) 
with the following keys:

```
Key              Example
-------------------------------------------
hassio_host 	 homeassistant.example
hassio_username  administrator
hassio_password  very_secure_password
snmp_user        snmpadmin
snmp_password	 snmp_very_secure_password
pdu_host         pdu01.example
unifi_url        https://unifi.example
unifi_username   unifiadmin
unifi_password   unifi_very_secure_password
```

### Vault AppRole policy

Vault AppRole should be created for the next access policy:

```hcl
path "hassio/*" {
  capabilities = ["read", "list"]
}
```

### iPXE / Clonezilla boot server

HTTP server http://ipxe.example (configurable, please refer to [`boot.ipxe.example`](boot.ipxe.example)) 
should exist in the infrastructure and be configured to serve Clonezilla 3.3+ network boot files:

```console
$ ls -1 /srv/www/ipxe/clonezilla33
filesystem.squashfs
initrd.img
vmlinuz
```

Adjust the Clonezilla section of `boot.ipxe` for your backup destination — see
[`boot.ipxe.example`](boot.ipxe.example) and the Clonezilla docs:

```text
ocs_repository="smb://BACKUP_HOST;backup_user:backup_password@backup_host.example/backup_path/"
```

### DHCP reservation

Reserve the temporary backup IP on the backup VLAN, for example (isc-dhcp-server):

```text
# ----------------- VLANy -----------------
# Dynamic assignment of temp HASSIO IP
# required for backup unattended operations
host hassio-backup-temp
{
    hardware ethernet AA:BB:CC:DD:EE:FF;
    fixed-address 192.168.1.4;
    next-server 192.168.1.100;
    filename "undionly.kpxe";
}
```

### AP7902 SNMP v3 configuration specifics

- Login to the Web management GUI of AP7902.
- Navigate to Administration -> Network -> SMNPv3 -> access
- Enable SMNPv3:

<img src="images/snmp1.jpg" width="600">

- Navigate to Administration -> Network -> SMNPv3 -> user profiles
  and choose a user profile:

<img src="images/snmp2.jpg" width="600">

- Set the username, authentication passphrase, choose MD5 as auth protocol (secirity level "authNoPriv").

  I **do not** recommend setting a privacy protocol or privacy passphrase.
  This enables the highest SNMPv3 security level (authPriv), which uses both authentication and encryption.
  On the AP7902, however, authPriv causes a severe performance impact because the hardware is simply too old
  and underpowered, even with the latest firmware installed.

<img src="images/snmp3.jpg" width="600">

- Navigate to Administration -> Network -> SMNPv3 -> access control

<img src="images/snmp4.jpg" width="600">

- Ensure that the user is enabled.
- (optional) As an additional security measure, restrict this user
  to the specific IP address or FQDN of the host that will be sending management requests,
  instead of leaving the default value of 0.0.0.0.
- **Reboot the PDU's management interface.** The SNMPv3 settings will not take effect until it has been restarted
  (this does not reset or reboot the device itself).


## Usage

```bash
./backup.py
```

The script runs the full backup cycle end to end and exits with status `0` on success or `1` on failure. 
On any failure it restores the original `boot.ipxe` before exiting.


## Logging

All progress is printed to the console (with color) and mirrored, without ANSI codes, to `backup.log` 
in the working directory. The log file is truncated at the start of each run.
