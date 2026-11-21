"""Prepare the mounted SQLite directory, then launch the service as app."""

import os
import pwd
import sys

if os.geteuid() == 0:
    app = pwd.getpwnam("app")
    os.chown("/data", app.pw_uid, app.pw_gid, follow_symlinks=False)
    os.setgroups([])
    os.setgid(app.pw_gid)
    os.setuid(app.pw_uid)
os.execvp(sys.argv[1], sys.argv[1:])
