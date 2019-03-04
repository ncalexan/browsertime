#!/bin/env python

from __future__ import absolute_import, unicode_literals, print_function

import argparse
# import matplotlib.pyplot as plt
import pandas as pd
import os
import sys


def main(args):
    parser = argparse.ArgumentParser()
    parser.add_argument("--btr", default="btr.csv",
                        help="CSV of browsertime results")
    parser.add_argument("--nd", default="nd.csv",
                        help="CSV of nimbledroid results")
    parser.add_argument("--verbose", "-v", action='count',
                        help="Be verbose (can be repeated)")
    args = parser.parse_args(args)

    btr = pd.read_csv(args.btr)
    # nd = pd.read_csv(args.nd)

    for g in btr.drop(columns=['run']).groupby(['site', 'browser', 'turbo']):
        print(g)

    # print(pd.merge(btr, nd, on='site')[0:2])

    # writer = csv.writer(sys.stdout)
    # writer.writerow(('site', 'browser', 'turbo', 'run', 'pageLoadTime'))
    # writer.writerows(sorted(walk(args.dir, args.verbose)))


if __name__ == '__main__':
    main(sys.argv[1:])
