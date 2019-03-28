#!/bin/env python

r"""With `wpr record ...` running, invoke a function or launch a process.
Then with `wpr replay ...` running, invoke another function or launch
another process.

Collect the outputs from the `wpr ...` runs, the HTTP archive, and the
outputs from the processes.

Install with:

`pipenv install`

Invoke like:

`pipenv run python with_wpr.py -v --wpr /path/to/wpr --record 'curl --proxy localhost:4040 http://example.com' --replay 'curl --proxy localhost https://example.com'` # noqa
"""

from __future__ import absolute_import, print_function, unicode_literals


import argparse
from contextlib import contextmanager
import errno
import mozprocess
import os
import pipes
import signal
import shlex
import sys
import tempfile


VERBOSE = 0


def ensureParentDir(path):
    """Ensures the directory parent to the given file exists."""
    d = os.path.dirname(path)
    if d and not os.path.exists(path):
        try:
            os.makedirs(d)
        except OSError as error:
            if error.errno != errno.EEXIST:
                raise


@contextmanager
def process(*args, **kwargs):
    proc = mozprocess.ProcessHandler(*args, **kwargs)

    if VERBOSE:
        cmd = [proc.cmd] + proc.args
        printable_cmd = ' '.join(pipes.quote(arg) for arg in cmd)
        print('Executing "{}"{}'.format(printable_cmd, '' if not proc.cwd else ' in "{}"'.format(proc.cwd)), file=sys.stderr)
        sys.stderr.flush()

    try:
        proc.run()
        yield proc
    finally:
        try:
            proc.kill()
        except RuntimeError as e:
            print(e)
            pass


def wpr_process_name(platform=sys.platform):
    is_64bits = sys.maxsize > 2**32

    if sys.platform.startswith('linux'):
        return 'wpr-linux64'
    if sys.platform.startswith('darwin'):
        return 'wpr-macosx64'
    if sys.platform.startswith('win'):
        if is_64bits:
            return 'wpr-win64.exe'
        else:
            return 'wpr-win32.exe'

    raise ValueError("Don't recognize platform: {}".format(platform))


def record_and_replay(
        wpr, wpr_root, wpr_extra_args=[],
        output_prefix='wpr',
        record=None, record_args=[], record_kwargs={},
        record_verify=None,
        replay=None, replay_args=[], replay_kwargs={},
        replay_verify=None):
    r"""Invoke `record(*record_args, **record_kwargs)` with `wpr record
    ...` running, and then invoke `replay(*replay_args,
    **replay_kwargs)` with `wpr replay ...` running.

    Writes `$output_prefix{wpr-record.log,wpr-replay.log,archive.wprgo}`.
    """

    if not os.path.isfile(wpr) or not os.access(wpr, os.X_OK):
        raise ValueError('wpr is not an executable file: {}'.format(wpr))

    if not os.path.isdir(wpr_root):
        raise ValueError('wpr_root is not a directory: {}'.format(wpr_root))

    # Paths are relative to `wpr_root`.
    wpr_args = ['--http_port', str(8080),
                '--https_port', str(8081),
                '--inject_scripts', 'deterministic.js']
    if '--https_cert_file' not in wpr_extra_args:
        wpr_args.extend(['--https_cert_file', 'wpr_cert.pem'])
    if '--https_key_file' not in wpr_extra_args:
        wpr_args.extend(['--https_key_file', 'wpr_key.pem'])

    wpr_args.extend(wpr_extra_args)

    archive_path = os.path.abspath('{}archive.wprgo'.format(output_prefix))
    ensureParentDir(archive_path)
    wpr_args.append(archive_path)

    record_logfile = os.path.abspath('{}record-wpr.log'.format(output_prefix))
    replay_logfile = os.path.abspath('{}replay-wpr.log'.format(output_prefix))

    for path in (record_logfile, replay_logfile):
        ensureParentDir(path)
        try:
            os.remove(path)
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise

    status = 0

    with process([wpr, 'record'] + wpr_args,
                 cwd=wpr_root,
                 logfile=record_logfile) as record_proc:
        try:
            if record_proc.poll():
                raise RuntimeError("Record proxy failed: ", record_proc.poll())

            status = record(*record_args, **record_kwargs)
            if status:
                raise RuntimeError("Recording failed: ", status)
            print("record_verify", bool(record_verify))
            if record_verify:
                status = record_verify(*record_args, **record_kwargs)
                print("record_verify status", status)

                if status:
                    raise RuntimeError("Record verifying failed: ", status)
        finally:
            if record_proc.poll():
                raise RuntimeError("Record proxy failed: ", record_proc.poll())
            else:
                record_proc.kill(signal.SIGINT)

    with process([wpr, 'replay'] + wpr_args,
                 cwd=wpr_root,
                 logfile=replay_logfile) as replay_proc:
        try:
            if replay_proc.poll():
                raise RuntimeError("Replay proxy failed: ", replay_proc.poll())

            status = replay(*replay_args, **replay_kwargs)
            if status:
                raise RuntimeError("Replaying failed: ", status)
            if replay_verify:
                status = replay_verify(*replay_args, **replay_kwargs)
                if status:
                    raise RuntimeError("Replay verifying failed: ", status)
        finally:
            if replay_proc.poll():
                raise RuntimeError("Replay proxy failed: ", replay_proc.poll())
            else:
                replay_proc.kill(signal.SIGINT)
        # return replay(*replay_args, **replay_kwargs)


def record_and_replay_processes(
        wpr, wpr_root, wpr_extra_args=[],
        output_prefix='wpr',
        record=None,
        record_verify=None,
        replay=None,
        replay_verify=None,
        logtag=None):
    r"""Execute `record` with `wpr record ...` running, and then execute
    `replay` with `wpr replay ...` running.

    Writes `$output_prefix{record.log,replay.log,
    wpr-record.log,wpr-replay.log,archive.wprgo}`.
    """
    record_logfile = '{}record{}.log'.format(output_prefix, '' if not logtag else '-{}'.format(logtag))
    replay_logfile = '{}replay{}.log'.format(output_prefix, '' if not logtag else '-{}'.format(logtag))

    for path in (record_logfile, replay_logfile):
        ensureParentDir(path)
        try:
            os.remove(path)
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise

    def execute(*args, **kwargs):
        with process(list(args), **kwargs) as proc:
            return proc.wait()

    return record_and_replay(
        wpr, wpr_root, wpr_extra_args=wpr_extra_args,
        output_prefix=output_prefix,
        record=execute,
        record_args=record,
        record_kwargs={'logfile': record_logfile},
        record_verify=record_verify,
        replay=execute,
        replay_args=replay,
        replay_kwargs={'logfile': replay_logfile},
        replay_verify=replay_verify)


ROOT = os.path.abspath(os.path.dirname(__file__))

def normalize_wpr_args(wpr, wpr_root):
    if not wpr and not wpr_root:
        wpr_root = os.path.join(ROOT, 'docker', 'webpagereplay')
        wpr = os.path.join(wpr_root, wpr_process_name())
    elif not wpr_root:
        wpr_root = os.path.dirname(os.path.abspath(wpr))
    elif not wpr:
        wpr = os.path.join(wpr_root, wpr_process_name())
    return wpr, wpr_root


def main(args):
    parser = argparse.ArgumentParser()
    parser.add_argument('--verbose', '-v', action='count',
                        help='Be verbose (can be repeated)')
    parser.add_argument('--wpr',
                        default=None,
                        help='Web Page Replay Go binary. ' +
                        'Parent directory should contain wpr_{cert,key}.pem '
                        'and deterministic.js (or set --root).')
    parser.add_argument('--root', dest='wpr_root',
                        default=None,
                        help='Web Page Replay Go root directory ' +
                        '(contains wpr_{cert,key}.pem, deterministic.js, ' +
                        'wpr-* binaries)')
    parser.add_argument('--args', dest='wpr_args', default='', help='wpr args')
    parser.add_argument('--record', required=True, help='record')
    parser.add_argument('--replay', required=True, help='replay')
    parser.add_argument('--output-prefix',
                        default='{}/rnr-'.format(tempfile.gettempdir()),
                        help='Output prefix (end with / to create directory)')
    args = parser.parse_args(args)

    global VERBOSE
    VERBOSE = args.verbose

    wpr, wpr_root = normalize_wpr_args(args.wpr, args.wpr_root)

    if VERBOSE:
        print("Running wpr: {}".format(wpr))
        print("Running in wpr root: {}".format(wpr_root))

    return record_and_replay_processes(
        wpr,
        wpr_root,
        wpr_extra_args=shlex.split(args.wpr_args),
        output_prefix=args.output_prefix,
        record=shlex.split(args.record),
        replay=shlex.split(args.replay))


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
