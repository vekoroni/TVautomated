"""Plan the dated one-off PostClose release. Only --execute starts the existing FULL runner."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from contracts.macro_postclose_exception import authorization


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    grant = authorization(ROOT)
    if not grant:
        print('STOPPED: no current dated PostClose authorization')
        return 7
    command = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
               str(ROOT/'Run-MacroInputs.ps1'), '-Session', 'PostClose', '-Force']
    print(json.dumps({'authorization': grant, 'execute': args.execute, 'command': command,
                      'funding_verified': False, 'pending_exports_resolved': False}))
    if not args.execute:
        return 0
    env = os.environ.copy()
    env.pop('AVSH_FULL_BUILD_ID', None)
    env.update(AVSH_BUILD_REASON='POST_CLOSE', AVSH_BUILD_FINGERPRINT=grant['fingerprint'],
               AVSH_BUILD_OWNER='USER_AUTHORIZED_ONE_OFF')
    return subprocess.run(command, cwd=ROOT, env=env,
        **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {})).returncode


if __name__ == '__main__':
    raise SystemExit(main())
