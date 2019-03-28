#!/bin/env python

from __future__ import absolute_import, unicode_literals, print_function


from collections import defaultdict
import csv
import itertools
import json
import os
import sys
import argparse


def walk(root, verbose=0):
    """Collect pageLoadTime entries from files like
    `{root}/firefox/turbo-true/google.com/browsertime.json`"""

    def map_browser(browser):
        if browser == 'chrome':
            return 'WebView'
        if browser == 'firefox':
            return 'GeckoView'
        raise ValueError('Unrecognized browser: {}'.format(browser))

    for root, _, fs in os.walk(root):
        for f in fs:
            if f == 'browsertime.json':
                path = os.path.join(root, f)
                if verbose > 0:
                    print('Processing {}...'.format(path), file=sys.stderr)

                try:
                    j = json.load(open(path, 'rt'))
                    for entry in j:
                        site = entry['info']['url'].lower()
                        proxy = entry['info']['extra']['proxy']
                        browser = entry['info']['extra']['browser']
                        turbo = entry['info']['extra']['turbo']
                        for i, run in enumerate(entry['browserScripts']):
                            pageLoadTime = run['timings']['pageTimings']['pageLoadTime']
                            timestamp = entry['timestamps'][i]
                            yield {'site': site, 'browser': map_browser(browser), 'turbo': turbo,
                                   'proxy': proxy, 'timestamp': timestamp,
                                   'pageLoadTime': pageLoadTime}
                except Exception as e:
                    print('Processing {}... ERROR: {}'.format(path, e), file=sys.stderr)

                if verbose > 0:
                    print('Processing {}... DONE'.format(path), file=sys.stderr)


def main(args):
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", "-D", nargs='*', default=["browsertime-results"],
                        help="Directory or directories to crawl for results")
    parser.add_argument("--verbose", "-v", action='count',
                        help="Be verbose (can be repeated)")
    args = parser.parse_args(args)

    def walk_dirs(dirs):
        for i, d in enumerate(dirs):
            run_extras = json.load(open(os.path.join(d, 'run.json'), 'rt'))
            for measurement in walk(d, args.verbose):
                measurement.update(run_extras)
                measurement['run'] = i + 1
                yield measurement

    writer = csv.DictWriter(sys.stdout, ('device', 'run', 'site', 'browser', 'turbo', 'proxy', 'timestamp', 'pageLoadTime'))
    writer.writeheader()
    writer.writerows(walk_dirs(args.dir))


if __name__ == '__main__':
    main(sys.argv[1:])
