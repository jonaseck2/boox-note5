# Runs as root at every boot (late_start service). Re-asserts that the adb shell (uid 2000) has root.
# Security: any adb client authorised on this tablet gets root. Remove the module to revoke.
magisk --sqlite "REPLACE INTO settings (key,value) VALUES('root_access',3)"
magisk --sqlite "REPLACE INTO policies (uid,policy,until,logging,notification) VALUES(2000,2,0,1,0)"

