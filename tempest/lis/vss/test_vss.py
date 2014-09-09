# import winrm
# import sys

# from winrm import protocol

# hostname = 'TEMPEST-2012R2'
# hostname = 'https://' + hostname + ':5986/wsman';

# s = winrm.Session(hostname, auth=('Administrator', 'Passw0rd'))
# r = s.run_cmd('ipconfig', ['/all'])

file = open('vss_backup.ps1')
script = file.read()
# print rawscript
script = script.format(getvmname='vm1', gethvserver='hostname', gettargetdrive='C')
print script
