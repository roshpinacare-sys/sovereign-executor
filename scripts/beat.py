#!/usr/bin/env python3
# fleet-beat sequencer — the executor's task runner (original SAOS engineering).
# Smart separation (owner directive 2026-10-18): PRIVATE content stays private; EXECUTION
# runs on free public minutes. This repo is PUBLIC on purpose: GitHub Actions minutes are
# unlimited-free for public repositories, while private repos hit the org billing wall.
# The beat carries read-only tasks over the private fleet via a short-lived checkout using
# the SOVEREIGN_PAT secret (encrypted at rest, never printed, never committed).
# Secret-surface law: this repo allows ONLY schedule + workflow_dispatch triggers — no
# pull_request target can ever reach the secret. Receipts are pseudonymous (p-<sha256[:7]>).
# Fail-isolation: each task runs in its own subprocess; one red task never kills the beat;
# the beat exits non-zero if ANY task failed (honest red), receipts committed BEFORE eval.
# Leak-law: every string that could reach a public receipt passes clean() — the PAT can
# never land on the public plane, not even inside an error message (CalledProcessError
# embeds the full clone command, which carries the credential).
import json, os, subprocess, sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(ROOT, 'state', 'beat-tasks.json')
RECEIPT = os.path.join(ROOT, 'receipts', 'fleet-beat', 'last.json')
PAT = os.environ.get('SOVEREIGN_PAT', '')


def clean(s):
    """Scrub the credential out of anything that might reach a public receipt."""
    s = str(s)
    if PAT:
        s = s.replace(PAT, '***REDACTED***')
    return s


def clone(url, dst, depth=None):
    """PAT-carrying clone whose failure NEVER embeds the credential (fail-closed)."""
    cmd = ['git', 'clone', '-q']
    if depth:
        cmd += ['--depth', str(depth)]
    cmd += [url, dst]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(clean(r.stderr)[-300:] or 'clone failed')


def task_census(args):
    """Full-fleet census on free minutes: clone the public runner-kit, run its census with
    the sovereign PAT so the private supplement fills (28 repos) — the visibility the CI
    default token cannot have. Receipt = pseudonymous census JSON."""
    kit = args.get('repo', 'roshpinacare-sys/sovereign-runner-kit')
    dst = os.path.join('/tmp', 'beat-census-kit')
    subprocess.run(['rm', '-rf', dst], check=False)
    clone(f'https://x-access:{PAT}@github.com/{kit}.git', dst, depth=1)
    out = os.path.join(ROOT, 'receipts', 'fleet-beat', 'census.json')
    # CI has no GITHUB_TOKEN env and no pat.env file — the sovereign PAT IS the token
    env = dict(os.environ, CENSUS_OUT=out, GITHUB_TOKEN=PAT, FLEET_TOKEN=PAT)
    r = subprocess.run([sys.executable, os.path.join(dst, 'scripts', 'fleet-census.py')],
                       cwd=dst, env=env, capture_output=True, text=True, timeout=900)
    tail = (r.stdout or '').strip().splitlines()[-2:] if r.stdout else []
    return {'ok': r.returncode == 0, 'tail': [clean(t) for t in tail],
            'err': clean((r.stderr or '')[-300:]) if r.returncode else ''}


def task_yield_snapshot(args):
    """The 1000/day bridge instrument (read-only): read the live yield engine's public
    receipts and emit the measured snapshot + the honest gap to the owner's target."""
    src = args.get('repo', 'roshpinacare-sys/Autonomy')
    dst = os.path.join('/tmp', 'beat-yield-src')
    subprocess.run(['rm', '-rf', dst], check=False)
    url = f'https://x-access:{PAT}@github.com/{src}.git' if PAT else f'https://github.com/{src}.git'
    clone(url, dst, depth=1)  # leak-law: same fail-closed clone() as every other task
    last = os.path.join(dst, 'receipts', 'fleet-yield', 'last.json')
    d = json.load(open(last)) if os.path.exists(last) else {}
    if not d:
        return {'ok': False, 'error': 'no fleet-yield/last.json in source repo'}
    log = os.path.join(dst, 'receipts', 'fleet-yield', 'log.jsonl')
    entries = []
    if os.path.exists(log):
        for line in open(log).read().strip().splitlines()[-200:]:
            try: entries.append(json.loads(line))
            except Exception: pass
    # measured cadence: receipts per day over the log window (honest, window-bounded)
    days = {}
    for e in entries:
        at = str(e.get('at', ''))[:10]
        if at: days[at] = days.get(at, 0) + 1
    snap = {
        'verdict': d.get('verdict'), 'engineHead': d.get('engineHead'),
        'selftest': d.get('selftest', {}).get('status'),
        'voterStatus': d.get('voter', {}).get('status'),
        'candidatesScanned': d.get('candidates', {}).get('scanned'),
        'receiptsPerDay': dict(sorted(days.items())[-7:]),
        'logWindow': len(entries),
    }
    out = os.path.join(ROOT, 'receipts', 'fleet-beat', 'yield-snapshot.json')
    json.dump(snap, open(out, 'w'), indent=2)
    return {'ok': True, 'snapshot': snap}


def task_actions_guard(args):
    """The hourly switch-guard (wave-19.8, owner order trace 1a1512554a26f66d verbatim in
    state/fleet-actions-guard-approval.json): 18 repo-level Actions switches were found
    disabled by an unprovable actor. The beat verifies the APPROVED set hourly and re-arms
    any found OFF again — the fleet self-heals within the hour instead of silently dying.
    Scope discipline: ONLY the approved set (saos-dex + 17 pseudonyms); anything else found
    OFF is measured and reported, never touched. GET-verified after every PUT."""
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'fleet_actions_guard.py')],
                       env=dict(os.environ, SOVEREIGN_PAT=PAT),
                       capture_output=True, text=True, timeout=600)
    tail = (r.stdout or '').strip().splitlines()[-2:]
    return {'ok': r.returncode == 0, 'tail': [clean(t) for t in tail],
            'err': clean((r.stderr or '')[-200:]) if r.returncode else ''}


def task_economy_book(args):
    """Write-path task (owner approval verbatim in state/beat-tasks.json): the economy
    book breathes on FREE public minutes. Runs the book repo's OWN runner
    (run-economy-beat.mjs) UNMODIFIED — zero changes to the book's lineage. The repo's
    own single-writer heartbeat lock decides everything: host writer alive (<30min) →
    the beat SKIPS honestly; lock stale (e.g. sandbox wiped) → the executor adopts and
    keeps the book breathing. Receipts carry the OUTCOME WORD only — no book numbers,
    no book content ever lands on this public plane. Exit 3 = the repo's own RACE-LOST
    fail-closed race law — benign (canonical adopted, next beat re-seals), counted ok.
    Full clone (not depth-1): the runner reads HEAD~1 for its race parent check."""
    repo = args.get('repo', 'roshpinacare-sys/fleet-economy')
    writer = args.get('writer', 'sovereign-executor-beat')
    dst = os.path.join('/tmp', 'beat-economy')
    subprocess.run(['rm', '-rf', dst], check=False)
    clone(f'https://x-access:{PAT}@github.com/{repo}.git', dst)
    env = dict(os.environ, BEAT_SECONDS='180', ECONOMY_WRITER=writer)
    try:
        r = subprocess.run(['bun', 'run-economy-beat.mjs'], cwd=dst, env=env,
                           capture_output=True, text=True, timeout=540)
        code = r.returncode
        out = r.stdout or ''
    except subprocess.TimeoutExpired:
        code, out = -1, ''
    if code == 0 and 'SKIP' in out:
        outcome = 'skip-lock'          # host writer holds the book — one writer, one truth
    elif code == 0:
        outcome = 'sealed'             # the book breathed + verified + sealed to git
    elif code == 3:
        outcome = 'race-lost-fail-closed'  # the repo's own honest race law
    else:
        outcome = 'failed'
    snap = {'at': datetime.now(timezone.utc).isoformat(),
            'outcome': outcome, 'writer': writer, 'exit': code}
    out_path = os.path.join(ROOT, 'receipts', 'fleet-beat', 'economy-book.json')
    json.dump(snap, open(out_path, 'w'), indent=2)
    return {'ok': outcome != 'failed', 'outcome': outcome}


TASKS = {'private-census': task_census, 'yield-snapshot': task_yield_snapshot,
         'actions-guard': task_actions_guard, 'economy-book': task_economy_book}


def self_test():
    """The laws prove themselves every beat — retro-hardened (owner: 'וחזק אחורה').
    1. leak-law: clean() scrubs the credential from any receipt-bound string.
    2. fail-closed clone: a failing clone raises RuntimeError with ZERO credential.
    3. registry drift: every task declared in beat-tasks.json exists in TASKS.
    4. receipts plane writable (evidence can always land).
    5. guard law: the switch-guard's approval file is intact and the guard
       itself is fail-closed without a credential (wave-19.10 — the guard must
       never act blind, and its owner-approved scope must never drift)."""
    ok = bad = 0
    def check(name, cond, extra=''):
        nonlocal ok, bad
        if cond:
            ok += 1; print(f'selftest {name}: PASS')
        else:
            bad += 1; print(f'selftest {name}: FAIL {extra}')
    if PAT:
        probe = f'fatal: unable to access https://x-access:{PAT}@github.com/o/r.git/'
        scrubbed = clean(probe)
        check('clean-law-scrubs-credential', PAT not in scrubbed and '***REDACTED***' in scrubbed)
    else:
        print('selftest clean-law-scrubs-credential: SKIP (no credential material in env — unexercisable, honestly not green)')
    try:
        clone(f'https://x-access:{PAT}@github.com/roshpinacare-sys/__no_such_repo_leaklaw__.git',
              '/tmp/beat-selftest-leak')
        raised, msg = False, ''
    except RuntimeError as e:
        raised, msg = True, str(e)
    except Exception as e:  # any other exception type is itself a leak-law violation
        raised, msg = False, clean(e)
    # CI lesson (run 39136318673, 2026-10-18): with PAT='' the expression
    # `PAT not in msg` is ALWAYS False ('' in anything == True) — the check
    # must treat credential-absence as vacuously clean, not as a leak.
    credential_clean = (PAT not in msg) if PAT else True
    check('clone-fail-closed-no-credential', raised and credential_clean,
          f'(raised={raised}, msg={msg[:80]})')
    reg = json.load(open(REGISTRY))
    drift = [t.get('id') for t in reg.get('tasks', []) if t.get('id') not in TASKS]
    check('task-registry-no-drift', not drift, f'drift={drift}')
    try:
        os.makedirs(os.path.dirname(RECEIPT), exist_ok=True)
        probe_file = os.path.join(os.path.dirname(RECEIPT), '.selftest-probe')
        json.dump({'at': datetime.now(timezone.utc).isoformat()}, open(probe_file, 'w'))
        os.remove(probe_file)
        check('receipts-plane-writable', True)
    except Exception as e:
        check('receipts-plane-writable', False, clean(e)[:80])
    # law 5 (wave-19.10): the guard never acts blind + its scope never drifts.
    approval_path = os.path.join(ROOT, 'state', 'fleet-actions-guard-approval.json')
    guard_path = os.path.join(ROOT, 'scripts', 'fleet_actions_guard.py')
    try:
        approval = json.load(open(approval_path))
        approved = (len(approval.get('approvedSet', {}).get('publicNamed', [])),
                    len(approval.get('approvedSet', {}).get('privatePseudonyms', [])))
        check('guard-approval-file-intact',
              approved == (1, 17) and approval.get('ownerApproval', {}).get('trace') == '1a1512554a26f66d',
              f'approvedSet={approved}')
    except Exception as e:
        check('guard-approval-file-intact', False, clean(e)[:80])
    try:
        # the guard must refuse to act without a credential: run it with the
        # env explicitly stripped — no API calls, one FAIL-CLOSED line, exit 1.
        r = subprocess.run([sys.executable, guard_path],
                           env={k: v for k, v in os.environ.items() if k != 'SOVEREIGN_PAT'},
                           capture_output=True, text=True, timeout=60)
        out = clean(r.stdout or '')
        # vacuously-clean law (wave-19.5 lesson, re-learned 2026-10-19): with
        # PAT='' the expression `PAT not in out` is ALWAYS False — credential
        # absence must read as vacuously clean, not as a leak.
        credential_clean = (PAT not in out) if PAT else True
        check('guard-fail-closed-no-credential',
              r.returncode == 1 and 'FAIL-CLOSED' in out and credential_clean,
              f'(exit={r.returncode}, out={out[:70]!r})')
    except Exception as e:
        check('guard-fail-closed-no-credential', False, clean(e)[:80])
    print(f'beat selftest: {ok} passed, {bad} failed')
    return 1 if bad else 0


def main():
    if '--self-test' in sys.argv:
        return self_test()
    reg = json.load(open(REGISTRY))
    results = []
    failed = 0
    for t in reg.get('tasks', []):
        tid = t.get('id')
        fn = TASKS.get(tid)
        if not fn:
            results.append({'task': tid, 'ok': False, 'error': 'unknown task'}); failed += 1; continue
        try:
            r = fn(t)
            results.append({'task': tid, **r}); failed += 0 if r.get('ok') else 1
        except Exception as e:
            results.append({'task': tid, 'ok': False, 'error': clean(e)[:200]}); failed += 1
    receipt = {
        'schema': 'saos.executor.fleet-beat/1',
        'at': datetime.now(timezone.utc).isoformat(),
        'tasks': len(results), 'failed': failed,
        'results': results,
        'secretSurface': 'SOVEREIGN_PAT used in-memory only; never printed, never committed; no pull_request triggers exist in this repo; PAT scrubbed from every error string (clean law)',
    }
    os.makedirs(os.path.dirname(RECEIPT), exist_ok=True)
    json.dump(receipt, open(RECEIPT, 'w'), indent=2, ensure_ascii=False)
    print(f"fleet-beat: tasks={len(results)} failed={failed}")
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
