# Runs as root at install time (sourced by Magisk's module installer).
magisk --sqlite "REPLACE INTO settings (key,value) VALUES('root_access',3)"
magisk --sqlite "REPLACE INTO policies (uid,policy,until,logging,notification) VALUES(2000,2,0,1,0)"
ui_print "- shell (uid 2000) granted root; root_access=apps+adb"
