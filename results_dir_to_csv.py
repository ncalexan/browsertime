#!/bin/env python

from __future__ import absolute_import, unicode_literals, print_function

from collections import defaultdict
import csv
import itertools
import json
import os
import sys
import argparse


def walk(root):
    """Collect pageLoadTime entries from files like
    `{root}/firefox/turbo-true/google.com/browsertime.json`"""

    for root, _, fs in os.walk(root):
        for f in fs:
            if f == 'browsertime.json':
                _, browser, turbo, _ = root.split('/', 3)
                turbo = turbo == 'true'

                j = json.load(open(os.path.join(root, f), 'rt'))
                for entry in j:
                    site = entry['info']['url'].lower()
                    for i, run in enumerate(entry['browserScripts']):
                        pageLoadTime = run['timings']['pageTimings']['pageLoadTime']
                        yield (site, browser, turbo, i, pageLoadTime)


def complete(i):
    runs = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    for run in i:
        (site, browser, turbo, i, pageLoadTime) = run
        runs[site][browser][turbo][(i, pageLoadTime)] = run

    for _, site in runs.items():
        complete = True
        complete &= len(site.items()) == 2
        for _, browser in site.items():
            complete &= len(browser.items()) == 2
            for _, turbo in browser.items():
                complete &= len(turbo.items()) == 4

        for _, browser in site.items():
            for _, turbo in browser.items():
                for _, run in turbo.items():
                    yield (complete,) + run


def main(args):
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", "-D", default="browsertime-results",
                        help="Directory to crawl for results")
    args = parser.parse_args(args)

    writer = csv.writer(sys.stdout)
    writer.writerow(('complete', 'site', 'browser', 'turbo', 'run', 'pageLoadTime'))
    writer.writerows(sorted(complete(walk(args.dir))))

if __name__ == '__main__':
    main(sys.argv[1:])
