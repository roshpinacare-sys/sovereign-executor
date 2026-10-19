#!/usr/bin/env python3
"""fleet_actions_guard — the hourly switch-guard (wave-19.8).

FORENSICS (2026-10-18): 18 repo-level Actions switches were found disabled
(wave-18 had lifted all 24; post-enable census was 0). Evidence: all workflow-
level states stayed active (repo-toggle only), a fleet agent's dispatches at
16:31 stuck-queued (cannot start while the switch is off), org audit-log 404
to the fleet PAT (actor unprovable from the API plane). GitHub does NOT
auto-flip repo switches for billing (it blocks run START instead) and the
scheduled-workflow auto-disable needs 60 days of inactivity — both ruled out.

OWNER ORDER (verbatim, trace 1a1512554a26f66d): «להחזיר לבדוק למה כובו ולתקן
ולדחוף שהכל יעבוד כמו שצריך לא לכבות לפתור בעיות ... תמשיך ודחוף» — recorded
in state/fleet-actions-guard-approval.json. ROOT FIX: the hourly beat verifies
the approved switches and re-arms any found OFF again — the fleet self-heals
within the hour instead of silently dying.

Scope discipline (deliberate): ONLY the approved set is re-armed — the 18
repos of wave-19.8 (saos-dex by name + 17 private pseudonyms p-<sha256[:7]>).
A NEW disable outside the set is measured and reported ('out-of-scope'),
never auto-re-armed — a future owner decision to switch something OFF must
not be fought by a bot. Laws: GET-verify after every PUT (truth law);
pseudonymous receipts (privacy law); fail-closed with clean() (leak law);
this script touches ONLY actions/permissions (no workflows, no secrets,
no vault — standing prohibitions untouched).

WATCHER-PULSE (wave-19.14): who watches the watchers — a read-only pulse of
the two dwell-chain keepalive lanes (runner-kit + beacon) appended to the
receipt each pass. Pure GETs, no dispatches, no touches; the verdict does
NOT change this script's switch-focused exit code — it is data for the beat
receipt (wiring it into a red state is a separate, deliberate decision).
"""
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

ORG = 'roshpinacare-sys'
# The two dwell-chain watchers (waves 19.11/19.13). Coverage semantics: a
# live chain always has a run created <=31min ago (its dwell window), so any
# lane whose newest run is >WATCHER_STALE_MIN old is chain-dead AND
# lottery-silent — exactly the hole this pulse exists to see.
WATCHERS = [
    {'lane': 'runner-kit/beat-keepalive', 'repo': 'sovereign-runner-kit', 'wf': 'keepalive.yml'},
    {'lane': 'beacon/beat-keepalive', 'repo': 'sovereign-beacon', 'wf': 'keepalive.yml'},
]
WATCHER_STALE_MIN = 40
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPROVAL = os.path.join(ROOT, 'state', 'fleet-actions-guard-approval.json')
RECEIPT = os.path.join(ROOT, 'receipts', 'fleet-beat', 'actions-guard.json')
PAT = os.environ.get('SOVEREIGN_PAT', '')


def clean(s):
    s = str(s)
    if PAT:
        s = s.replace(PAT, '***REDACTED***')
    return s


def pseudonym(name):
    return 'p-' + hashlib.sha256(name.encode()).hexdigest()[:7]


def api(url, method='GET', body=None):
    req = urllib.request.Request(url, method=method)
    req.add_header('Authorization', 'Basic ' + __import__('base64').b64encode(
        ('x-access-token:' + PAT).encode()).decode())
    req.add_header('Accept', 'application/vnd.github+json')
    data = json.dumps(body).encode() if body is not None else None
    if data:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, {'error': clean(e.read().decode(errors='replace'))[:200]}
    except Exception as e:
        return 0, {'error': clean(e)[:200]}


def list_repos():
    names = []
    for page in (1, 2, 3):
        st, d = api('https://api.github.com/user/repos?per_page=100&type=owner&page=%d' % page)
        if st != 200:
            break
        batch = [r['name'] for r in (d or [])]
        names.extend(batch)
        if len(batch) < 100:
            break
    if not names:
        st, d = api('https://api.github.com/users/%s/repos?per_page=100' % ORG)
        if st == 200:
            names = [r['name'] for r in (d or [])]
    return sorted(set(names))


def watcher_pulse():
    """Read-only pulse of the two keepalive lanes (wave-19.14). Pure GETs;
    any API error is recorded as 'unreachable', never raised — the pulse
    must not break the switch-guard's own work."""
    now = datetime.now(timezone.utc)
    out = []
    for w in WATCHERS:
        st, d = api('https://api.github.com/repos/%s/%s/actions/workflows/%s/runs?per_page=1'
                    % (ORG, w['repo'], w['wf']))
        if st != 200:
            out.append({'lane': w['lane'], 'state': 'unreachable-http-%s' % st})
            continue
        runs = (d or {}).get('workflow_runs') or []
        if not runs:
            out.append({'lane': w['lane'], 'state': 'no-runs-ever'})
            continue
        r = runs[0]
        at = datetime.fromisoformat(r['created_at'].replace('Z', '+00:00'))
        out.append({'lane': w['lane'], 'run': r.get('run_number'),
                    'status': r.get('status'), 'conclusion': r.get('conclusion'),
                    'ageMin': round((now - at).total_seconds() / 60.0)})
    covered = [w for w in out
               if isinstance(w.get('ageMin'), int) and w['ageMin'] <= WATCHER_STALE_MIN]
    verdict = 'coverage-ok' if covered else 'coverage-stale'
    return {'verdict': verdict, 'thresholdMin': WATCHER_STALE_MIN, 'watchers': out}


def main():
    if not PAT:
        print('actions-guard: FAIL-CLOSED — no SOVEREIGN_PAT; cannot verify or re-arm switches')
        return 1
    try:
        approval = json.load(open(APPROVAL))
    except Exception as e:
        print(clean('actions-guard: FAIL-CLOSED — approval unreadable: %s' % e))
        return 1
    approved_public = set(approval['approvedSet']['publicNamed'])
    approved_private = set(approval['approvedSet']['privatePseudonyms'])

    repos = list_repos()
    if not repos:
        print('actions-guard: FAIL-CLOSED — no repos visible; refusing to act blind')
        return 1
    results, re_armed, verified, out_of_scope, failed, already_on = [], 0, 0, 0, 0, 0
    for name in repos:
        alias = name if not name.startswith('p-') else name
        st, perm = api('https://api.github.com/repos/%s/%s/actions/permissions' % (ORG, name))
        if st != 200:
            results.append({'repo': pseudonym(name), 'state': 'check-http-%s' % st})
            failed += 1
            continue
        if bool(perm.get('enabled', True)):
            already_on += 1
            continue
        pub = name in approved_public
        priv = pseudonym(name) in approved_private
        if not (pub or priv):
            out_of_scope += 1
            results.append({'repo': pseudonym(name), 'state': 'out-of-scope-reported',
                            'note': 'found OFF, not in the approved set — measured, reported, NOT touched'})
            continue
        st2, _ = api('https://api.github.com/repos/%s/%s/actions/permissions' % (ORG, name),
                     method='PUT', body={'enabled': True, 'allowed_actions': 'all'})
        # truth law with patience: the GET right after a PUT can read stale
        # propagation state (measured 2026-10-18: PUT 204, immediate GET still false,
        # state actually landed seconds later). Retry the verify before declaring failure.
        ok, st3, after = False, None, {}
        for attempt in range(3):
            st3, after = api('https://api.github.com/repos/%s/%s/actions/permissions' % (ORG, name))
            ok = st3 == 200 and bool(after.get('enabled', False))
            if ok:
                break
            time.sleep(5)
        results.append({'repo': pseudonym(name), 'state': 're-armed' if ok else 'FAILED',
                        'put': st2, 'get': st3})
        if ok:
            re_armed += 1
            verified += 1
        else:
            failed += 1
    pulse = watcher_pulse()
    receipt = {
        'what': 'hourly actions-guard — verify approved repo-level switches, re-arm any found OFF (owner trace 1a1512554a26f66d)',
        'executedAt': datetime.now(timezone.utc).isoformat(),
        'summary': {'reposScanned': len(repos), 'alreadyOn': already_on,
                    'reArmed': re_armed, 'verified': verified,
                    'outOfScopeReported': out_of_scope, 'failed': failed},
        'results': results,
        'watcherPulse': pulse,
    }
    os.makedirs(os.path.dirname(RECEIPT), exist_ok=True)
    json.dump(receipt, open(RECEIPT, 'w'), ensure_ascii=False, indent=2)
    print('actions-guard: scanned=%d alreadyOn=%d reArmed=%d verified=%d outOfScope=%d failed=%d watcherPulse=%s'
          % (len(repos), already_on, re_armed, verified, out_of_scope, failed, pulse['verdict']))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
