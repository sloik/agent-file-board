#!/usr/bin/env python3
"""Bound and retry network setup, never tests. Kill the owned process group on timeout."""
import argparse
import os
import signal
import subprocess
import sys


def attempt(command, seconds):
    process = subprocess.Popen(command, start_new_session=True)
    try:
        return process.wait(timeout=seconds)
    except BaseException:
        # Includes timeout and interruption: pip/apt children must not outlive setup.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        # The group can retain a child even after its leader exits.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        raise


def run(command, seconds=180, attempts=2, execute=attempt):
    if not command or not 0 < seconds <= 600 or not 1 <= attempts <= 3:
        raise ValueError('invalid setup bounds')
    for number in range(1, attempts + 1):
        print(f'Network setup attempt {number}/{attempts} (limit {seconds}s)', flush=True)
        try:
            code = execute(command, seconds)
        except subprocess.TimeoutExpired:
            code = 124
        if code == 0:
            return 0
    print('Network setup exhausted; verification did not run successfully.', file=sys.stderr)
    return code if code > 0 else 1


if __name__ == '__main__':
    def stop(signum, frame):
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, stop)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=180)
    parser.add_argument('--attempts', type=int, default=2)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    sys.exit(run(command, args.seconds, args.attempts))
