#!/usr/bin/env python
# Copyright 2016 SKA South Africa (http://ska.ac.za/)
# BSD license - see COPYING for details
"""Simple example demonstrating queries of schedule block IDs using
the capture block ID.

This example uses HTTP access to katportal, not websocket access.  It uses a
specific capture block ID when initialising the KATPortalClient.
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
    # Change URL to point to a valid portal node.  Subarray can be 1 to 4.
    # Note: if on_update_callback is set to None, then we cannot use the
    #       KATPortalClient.connect() method (i.e. no websocket access).
    portal_client = KATPortalClient('http://{}/api/client'.
                                    format(args.host),
                                    on_update_callback=None, logger=logger)

    # Note: cb_ids is a list that contains capture block IDs, Session assigns
    # an integer as cb_id on site.
    cb_ids = ['1556745649']
    if len(cb_ids) > 0:
        cb_details = yield portal_client.sb_ids_by_capture_block(cb_ids[0])
        print("\nSchedule block IDs for Capture block ID {}:\n{}\n".format(cb_ids[0], cb_details))
    else:
        print('No SB IDs found!')
    # ./get_sb_id_with_capture_block.py --host portal.mkat.karoo.kat.ac.za -c 1556745649
    # Example output:
        # Schedule block IDs for Capture block ID 1556745649:
        # [u'20190501-0001']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Download schedule block info for a subarray and print to stdout.")
    parser.add_argument(
        '--host',
        default='127.0.0.1',
        help="hostname or IP of the portal server (default: %(default)s).")
    parser.add_argument(
        '-c', '--capture_block_id',
        default='1',
        type=int,
        help="subarray number (1, 2, 3, or 4) to request schedule for "
             "(default: %(default)s).")
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
