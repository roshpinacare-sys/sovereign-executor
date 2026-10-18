#!/usr/bin/env python3
"""chain_link — the beat perpetuates itself (wave-19.6).

MEASURED (2026-10-18): GitHub's scheduler dropped 17 of 18 scheduled slots
across three repos in one afternoon. A beat that only triggers from cron is
therefore NOT sovereign continuity. Every SUCCESSFUL fleet-beat dispatches
its own next link; the interval gate (scripts/interval_gate.py) is the
metronome that paces the chain at >=55min. The schedule + the cross-repo
keep-alive net (runner-kit, beacon) remain as independent backup triggers.

Laws:
- chains ONLY after a successful beat (a red run breaks the chain loudly —
  the backup planes keep drawing);
- fail-closed: a failed dispatch exits 1 with a clean() message — the lane
  reddens, evidence lands, never silence;
- LEAK-LAW: the credential never appears in any printed string;
- secret-surface: this script only ever runs from schedule/dispatch lanes.
"""
import base64
import json
import os
import sys
from urllib.request import Request, urlopen

REPO = 'roshpinacare-sys/sovereign-executor'
WORKFLOW = 'fleet-beat.yml'


def clean(s):
    s = str(s)
    pat = os.environ.get('SOVEREIGN_PAT', '')
    if pat:
        s = s.replace(pat, '***REDACTED***')
    return s


def main():
    tok = os.environ.get('SOVEREIGN_PAT', '')
    if not tok:
        print('chain: FAIL-CLOSED — no SOVEREIGN_PAT; the chain dies here, schedule+keepalive planes remain')
        return 1
    req = Request('https://api.github.com/repos/%s/actions/workflows/%s/dispatches' % (REPO, WORKFLOW),
                  method='POST')
    req.add_header('Authorization', 'Basic ' + base64.b64encode(
        ('x-access-token:' + tok).encode()).decode())
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('Content-Type', 'application/json')
    try:
        with urlopen(req, data=json.dumps({'ref': 'main'}).encode(), timeout=30) as r:
            print('chain: dispatched the next link (%s) — the beat continues independent of the scheduler' % r.status)
    except Exception as e:
        print(clean('chain: FAIL-CLOSED — %s (chain dies; schedule+keepalive planes remain)' % e)[-300:])
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
