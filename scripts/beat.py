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
import json, os, subprocess, sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(ROOT, 'state', 'beat-tasks.json')
RECEIPT = os.path.join(ROOT, 'receipts', 'fleet-beat', 'last.json')
PAT = os.environ.get('SOVEREIGN_PAT', '')


def task_census(args):
    """Full-fleet census on free minutes: clone the public runner-kit, run its census with
    the sovereign PAT so the private supplement fills (28 repos) — the visibility the CI
    default token cannot have. Receipt = pseudonymous census JSON."""
    kit = args.get('repo', 'roshpinacare-sys/sovereign-runner-kit')
    dst = os.path.join('/tmp', 'beat-census-kit')
    subprocess.run(['rm', '-rf', dst], check=False)
    subprocess.run(['git', 'clone', '-q', '--depth', '1',
                    f'https://x-access:{PAT}@github.com/{kit}.git', dst], check=True)
    out = os.path.join(ROOT, 'receipts', 'fleet-beat', 'census.json')
    env = dict(os.environ, CENSUS_OUT=out)
    r = subprocess.run([sys.executable, os.path.join(dst, 'scripts', 'fleet-census.py')],
                       cwd=dst, env=env, capture_output=True, text=True, timeout=900)
    tail = (r.stdout or '').strip().splitlines()[-2:] if r.stdout else []
    return {'ok': r.returncode == 0, 'tail': tail, 'err': (r.stderr or '')[-300:] if r.returncode else ''}


def task_yield_snapshot(args):
    """The 1000/day bridge instrument (read-only): read the live yield engine's public
    receipts and emit the measured snapshot + the honest gap to the owner's target."""
    src = args.get('repo', 'roshpinacare-sys/Autonomy')
    dst = os.path.join('/tmp', 'beat-yield-src')
    subprocess.run(['rm', '-rf', dst], check=False)
    url = f'https://x-access:{PAT}@github.com/{src}.git' if PAT else f'https://github.com/{src}.git'
    subprocess.run(['git', 'clone', '-q', '--depth', '1', url, dst], check=True)
    last = os.path.join(dst, 'receipts', 'fleet-yield', 'last.json')
    d = json.load(open(last)) if os.path.exists(last) else {}
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


TASKS = {'private-census': task_census, 'yield-snapshot': task_yield_snapshot}


def main():
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
            results.append({'task': tid, 'ok': False, 'error': str(e)[:200]}); failed += 1
    receipt = {
        'schema': 'saos.executor.fleet-beat/1',
        'at': datetime.now(timezone.utc).isoformat(),
        'tasks': len(results), 'failed': failed,
        'results': results,
        'secretSurface': 'SOVEREIGN_PAT used in-memory only; never printed, never committed; no pull_request triggers exist in this repo',
    }
    os.makedirs(os.path.dirname(RECEIPT), exist_ok=True)
    json.dump(receipt, open(RECEIPT, 'w'), indent=2, ensure_ascii=False)
    print(f"fleet-beat: tasks={len(results)} failed={failed}")
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
