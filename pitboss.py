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

import with_wpr


def get_ip():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Doesn't even have to be reachable.
        s.connect(('10.255.255.255', 1))
        return s.getsockname()[0]
    except:
        return '127.0.0.1'
    finally:
        s.close()


def main(args):
    default_root = os.path.join(
        os.path.abspath(os.path.dirname(__file__)), 'docker', 'webpagereplay')

    parser = argparse.ArgumentParser()
    parser.add_argument('--verbose', '-v', action='count',
                        help='Be verbose (can be repeated)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Echo commands but do not execute')
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
                        default='/Users/nalexander/Mozilla/gecko/target/debug/geckodriver',
                        # default=None,
                        # required=True, # XXX
                        help='geckodriver binary.')
    parser.add_argument('--chromedriver',
                        default='/Users/nalexander/Downloads/chromedriver-2.46', # XXX
                        # default=None,
                        # required=True,
                        help='chromedriver binary.')

    # parser.add_argument('--firefox-true-profile-template',
    #                     default=None,
    #                     help='Gecko profile template directory to use when turbo is true.')
    # parser.add_argument('--firefox-false-profile-template',
    #                     default=None,
    #                     help='Gecko profile template directory to use when turbo is false.')

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

    parser.add_argument('urls', nargs='*', help='URLs') # xxx

    # parser.add_argument('url', help='URL') # xxx

    args = parser.parse_args(args)

    global VERBOSE
    VERBOSE = args.verbose
    with_wpr.VERBOSE = VERBOSE

    # print(args)

    import yaml
    import jsone

    config = yaml.safe_load(open('racetrack.yaml', 'rt').read())
    # print(yaml.dump(config))

    print(get_ip)
    http_proxy_host = args.wpr_host or (get_ip())

    context = {
        'geckodriver': args.geckodriver or '',
        'chromedriver': args.chromedriver or '',
        'verbosity_flag': '-' + ('v' * (1 + (args.verbose or 0))), # XXX.
        'user': 'nalexander', # XXX.
        'http_proxy_host': http_proxy_host,
        'http_proxy_port': '4040',
    }

    data = jsone.render(config, context)

    racetrack = data['racetrack']

    named_vehicles = {}

    def flatten(vehicle):
        base = vehicle.pop('from', None)
        if not base:
            return vehicle
        return jsone.render({'$mergeDeep': [flatten(base), vehicle]}, context)

    for vehicle in racetrack['vehicles']:
        flattened = flatten(vehicle)
        name = flattened.get('name', None)
        if name:
            named_vehicles[name] = flattened

    print(yaml.dump(named_vehicles))

    # print(yaml.dump(racetrack))

    # TODO: use voluptuous.
    if not racetrack['proxy']:
        raise ValueError('no proxy')

    if not racetrack['proxy']['type'] == 'wpr':
        raise ValueError('proxy type must be wpr')

    if not racetrack['proxy']['record'] == True:
        raise ValueError('proxy must record')

    if not racetrack['proxy']['replay'] == True:
        raise ValueError('proxy must replay')

    race = data['race']

    urls = race['urls']

    for url in args.urls:
        if url.startswith('@'):
            urls.extend(line.strip() for line in open(url[1:], 'rt') if line.strip() and not line.strip().startswith('#'))
        else:
            urls.append(url)

    for url in urls:
        if urllib.parse.urlparse(url).scheme not in ('http', 'https'):
            raise ValueError('URL scheme is not http(s): {}'.format(url))

    if os.path.exists(args.result_dir) and not args.force:
        raise ValueError('Results directory exists with no --force flag: {}', args.result_dir)

    race_vehicles = [named_vehicles[name] for name in sorted(race['vehicle_names'])]

    for url_index, url in enumerate(urls):
        # url_log = log.new(url_index=url_index, url=url)
        # url_log.info('testing URL')

        url_result_dir = os.path.join(args.result_dir,
                                      "{:02d}-{}".format(url_index + 1, urllib.parse.quote_plus(url)))

        for vehicle_index, vehicle in enumerate(race_vehicles):
            vehicle_result_dir = os.path.join(url_result_dir, "{:02d}-{}".format(vehicle_index + 1, vehicle['name']))
            # print(vehicle_result_dir)

            record = vehicle['args'] + ['--resultDir', os.path.join(vehicle_result_dir, 'record'), '-n', '1', url]
            # print(record)

            for arg in record:
                print(arg, shlex.quote(arg))

            replay = vehicle['args'] + ['--resultDir', os.path.join(vehicle_result_dir, 'replay'), '-n', str(args.iterations), url]

            cmd = [sys.executable, 'with_wpr.py', '-v'] + \
            (['--dry-run'] if args.dry_run else []) + \
            ['--output-prefix', vehicle_result_dir if vehicle_result_dir.endswith(os.sep) else vehicle_result_dir + os.sep,
             '--wpr', '/Users/nalexander/Downloads/wpr-go/wpr-macosx64',
             '--record', ' '.join(shlex.quote(arg) for arg in record),
             '--replay', ' '.join(pipes.quote(arg) for arg in replay),
             '--wpr-args', '--host {} --https_cert_file /Users/nalexander/.mitmproxy/mitmproxy-ca-cert.pem --https_key_file /Users/nalexander/.mitmproxy/mitmproxy-ca-key.pem'.format(http_proxy_host)] # XXX

            with with_wpr.process(cmd, prefix='with_wpr', logfile=os.path.join(vehicle_result_dir, 'with_wpr.log')) as with_wpr_proc:
                try:
                    if with_wpr_proc.poll():
                        raise RuntimeError("with_wpr failed: ", with_wpr_proc.poll())

                    status = with_wpr_proc.wait()
                    print("XXX", status)
                finally:
                    if with_wpr_proc.poll():
                        raise RuntimeError("with_wpr failed: ", with_wpr_proc.poll())
                    else:
                        with_wpr_proc.kill(signal.SIGINT)

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
