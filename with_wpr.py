#!/bin/env python

r"""With `wpr record ...` running, invoke a function or launch a process.
Then with `wpr replay ...` running, invoke another function or launch
another process.

Collect the outputs from the `wpr ...` runs, the HTTP archive, and the
outputs from the processes.

Install like:

`pipenv install`

You will also need to install `mitmproxy`, perhaps using `brew install mitmproxy`.  TODO: figure out how to invoke `mitmdump` from a Python module installed using `pipenv install`; this will require we use Python 3 (which is fine, but not yet done).

Invoke like:

`pipenv run python with_wpr.py -v --wpr ~/Downloads/wpr-go/wpr-macosx64 --record 'curl --proxy 127.0.0.1:4040 https://example.com/ --proxy-cacert /Users/nalexander/.mitmproxy/mitmproxy-ca-cert.pem --cacert /Users/nalexander/.mitmproxy/mitmproxy-ca-cert.pem -vvv' --replay 'curl --proxy 127.0.0.1:4040 https://example.com/ --proxy-cacert /Users/nalexander/.mitmproxy/mitmproxy-ca-cert.pem --cacert /Users/nalexander/.mitmproxy/mitmproxy-ca-cert.pem' --wpr-args '--host 127.0.0.1 --https_cert_file /Users/nalexander/.mitmproxy/mitmproxy-ca-cert.pem --https_key_file /Users/nalexander/.mitmproxy/mitmproxy-ca-key.pem'` # noqa
"""

from __future__ import absolute_import, print_function, unicode_literals


import argparse
from contextlib import contextmanager
import errno
import mozprocess
import os
import pipes
import requests
import signal
import shlex
import subprocess
import sys
import tempfile
import warnings

import backoff
import requests


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


class FormatStreamOutput(object):
    """Pass formatted output to a stream and flush"""

    def __init__(self, stream, template):
        self.stream = stream
        self.template = template + '\n'

    def __call__(self, line):
        if type(line) == bytes:
            line = line.decode('utf-8')
        self.stream.write(self.template.format(line))
        self.stream.flush()


class FormatLogOutput(FormatStreamOutput):
    """Pass formatted output to a file."""

    def __init__(self, filename, template):
        self.file_obj = open(filename, 'a')
        FormatStreamOutput.__init__(self, self.file_obj, template)

    def __del__(self):
        if self.file_obj is not None:
            self.file_obj.close()


@contextmanager
def process(*args, **kwargs):
    logoutput = FormatLogOutput(kwargs.pop('logfile'), template='{}')
    processOutputLine = [FormatStreamOutput(sys.stdout, "[{}] {{}}".format(kwargs.pop('prefix'))), logoutput]
    kwargs['processOutputLine'] = processOutputLine

    proc = mozprocess.ProcessHandler(*args, **kwargs)

    if VERBOSE:
        cmd = [proc.cmd] + proc.args
        printable_cmd = ' '.join(pipes.quote(arg) for arg in cmd)
        for pol in processOutputLine:
            pol('Executing "{}"{}'.format(printable_cmd, '' if not proc.cwd else ' in "{}"'.format(proc.cwd)))

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


@backoff.on_exception(backoff.expo,
                      requests.exceptions.RequestException,
                      max_time=5)
def _ensure_http_response(url):
    with warnings.catch_warnings():
        # Eat warnings about SSL insecurity.  These fetches establish status only.
        warnings.simplefilter("ignore")
        return requests.get(url, verify=False)


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

    portforward_logfile = os.path.abspath('{}portforward-mitmproxy.log'.format(output_prefix))
    record_logfile = os.path.abspath('{}record-wpr.log'.format(output_prefix))
    replay_logfile = os.path.abspath('{}replay-wpr.log'.format(output_prefix))

    for path in (portforward_logfile, record_logfile, replay_logfile):
        ensureParentDir(path)
        try:
            os.remove(path)
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise

    status = 0

    host = '127.0.0.1'
    print(wpr_extra_args)
    if '--host' in wpr_extra_args:
        host = wpr_extra_args[wpr_extra_args.index('--host') + 1]

    mitmproxy_args = ['--listen-host',
                      host,
                      '--listen-port',
                      str(4040), # Configurable?
                      '-s',
                      'vendor/mitmproxy_portforward.py', # XXX
                      '--set', 'portmap=80,8080,443,8081', # Configurable.
                      '--ssl-insecure',  # REALLY?
                      # '--certs', '*=/Users/nalexander/.mitmproxy/mitmproxy-ca.pem',
                      # '--certs', '*=/Users/nalexander/Downloads/wpr-go/wpr_both.pem',
                      ]

    # `mitmdump` is sibling to `python` in the virtualenv `bin/` directory.
    with process([os.path.join(os.path.dirname(sys.executable), 'mitmdump')] + mitmproxy_args,
                 prefix='portfwd',
                 logfile=portforward_logfile) as portforward_proc:
        try:
            if portforward_proc.poll():
                raise RuntimeError("Port forwarding proxy failed: ", portforward_proc.poll())

            with process([wpr, 'record'] + wpr_args,
                         cwd=wpr_root,
                         prefix='rec-wpr',
                         logfile=record_logfile) as record_proc:
                try:
                    if record_proc.poll():
                        raise RuntimeError("Record proxy failed: ", record_proc.poll())

                    # It takes some time for mitmproxy and wpr to be ready to serve.  mitmproxy is
                    # actually slower (Python startup time, yo!) so we check for it last.
                    r = _ensure_http_response("http://{}:{}/web-page-replay-generate-200".format(host, 8080))
                    r = _ensure_http_response("https://{}:{}/web-page-replay-generate-200".format(host, 8081))
                    r = _ensure_http_response("http://{}:{}/mitmdump-generate-200".format(host, 4040))
                    print(r)

                    status = record(*record_args, **record_kwargs)
                    if status:
                        raise RuntimeError("Recording failed: ", status)
                    if record_verify:
                        status = record_verify(*record_args, **record_kwargs)

                        if status:
                            raise RuntimeError("Record verifying failed: ", status)
                finally:
                    if record_proc.poll():
                        raise RuntimeError("Record proxy failed: ", record_proc.poll())
                    else:
                        record_proc.kill(signal.SIGINT)

            with process([wpr, 'replay'] + wpr_args,
                         cwd=wpr_root,
                         prefix='rep-wpr',
                         logfile=replay_logfile) as replay_proc:
                try:
                    if replay_proc.poll():
                        raise RuntimeError("Replay proxy failed: ", replay_proc.poll())

                    # It takes some time for wpr to be ready to serve.  Don't race!
                    r = _ensure_http_response("http://{}:{}/web-page-replay-generate-200".format(host, 8080))
                    r = _ensure_http_response("https://{}:{}/web-page-replay-generate-200".format(host, 8081))

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
        finally:
            if portforward_proc.poll():
                raise RuntimeError("Port forwarding proxy failed: ", portforward_proc.poll())
            else:
                portforward_proc.kill(signal.SIGINT)


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
        record_kwargs={'prefix': 'rec-cmd', 'logfile': record_logfile},
        record_verify=record_verify,
        replay=execute,
        replay_args=replay,
        replay_kwargs={'prefix': 'rep-cmd', 'logfile': replay_logfile},
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
                        'and deterministic.js (or set --wpr-root).')
    parser.add_argument('--wpr-root', dest='wpr_root',
                        default=None,
                        help='Web Page Replay Go root directory ' +
                        '(contains wpr_{cert,key}.pem, deterministic.js, ' +
                        'wpr-* binaries)')
    parser.add_argument('--wpr-args', dest='wpr_args', default='', help='string of wpr args')
    parser.add_argument('--record', required=True, help='string record command')
    parser.add_argument('--replay', required=True, help='string replay command')
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
