#!/bin/env python

from __future__ import absolute_import, unicode_literals, print_function

import structlog

import argparse
from collections import OrderedDict
from contextlib import contextmanager
import errno
import functools
import itertools
import json
import mozprocess
import os
import pipes
import signal
import shlex
import sys
import urllib
import urlparse

import with_wpr

from blessings import Terminal

TERMINAL = Terminal()

log = structlog.get_logger()
log.msg("greeted", whom="world", more_than_a_string=[1, 2, 3])
log.info("info", whom="world", more_than_a_string=[1, 2, 3])
log.debug("debug", whom="world", more_than_a_string=[1, 2, 3])

# VERBOSE = 0


def ensureParentDir(path):
    """Ensures the directory parent to the given file exists."""
    d = os.path.dirname(path)
    if d and not os.path.exists(path):
        try:
            os.makedirs(d)
        except OSError as error:
            if error.errno != errno.EEXIST:
                raise


# @contextmanager
# def process(*args, **kwargs):
#     proc = mozprocess.ProcessHandler(*args, **kwargs)

#     if VERBOSE:
#         cmd = [proc.cmd] + proc.args
#         printable_cmd = ' '.join(pipes.quote(arg) for arg in cmd)
#         print('Executing "{}"'.format(printable_cmd), file=sys.stderr)
#         sys.stderr.flush()

#     try:
#         proc.run()
#         yield proc
#     finally:
#         try:
#             proc.kill()
#         except RuntimeError as e:
#             print(e)
#             pass


# def wpr_process_name(platform=sys.platform):
#     is_64bits = sys.maxsize > 2**32

#     if sys.platform.startswith('linux'):
#         return 'wpr-linux64'
#     if sys.platform.startswith('darwin'):
#         return 'wpr-macosx64'
#     if sys.platform.startswith('win'):
#         if is_64bits:
#             return 'wpr-win64.exe'
#         else:
#             return 'wpr-win32.exe'

#     raise ValueError("Don't recognize platform: {}".format(platform))


# def record_and_replay(
#         wpr_root, wpr_extra_args=[],
#         output_prefix='wpr',
#         record=None, record_args=[], record_kwargs={},
#         replay=None, replay_args=[], replay_kwargs={}):
#     r"""Invoke `record(*record_args, **record_kwargs)` with `wpr record
#     ...` running, and then invoke `replay(*replay_args,
#     **replay_kwargs)` with `wpr replay ...` running.

#     Writes `$output_prefix{wpr-record.log,wpr-replay.log,archive.wprgo}`.
#     """

#     # Paths are relative to `wpr_root`.
#     wpr_args = ['--http_connect_proxy_port', str(4040),
#                 '--http_port', str(8080),
#                 '--https_port', str(8081),
#                 '--https_cert_file', 'wpr_cert.pem',
#                 '--https_key_file', 'wpr_key.pem',
#                 '--inject_scripts', 'deterministic.js']
#     wpr_args.extend(wpr_extra_args)

#     archive_path = '{}archive.wprgo'.format(output_prefix)
#     ensureParentDir(archive_path)
#     wpr_args.append(archive_path)

#     record_logfile = '{}wpr-record.log'.format(output_prefix)
#     replay_logfile = '{}wpr-replay.log'.format(output_prefix)

#     for path in (record_logfile, replay_logfile):
#         ensureParentDir(path)
#         try:
#             os.remove(path)
#         except OSError as e:
#             if e.errno != errno.ENOENT:
#                 raise

#     cmd = os.path.join(wpr_root, wpr_process_name())

#     with process([cmd, 'record'] + wpr_args,
#                  cwd=wpr_root,
#                  logfile=record_logfile) as record_proc:
#         try:
#             record(*record_args, **record_kwargs)
#         finally:
#             if not record_proc.poll():
#                 record_proc.kill(signal.SIGINT)

#     with process([cmd, 'replay'] + wpr_args,
#                  cwd=wpr_root,
#                  logfile=replay_logfile):
#         return replay(*replay_args, **replay_kwargs)


# def record_and_replay_processes(
#         wpr_root, wpr_extra_args=[],
#         output_prefix='wpr',
#         record=None,
#         replay=None):
#     r"""Execute `record` with `wpr record ...` running, and then execute
#     `replay` with `wpr replay ...` running.

#     Writes `$output_prefix{record.log,replay.log,
#     wpr-record.log,wpr-replay.log,archive.wprgo}`.
#     """
#     record_logfile = '{}record.log'.format(output_prefix)
#     replay_logfile = '{}replay.log'.format(output_prefix)

#     for path in (record_logfile, replay_logfile):
#         ensureParentDir(path)
#         try:
#             os.remove(path)
#         except OSError as e:
#             if e.errno != errno.ENOENT:
#                 raise

#     def execute(*args, **kwargs):
#         with process(list(args), **kwargs) as proc:
#             return proc.wait()

#     return record_and_replay(
#         wpr_root, wpr_extra_args=wpr_extra_args,
#         output_prefix=output_prefix,
#         record=execute,
#         record_args=record,
#         record_kwargs={'logfile': record_logfile},
#         replay=execute,
#         replay_args=replay,
#         replay_kwargs={'logfile': replay_logfile})


class WprConfiguration(object):
    """xyz"""
    __slots__ = (
        'wpr',
        'root',
        'extra_args',
    )

    def __init__(self, wpr, root, extra_args=[]):
        self.wpr, self.root = with_wpr.normalize_wpr_args(wpr, root)
        self.extra_args = extra_args


class VehicleConfiguration(object):
    """xyz"""
    __slots__ = (
        'browser',
        'turbo',
        'record',
        'replay',
        'live',
    )

    def __init__(self, browser, turbo, record, replay, live):
        if browser not in ('firefox', 'chrome'):
            raise ValueError("browser not 'firefox' or 'chrome': '{}'".format(browser))
        self.browser = browser
        if turbo not in ('true', 'false'):
            raise ValueError("turbo not 'true' or 'false': '{}'".format(turbo))
        self.turbo = turbo
        self.record = list(record)
        self.replay = list(replay)
        self.live = list(live)

    def result_dir(self, url_result_dir):
        return os.path.join(url_result_dir, '{}-{}'.format(self.browser, self.turbo))


def verify_browsertime_results(path, expected, *args, **kwargs):
    if not os.path.exists(path):
        log.warn('record_verify path not found', path=path)
        raise RuntimeError('record_verify path not found')

    actual = len(json.load(open(path, 'rt')))
    if actual != expected:
        log.warn('record_verify wrong number of results', actual=actual, expected=expected)
        raise RuntimeError('record_verify wrong number of results')

    return 0

def test_one_url(vehicle_configuration, wpr_configuration, result_dir, url):
    ensureParentDir(result_dir)

    record = vehicle_configuration.record + ['--resultDir', os.path.join(result_dir, 'record'), url]
    replay = vehicle_configuration.replay + ['--resultDir', os.path.join(result_dir, 'replay'), url]

    return with_wpr.record_and_replay_processes(
        wpr_configuration.wpr,
        wpr_configuration.root,
        wpr_extra_args=wpr_configuration.extra_args,
        output_prefix=result_dir if result_dir.endswith(os.sep) else result_dir + os.sep,
        record=record,
        record_verify=functools.partial(verify_browsertime_results, os.path.join(result_dir, 'record', 'browsertime.json'), 1),
        replay=replay,
        logtag='browsertime')


def main(args):
    default_root = os.path.join(
        os.path.abspath(os.path.dirname(__file__)), 'docker', 'webpagereplay')

    parser = argparse.ArgumentParser()
    parser.add_argument('--verbose', '-v', action='count',
                        help='Be verbose (can be repeated)')
    parser.add_argument('--video', action='store_true', default=False,
                        help='Record and store video of each pageload.')
    parser.add_argument('--wpr',
                        default=None,
                        help='Web Page Replay Go binary. ' +
                        'Parent directory should contain wpr_{cert,key}.pem '
                        'and deterministic.js (or set --root).')
    parser.add_argument('--wpr-root',
                        default=None,
                        help='Web Page Replay Go root directory ' +
                        '(contains wpr_{cert,key}.pem, deterministic.js, ' +
                        'wpr-* binaries)')
    parser.add_argument('--wpr-args', default='', help='wpr args')
    parser.add_argument('--wpr-host', default=None, help='wpr host to bind')

    parser.add_argument('--iterations', '-n', default=1, type=int, help='XXX') # xxx

    parser.add_argument('--browsers', default=['firefox', 'chrome'], choices=['firefox', 'chrome'], nargs='*')
    parser.add_argument('--turbos', default=['true', 'false'], choices=['true', 'false'], nargs='*')
    # parser.add_argument('--turbo', action='append', default=[], dest='turbos')

    parser.add_argument('--geckodriver',
                        default=None,
                        help='geckodriver binary.')
    parser.add_argument('--chromedriver',
                        default=None,
                        help='chromedriver binary.')

    parser.add_argument('--firefox-true-profile-template',
                        default=None,
                        help='Gecko profile template directory to use when turbo is true.')
    parser.add_argument('--firefox-false-profile-template',
                        default=None,
                        help='Gecko profile template directory to use when turbo is false.')

    parser.add_argument('--result-dir',
                        default='browsertime-results-android',
                        help='Result directory to populate with browsertime result files, collected data files, and log files.') # xxx
    parser.add_argument('--force',
                        action='store_true',
                        default=False,
                        help='Force writing to existing result directory')

    parser.add_argument('--no-continue',
                        action='store_true',
                        default=False,
                        help='Do not continue after first failing configuration.')

    parser.add_argument('urls', nargs='+', help='URLs') # xxx

    # parser.add_argument('url', help='URL') # xxx

    args = parser.parse_args(args)

    global VERBOSE
    VERBOSE = args.verbose
    with_wpr.VERBOSE = VERBOSE

    # print(args)
    # sys.exit(0)

    urls = []
    for url in args.urls:
        if url.startswith('@'):
            urls.extend(line.strip() for line in open(url[1:], 'rt') if line.strip() and not line.strip().startswith('#'))
        else:
            urls.append(url)

    for url in urls:
        if urlparse.urlparse(url).scheme not in ('http', 'https'):
            raise ValueError('URL scheme is not http(s): {}'.format(url))

    print(urls)

    if os.path.exists(args.result_dir) and not args.force:
        raise ValueError('Results directory exists with no --force flag: {}', args.result_dir)

    # args.turbos = [turbo == 'true' for turbo in args.turbos]

    browsertime = 'bin/browsertime.js'
    shared_browsertime_args = [
        'bin/browsertime.js',
        '--android',
        '--skipHar',
    ]

    shared_browsertime_args.extend(['-v'] * args.verbose)

    if args.video:
        shared_browsertime_args.extend(['--video'])

    # From `docker/scripts/start.sh`.  We must use this wait script for both
    # record and replay, because the default script uses `Date.now()`, which WPR
    # makes deterministic!
    WAIT_SCRIPT = 'return (function() {try { var end = window.performance.timing.loadEventEnd; var start= window.performance.timing.navigationStart; return (end > 0) && (performance.now() > end - start + %d);} catch(e) {return true;}})()' % (10000,)
    shared_browsertime_args.extend(['--pageCompleteCheck', WAIT_SCRIPT])

    shared_browsertime_args.extend(['--preURL', 'data:text/html,', '--preURLDelay', '5000'])

    if args.wpr or args.wpr_root:
        import socket
        def get_ip():
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                # doesn't even have to be reachable
                s.connect(('10.255.255.255', 1))
                return s.getsockname()[0]
            except:
                return '127.0.0.1'
            finally:
                s.close()

    host = args.wpr_host or get_ip()

    # browser {firefox, chrome} x turbo {on, off}.
    configurations = OrderedDict()

    browsers = ('firefox', 'chrome')
    turbos = ('true', 'false')

    # for configuration in itertools.product(browsers, turbos):
    for turbo in turbos:
        configurations[('firefox', turbo)] = {
            'extra_browsertime_args': [
                '--browser', 'firefox',
                '--firefox.android.package', 'org.mozilla.tv.firefox.gecko.debug',
                '--firefox.android.activity', 'org.mozilla.tv.firefox.MainActivity',
                '--firefox.android.intentArgument=-a',
                '--firefox.android.intentArgument=android.intent.action.VIEW',
                '--firefox.android.intentArgument=-d',
                '--firefox.android.intentArgument=data:text/html,',
                '--firefox.android.intentArgument=--ez',
                '--firefox.android.intentArgument=TURBO_MODE',
                '--firefox.android.intentArgument={}'.format(turbo),
            ],
        }

        configurations[('chrome', turbo)] = {
            'extra_browsertime_args': [
                '--browser', 'chrome',
                '--chrome.android.package', 'org.mozilla.tv.firefox.debug',
                # N.B.: chromedriver doesn't have an official way to pass intent
                # arguments, but it does have an unsanitized injection at
                # https://github.com/bayandin/chromedriver/blob/5a2b8f793391c80c9d1a1b0004f28be0a2be9ab2/chrome/adb_impl.cc#L212.
                '--chrome.android.activity', 'org.mozilla.tv.firefox.MainActivity --ez TURBO_MODE {} --es HTTP_PROXY_HOST {} --ei HTTP_PROXY_PORT {} -a android.intent.action.VIEW'.format(turbo, host, 4444),
            ],
        }

    if args.firefox_true_profile_template:
        configurations[('firefox', 'true')]['extra_browsertime_args'].extend(
            ['--firefox.profileTemplate', args.firefox_true_profile_template])

    if args.firefox_false_profile_template:
        configurations[('firefox', 'false')]['extra_browsertime_args'].extend(
            ['--firefox.profileTemplate', args.firefox_false_profile_template])

    if args.geckodriver:
        configurations[('firefox', 'true')]['extra_browsertime_args'].extend(['--firefox.geckodriverPath', args.geckodriver])
        configurations[('firefox', 'false')]['extra_browsertime_args'].extend(['--firefox.geckodriverPath', args.geckodriver])

    if args.chromedriver:
        configurations[('chrome', 'true')]['extra_browsertime_args'].extend(['--chrome.chromedriverPath', args.chromedriver])
        configurations[('chrome', 'false')]['extra_browsertime_args'].extend(['--chrome.chromedriverPath', args.chromedriver])

    wanted_configurations = []

    for configuration, extras in configurations.items():
        (browser, turbo) = configuration
        if browser not in args.browsers:
            if VERBOSE:
                print('Skipping configuration because browser is unwanted: {}'.format(configuration), file=sys.stderr)
                sys.stderr.flush()
            continue

        if turbo not in args.turbos:
            if VERBOSE:
                print('Skipping configuration because turbo is unwanted: {}'.format(configuration), file=sys.stderr)
                sys.stderr.flush()
            continue

        if VERBOSE:
            print('Testing configuration: {}'.format(configuration), file=sys.stderr)
            sys.stderr.flush()

        # print(configuration)

        record = list(shared_browsertime_args)
        record.extend(extras['extra_browsertime_args'])

        record.extend(['-n', str(1)])

        # TODO: proxy!

        replay = list(shared_browsertime_args)
        replay.extend(extras['extra_browsertime_args'])
        replay.extend(['-n', str(args.iterations)])

        live = list(replay)

        for variant in (record, replay):
            variant.extend(['--proxy.http', '{}:4444'.format(host)]) # XXX
            variant.extend(['--proxy.https', '{}:4444'.format(host)])

        for variant, name in ((record, 'record'), (replay, 'replay'), (live, 'live')):
            variant.extend(['--info.extra', json.dumps({'browser': browser, 'turbo': turbo, 'proxy': name})])

        extras['record'] = record
        extras['replay'] = replay
        # configurations[('firefox', 'false')]['live'] = live

        wanted_configurations.append(VehicleConfiguration(browser, turbo, record, replay, live))

    mitmdump_logfile = os.path.join(args.result_dir, 'mitmdump.log')
    ensureParentDir(mitmdump_logfile)

    mitmproxy_args = ['--listen-host',
                      host,
                      '--listen-port',
                      str(4444),
                      '-s',
                      'vendor/mitmproxy_portforward.py',
                      '--ssl-insecure']
    with with_wpr.process(
        ['mitmdump'] + mitmproxy_args,
        logfile=mitmdump_logfile) as mitmdump_proc:

        if mitmdump_proc.poll():
            raise RuntimeError("Port forwarding proxy failed: ", mitmdump_proc.poll())

        for url_index, url in enumerate(urls):
            url_log = log.new(url_index=url_index, url=url)
            url_log.info('testing URL')

            if args.wpr or args.wpr_root:
                wpr_configuration = WprConfiguration(args.wpr, args.wpr_root, shlex.split(args.wpr_args) + ['--host', host]) # '0.0.0.0'

                url_result_dir = os.path.join(args.result_dir,
                                              "url-{:02d}".format(url_index + 1),
                                              urllib.quote_plus(url))

                for vehicle_index, vehicle_configuration in enumerate(wanted_configurations):
                    vehicle_log = url_log.bind(vehicle_index=vehicle_index, vehicle_configuration=vehicle_configuration)
                    vehicle_log.info('Testing vehicle', browser=vehicle_configuration.browser, turbo=vehicle_configuration.turbo)

                    vehicle_result_dir = vehicle_configuration.result_dir(os.path.join(url_result_dir, "vehicle-{:02d}".format(vehicle_index + 1)))
                    try:
                        # if FOOTER:
                        #     FOOTER.clear()

                        # if FOOTER:
                        #     FOOTER.write([('green', 'url {:02d}/{:02d}'.format(url_index, len(urls))),
                        #                   ('green', 'vehicle {:02d}/{:02d}'.format(vehicle_index, len(wanted_configurations)))])

                        test_one_url(vehicle_configuration, wpr_configuration, vehicle_result_dir, url)
                    except RuntimeError as e:
                        error_file = os.path.join(vehicle_result_dir, "error")
                        ensureParentDir(error_file)
                        print(e, file=open(error_file, 'wt'))

                        if args.no_continue:
                            raise
            else:
                raise NotImplementedError
                # import pprint
                # pprint.pprint(live)

                # # XXX: logging.
                # logfile = os.path.join(result_dir, 'browsertime') # 'browsertime-{}-{}.log'.format(browser, turbo))
                # ensureParentDir(logfile)

                # with with_wpr.process(live, logfile=logfile) as browsertime_proc:
                #     browsertime_proc.wait()

            # url_log.info('Testing URL {} ... DONE', url)


if __name__ == '__main__':
    # structlog.configure(
    #     processors=[
    #         # structlog.stdlib.filter_by_level,
    #         structlog.stdlib.add_logger_name,
    #         structlog.stdlib.add_log_level,
    #         structlog.stdlib.PositionalArgumentsFormatter(),
    #         structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M.%S"),
    #         structlog.processors.StackInfoRenderer(),
    #         structlog.processors.format_exc_info,
    #         structlog.dev.ConsoleRenderer()  # <===
    #     ],
    #     context_class=dict,
    #     logger_factory=structlog.stdlib.LoggerFactory(),
    #     wrapper_class=structlog.stdlib.BoundLogger,
    #     cache_logger_on_first_use=True,
    # )

    sys.exit(main(sys.argv[1:]))
