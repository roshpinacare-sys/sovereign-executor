#!/usr/bin/env python3
"""interval_gate — the beat's metronome (wave-19.6).

MEASURED (2026-10-18): GitHub dropped 17 of 18 scheduled slots across three
repos (executor 1/7 then 6/6, then 0/5 on the */15 density). A slot that only
skips when fresh is hostage to the scheduler: if every scheduled slot is
dropped, nothing ever beats. The gate therefore SLEEPS TO DUE: a fresh slot
does not exit — it sleeps until the last beat is >= GATE_THRESHOLD_MIN
(default 55) minutes old, re-checks the receipt (another plane may have
beaten meanwhile — then it skips honestly, no double beat), and runs.

Design notes:
- The beat perpetuates itself elsewhere (scripts/chain_link.py): every
  successful beat dispatches the next link, so the cadence lives in this
  gate, not in GitHub's scheduler. Schedule + keep-alive net remain as
  backup trigger planes.
- Fail-open to real work on an unreadable receipt — never fail-open to
  silence. A slot that cannot read the receipt runs the beat.
- Public repo => minutes are free; sleeping a runner is honest and cheap.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone

RECEIPT = os.path.join('receipts', 'fleet-beat', 'last.json')


def last_age_min():
    """Minutes since the last beat, or None if the receipt is unreadable."""
    try:
        d = json.load(open(RECEIPT))
        at = datetime.fromisoformat(str(d['at']).replace('Z', '+00:00'))
        return (datetime.now(timezone.utc) - at).total_seconds() / 60.0
    except Exception:
        return None


def main():
    try:
        threshold = float(os.environ.get('GATE_THRESHOLD_MIN', '55'))
    except ValueError:
        threshold = 55.0
    age = last_age_min()
    if age is None:
        run = 'true'
        print('interval gate: unreadable/absent receipt — running the beat (fail-open to real work, never fail-open to silence)')
    elif age < threshold:
        wait = threshold - age
        print('interval gate: last beat %.0fmin ago — slot sleeps %.0fmin to due (the metronome; free minutes on a public repo)' % (age, wait))
        time.sleep(wait * 60)
        age2 = last_age_min()
        if age2 is None:
            run = 'true'
            print('interval gate: after sleep the receipt is unreadable — running the beat')
        elif age2 < threshold:
            run = 'false'
            print('interval gate: another plane beat %dmin ago while this slot slept — skip honestly, no double beat' % int(age2))
        else:
            run = 'true'
            print('interval gate: due (%dmin since the last beat) — running the beat' % int(age2))
    else:
        run = 'true'
        print('interval gate: last beat %.0fmin ago — due, running the beat' % age)
    print('gate verdict: %s' % run)
    out = os.environ.get('GITHUB_OUTPUT')
    if out:
        with open(out, 'a') as f:
            f.write('run=%s\n' % run)
    return 0


if __name__ == '__main__':
    sys.exit(main())
