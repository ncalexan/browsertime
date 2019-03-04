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

    for root, _, fs in os.walk(root):
        for f in fs:
            if f == 'browsertime.json':
                _, browser, turbo, _ = root.split('/', 3)
                turbo = turbo == 'true'

                path = os.path.join(root, f)
                if verbose > 0:
                    print('Processing {}...'.format(path), file=sys.stderr)

                try:
                    j = json.load(open(path, 'rt'))
                    for entry in j:
                        site = entry['info']['url'].lower()
                        for i, run in enumerate(entry['browserScripts']):
                            pageLoadTime = run['timings']['pageTimings']['pageLoadTime']
                            timestamp = entry['timestamps'][i]
                            yield (site, browser, turbo, i + 1, timestamp, pageLoadTime)
                except Exception as e:
                    print('Processing {}... ERROR: {}'.format(path, e), file=sys.stderr)

                if verbose > 0:
                    print('Processing {}... DONE'.format(path), file=sys.stderr)


# def complete(i):
#     runs = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
#     for run in i:
#         (site, browser, turbo, i, pageLoadTime) = run
#         runs[site][browser][turbo][(i, pageLoadTime)] = run

#     for _, site in runs.items():
#         complete = True
#         complete &= len(site.items()) == 2
#         for _, browser in site.items():
#             complete &= len(browser.items()) == 2
#             for _, turbo in browser.items():
#                 complete &= len(turbo.items()) == 4

#         for _, browser in site.items():
#             for _, turbo in browser.items():
#                 for _, run in turbo.items():
#                     yield (complete,) + run


def main(args):
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", "-D", default="browsertime-results",
                        help="Directory to crawl for results")
    parser.add_argument("--verbose", "-v", action='count',
                        help="Be verbose (can be repeated)")
    args = parser.parse_args(args)

    writer = csv.writer(sys.stdout)
    writer.writerow(('site', 'browser', 'turbo', 'run', 'timestamp', 'pageLoadTime'))
    writer.writerows(sorted(walk(args.dir, args.verbose)))


if __name__ == '__main__':
    main(sys.argv[1:])
