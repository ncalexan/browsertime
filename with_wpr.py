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

`pipenv run python with_wpr.py -v --wpr ~/Downloads/wpr-go/wpr-macosx64 --record 'curl --silent --show-error --proxy 127.0.0.1:4040 https://example.com/ --proxy-cacert /Users/nalexander/.mitmproxy/mitmproxy-ca-cert.pem --cacert /Users/nalexander/.mitmproxy/mitmproxy-ca-cert.pem -vvv' --replay 'curl --silent --show-error --proxy 127.0.0.1:4040 https://example.com/ --proxy-cacert /Users/nalexander/.mitmproxy/mitmproxy-ca-cert.pem --cacert /Users/nalexander/.mitmproxy/mitmproxy-ca-cert.pem' --wpr-args '--host 127.0.0.1 --https_cert_file /Users/nalexander/.mitmproxy/mitmproxy-ca-cert.pem --https_key_file /Users/nalexander/.mitmproxy/mitmproxy-ca-key.pem'` # noqa
"""

from __future__ import absolute_import, print_function, unicode_literals


from abc import ABCMeta, abstractmethod
import argparse
from contextlib import contextmanager
import errno
import os
import pipes
import signal
import shlex
import sys
import tempfile
import time
import warnings

import mozprocess

import backoff
import requests


VERBOSE = 0
DRY_RUN = False


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
        for line in line.split('\n'):
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
    timeout = kwargs.pop('timeout', None)
    outputTimeout = kwargs.pop('outputTimeout', None)
    onTimeout = kwargs.pop('onTimeout', None)

    proc_holder = [None]
    if onTimeout:
        kwargs['onTimeout'] = lambda: onTimeout(proc_holder[0])

    prefix = kwargs.pop('prefix', None)
    if prefix:
        streamoutput = FormatStreamOutput(sys.stdout, '[{}] {{}}'.format(prefix))
    else:
        streamoutput = FormatStreamOutput(sys.stdout, '{}')

    logfile = kwargs.pop('logfile')
    ensureParentDir(logfile)
    try:
        os.remove(logfile)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise

    logoutput = FormatLogOutput(logfile, '{}')

    processOutputLine = [streamoutput, logoutput]
    kwargs['processOutputLine'] = processOutputLine

    proc = mozprocess.ProcessHandler(*args, **kwargs)

    if VERBOSE:
        cmd = [proc.cmd] + proc.args
        printable_cmd = ' '.join(pipes.quote(arg) for arg in cmd)
        for pol in processOutputLine:
            pol('Executing "{}"{}\n'.format(printable_cmd, '' if not proc.cwd else ' in "{}"'.format(proc.cwd)))

    if DRY_RUN:
        proc = mozprocess.ProcessHandler(['true'], **kwargs)  # XXX what to invoke on Windows?

    proc_holder[0] = proc

    try:
        proc.run(timeout=timeout, outputTimeout=outputTimeout)
        yield proc
    finally:
        if proc.poll() is None:
            proc.kill(signal.SIGINT)
            if proc.poll() is None:
                time.sleep(1.0)
                if proc.poll() is None:
                    proc.kill()


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
    if DRY_RUN:
        return

    with warnings.catch_warnings():
        # Eat warnings about SSL insecurity.  These fetches establish status only.
        warnings.simplefilter("ignore")
        requests.get(url, verify=False)


class Proxy(object):
    __metaclass__ = ABCMeta

    @property
    @abstractmethod
    def tag(self):
        r'''A short string identifying the type of proxy to a consumer, like 'wpr' or 'mitmproxy'.'''
        pass

    @abstractmethod
    def record(self, logfile):
        pass

    @abstractmethod
    def replay(self, logfile):
        pass

    @abstractmethod
    def ensure_recording_started(self, recorder=None):
        pass

    @abstractmethod
    def ensure_replaying_started(self, replayer=None):
        pass

    def record_and_replay(self,
                          output_prefix,
                          archive_path,
                          record=None, record_args=[], record_kwargs={},
                          record_logfile=None,
                          record_verify=None,
                          replay=None, replay_args=[], replay_kwargs={},
                          replay_logfile=None,
                          replay_verify=None):
        if record:
            with self.record(logfile=record_logfile, archive_path=archive_path) as recorder:
                self.ensure_recording_started(recorder)

                status = record(*record_args, **record_kwargs)
                if status:
                    raise RuntimeError("Recording failed: ", status)

                if record_verify:
                    status = record_verify(*record_args, **record_kwargs)
                    if status:
                        raise RuntimeError("Record verifying failed: ", status)

        if replay:
            with self.replay(logfile=replay_logfile, archive_path=archive_path) as replayer:
                self.ensure_replaying_started(replayer)

                status = replay(*replay_args, **replay_kwargs)
                if status:
                    raise RuntimeError("Replaying failed: ", status)

                if replay_verify:
                    status = replay_verify(*replay_args, **replay_kwargs)
                    if status:
                        raise RuntimeError("Replay verifying failed: ", status)

    def record_and_replay_processes(
            self,
            output_prefix,
            record=None,
            record_verify=None,
            replay=None,
            replay_verify=None):
        r"""Execute `record` with `wpr record ...` running, and then execute
        `replay` with `wpr replay ...` running.

        Writes `$output_prefix{record.log,replay.log,
        wpr-record.log,wpr-replay.log,archive.wprgo}`.
        """
        record_cmd_logfile = '{}record-{}.log'.format(output_prefix, 'cmd')
        replay_cmd_logfile = '{}replay-{}.log'.format(output_prefix, 'cmd')
        record_proxy_logfile = '{}record-{}.log'.format(output_prefix, self.tag)
        replay_proxy_logfile = '{}replay-{}.log'.format(output_prefix, self.tag)
        archive_path = os.path.abspath('{}archive.wprgo'.format(output_prefix))

        def execute(*args, **kwargs):
            if args:
                with process(list(args), **kwargs) as proc:
                    return proc.wait()

        return self.record_and_replay(
            output_prefix,
            archive_path,
            record=execute,
            record_args=record,
            record_kwargs={'prefix': 'rec-cmd', 'logfile': record_cmd_logfile},
            record_logfile=record_proxy_logfile,
            record_verify=record_verify,  # XXX make this a process invocation too.
            replay=execute,
            replay_args=replay,
            replay_kwargs={'prefix': 'rep-cmd', 'logfile': replay_cmd_logfile},
            replay_logfile=replay_proxy_logfile,
            replay_verify=replay_verify)


class WPRProxy(Proxy):
    def __init__(self, wpr, wpr_root,
                 wpr_extra_args=[],
                 host='127.0.0.1',
                 http_proxy_port=4040,
                 http_port=8080,
                 https_port=8081):
        Proxy.__init__(self)

        self.http_proxy_port = http_proxy_port

        if not os.path.isfile(wpr) or not os.access(wpr, os.X_OK):
            raise ValueError('wpr is not an executable file: {}'.format(wpr))
        self.wpr = wpr

        if not os.path.isdir(wpr_root):
            raise ValueError('wpr_root is not a directory: {}'.format(wpr_root))
        self.wpr_root = wpr_root

        # Paths are relative to `wpr_root`.
        self.wpr_args = ['--inject_scripts', 'deterministic.js']
        if '--https_cert_file' not in wpr_extra_args:
            self.wpr_args.extend(['--https_cert_file', 'wpr_cert.pem'])  # XXX prefer mitmproxy certs.
        if '--https_key_file' not in wpr_extra_args:
            self.wpr_args.extend(['--https_key_file', 'wpr_key.pem'])

        self.host = host
        if '--host' in wpr_extra_args:
            self.host = wpr_extra_args[wpr_extra_args.index('--host') + 1]
        else:
            self.wpr_args.extend(['--host', self.host])

        self.http_port = http_port
        if '--http_port' in wpr_extra_args:
            self.http_port = int(wpr_extra_args[wpr_extra_args.index('--http_port') + 1])
        else:
            self.wpr_args.extend(['--http_port', str(self.http_port)])

        self.https_port = https_port
        if '--https_port' in wpr_extra_args:
            self.https_port = int(wpr_extra_args[wpr_extra_args.index('--https_port') + 1])
        else:
            self.wpr_args.extend(['--https_port', str(self.https_port)])

        self.wpr_args.extend(wpr_extra_args)

    @property
    def tag(self):
        return 'wpr'

    @contextmanager
    def record(self, logfile, archive_path):
        ensureParentDir(archive_path)

        with process([self.wpr, 'record'] + self.wpr_args + [archive_path],
                     cwd=self.wpr_root,
                     prefix='rec-wpr',
                     logfile=logfile) as record_proc:
            try:
                if record_proc.poll():
                    raise RuntimeError("Record proxy failed: ", record_proc.poll())

                yield record_proc
            finally:
                if record_proc.poll():
                    raise RuntimeError("Record proxy failed: ", record_proc.poll())

    @contextmanager
    def replay(self, logfile, archive_path):
        with process([self.wpr, 'replay'] + self.wpr_args + [archive_path],
                     cwd=self.wpr_root,
                     prefix='rep-wpr',
                     logfile=logfile) as replay_proc:
            try:
                if replay_proc.poll():
                    raise RuntimeError("Replay proxy failed: ", replay_proc.poll())

                yield replay_proc
            finally:
                if replay_proc.poll():
                    raise RuntimeError("Replay proxy failed: ", replay_proc.poll())

    def ensure_recording_started(self, recorder=None):
        # It takes some time for mitmproxy and wpr to be ready to serve.  mitmproxy is
        # actually slower (Python startup time, yo!) so we check for it last.
        _ensure_http_response("http://{}:{}/web-page-replay-generate-200".format(self.host, self.http_port))
        _ensure_http_response("https://{}:{}/web-page-replay-generate-200".format(self.host, self.https_port))
        _ensure_http_response("http://{}:{}/mitmdump-generate-200".format(self.host, self.http_proxy_port))

    def ensure_replaying_started(self, replayer=None):
        self.ensure_recording_started()

    def record_and_replay(self,
                          output_prefix,
                          archive_path,
                          record=None, record_args=[], record_kwargs={},
                          record_logfile=None,
                          record_verify=None,
                          replay=None, replay_args=[], replay_kwargs={},
                          replay_logfile=None,
                          replay_verify=None):
        # WebPageReplay [isn't a regular HTTP CONNECT
        # proxy](https://github.com/catapult-project/catapult/issues/4619).  Using
        # [goproxy](github.com/elazarl/goproxy) to [add HTTP CONNECT
        # support](https://github.com/ncalexan/catapult/commit/d21a98f0ee0bc0394eb93922d0b274fd6ac281d5)
        # didn't work well in practice: I saw lots of connection issues of different types.  So
        # instead we run mitmproxy just to handle port-forwarding, and then do the actual
        # record-and-replay with WebPageReplay.
        #
        # This just wraps the record-and-replay logic in this mitmproxy port-forwarding layer.

        mitmproxy_args = [
            '--listen-host',
            self.host,
            '--listen-port',
            str(self.http_proxy_port),
            '--scripts',
            'vendor/mitmproxy_portforward.py',  # XXX
            '--set', 'portmap=80:{},443:{}'.format(self.http_port, self.https_port),
            '--ssl-insecure',  # XXX explain why.  Is this really necessary?
        ]

        portforward_logfile = os.path.abspath('{}portforward-mitmproxy.log'.format(output_prefix))

        # `mitmdump` is sibling to `python` in the virtualenv `bin/` directory.
        with process([os.path.join(os.path.dirname(sys.executable), 'mitmdump')] + mitmproxy_args,
                     prefix='portfwd',
                     logfile=portforward_logfile) as portforward_proc:
            try:
                if portforward_proc.poll():
                    raise RuntimeError("Port forwarding proxy failed: ", portforward_proc.poll())

                return Proxy.record_and_replay(
                    self,
                    output_prefix,
                    archive_path,
                    record=record, record_args=record_args, record_kwargs=record_kwargs,
                    record_logfile=record_logfile,
                    record_verify=record_verify,
                    replay=replay, replay_args=replay_args, replay_kwargs=replay_kwargs,
                    replay_logfile=replay_logfile,
                    replay_verify=replay_verify)
            finally:
                if portforward_proc.poll():
                    raise RuntimeError("Port forwarding proxy failed: ", portforward_proc.poll())


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
    parser.add_argument('--dry-run', action='store_true',
                        help='Echo commands but do not execute')
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

    global DRY_RUN
    DRY_RUN = args.dry_run

    wpr, wpr_root = normalize_wpr_args(args.wpr, args.wpr_root)

    if VERBOSE > 1:
        print("Running wpr: {}".format(wpr))
        print("Running in wpr root: {}".format(wpr_root))

    proxy = WPRProxy(wpr, wpr_root, shlex.split(args.wpr_args))

    return proxy.record_and_replay_processes(
        args.output_prefix,
        record=shlex.split(args.record),
        replay=shlex.split(args.replay))


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
