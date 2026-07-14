# TODO

## Done

- [x] Replace token-based Vault auth with AppRole (or TLS cert auth, which would
      be even better given the lab PKI infrastructure).

## Tentative

- [ ] Replace Telnet-based PDU management mech by SNMP v3.
      A quick-and-dirty testing script confirmed SNMP v3 can be used 
      but looks like it's even slower than Telnet.
      The benefits of encryption are also questionable. 
      While SNMP credentials are encrypted using MD5 (a severely outdated and vulnerable protocol),
      the SNMP packets themselves are not encrypted. 
      And if you enable authPriv ("encrypt everything") in this outdated PDU, 
      management operations become incredibly slow.

## Planned

- [ ] Verify backup integrity after Clonezilla completes.
