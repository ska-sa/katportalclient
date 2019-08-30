#!/usr/bin/env python
# Copyright (c) 2019 National Research Foundation (South African Radio Astronomy Observatory)
# BSD license - see LICENSE for details
"""Simple example demonstrating queries of schedule block IDs using
a given valid capture block ID.
"""
from __future__ import print_function

import logging
import argparse

import tornado.gen

from katportalclient import KATPortalClient


logger = logging.getLogger('katportalclient.example')
logger.setLevel(logging.INFO)


@tornado.gen.coroutine
def main():
    # Change URL to point to a valid portal node.
    portal_client = KATPortalClient('http://{}/api/client'.
                                    format(args.host),
                                    on_update_callback=None, logger=logger)

    for capture_block_id in args.capture_block_ids:
        schedule_blocks = yield portal_client.sb_ids_by_capture_block(capture_block_id)
        print("\nSchedule block ID(s) for the Capture block ID {}:\n{}\n".format(capture_block_id, schedule_blocks))
        # ./get_sb_id_with_capture_block.py --host portal.mkat.karoo.kat.ac.za 1556745649
        # Example output:
        # Schedule block IDs for Capture block ID 1556745649:
        # [u'20190501-0001']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Download schedule block ID of a given capture block ID and print to stdout.")
    parser.add_argument(
        '--host',
        default='127.0.0.1',
        help="hostname or IP of the portal server (default: %(default)s).")
    parser.add_argument(
        'capture_block_ids',
        metavar='capture-block-id',
        nargs='+',
        help="capture block ID used to request associated schedule block ID(s).")
    parser.add_argument(
        '-v', '--verbose',
        dest='verbose', action="store_true",
        default=False,
        help="provide extremely verbose output.")
    args = parser.parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.WARNING)

    # Start up the tornado IO loop.
    # Only a single function to run once, so use run_sync() instead of start()
    io_loop = tornado.ioloop.IOLoop.current()
    io_loop.run_sync(main)
