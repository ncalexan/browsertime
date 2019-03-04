#!/bin/env python

from __future__ import absolute_import, unicode_literals, print_function

import csv
import json
import os
import sys
import argparse

# def walk(root):
#     """Collect pageLoadTime entries from files like
#     `{root}/firefox/turbo-true/google.com/browsertime.json`"""
                
#     for root, _, fs in os.walk(root):
#         for f in fs:
#             if f == 'browsertime.json':
#                 _, browser, turbo, site = root.split('/')
#                 _, turbo = turbo.split('-')
#                 turbo = turbo == 'true'

#                 j = json.load(open(os.path.join(root, f), 'rt'))
#                 for entry in j:
#                     for i, run in enumerate(entry['browserScripts']):
#                         pageLoadTime = run['timings']['pageTimings']['pageLoadTime']
#                         yield (site, browser, turbo, i, pageLoadTime)

def main(args):
    parser = argparse.ArgumentParser()
    # parser.add_argument("--dir", "-D", default="browsertime-results",
    #                     help="Directory to crawl for results")
    args = parser.parse_args(args)

    def to_msecs(s):
        return int(1000 * float(s))

    def read():
        reader = csv.DictReader(sys.stdin)
        for row in reader:
            site = row['Websites'].lower()
            if not site.startswith('http'):
                site = 'http://' + site
            yield (site, 'firefox', True, 0, to_msecs(row['Cube_GV_TPON']))
            yield (site, 'firefox', False, 0, to_msecs(row['Cube_GV_TPOFF']))
            yield (site, 'chrome', True, 0, to_msecs(row['Cube_WV_TPON']))
            yield (site, 'chrome', False, 0, to_msecs(row['Cube_WV_TPOFF']))

    writer = csv.writer(sys.stdout)
    writer.writerow(('site', 'browser', 'turbo', 'run', 'pageLoadTime'))
    writer.writerows(sorted(read()))


if __name__ == '__main__':
    main(sys.argv[1:])
