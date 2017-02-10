#!/usr/bin/env python
###############################################################################
# SKA South Africa (http://ska.ac.za/)                                        #
# Author: cam@ska.ac.za                                                       #
# Copyright @ 2013 SKA SA. All rights reserved.                               #
#                                                                             #
# THIS SOFTWARE MAY NOT BE COPIED OR DISTRIBUTED IN ANY FORM WITHOUT THE      #
# WRITTEN PERMISSION OF SKA SA.                                               #
###############################################################################
"""Simple example demonstrating getting future pointing information by supplying
a schedule block id code.

This example uses HTTP access to katportal, not websocket access.
"""
import logging
import argparse
import time

import tornado.gen

from katportalclient import KATPortalClient


logger = logging.getLogger('katportalclient.example')
logger.setLevel(logging.INFO)


@tornado.gen.coroutine
def main():
    # Change URL to point to a valid portal node.  Subarray can be 1 to 4.
    # Note: if on_update_callback is set to None, then we cannot use the
    #       KATPortalClient.connect() method (i.e. no websocket access).
    portal_client = KATPortalClient('http://{host}/api/client/1'.format(**vars(args)),
                                    on_update_callback=None, logger=logger)

    results = yield portal_client.future_targets(
        '{sb_id_code}'.format(**vars(args)))
    print results

    # Example output:
    # [
    #     {
    #         "track_start_offset":39.8941187859,
    #         "target":"PKS 0023-26 | J0025-2602 | OB-238, radec, 0:25:49.16, -26:02:12.6, (1410.0 8400.0 -1.694 2.107 -0.4043)",
    #         "track_duration":20.0
    #     },
    #     {
    #         "track_start_offset":72.5947952271,
    #         "target":"PKS 0043-42 | J0046-4207, radec, 0:46:17.75, -42:07:51.5, (400.0 2000.0 3.12 -0.7)",
    #         "track_duration":20.0
    #     },
    #     {
    #         "track_start_offset":114.597304821,
    #         "target":"PKS 0408-65 | J0408-6545, radec, 4:08:20.38, -65:45:09.1, (1410.0 8400.0 -3.708 3.807 -0.7202)",
    #         "track_duration":20.0
    #     }
    # ]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Gets the target list and target pointing descriptions "
                    "from katportal catalogues.")
    parser.add_argument(
        '--host',
        default='127.0.0.1',
        help="hostname or IP of the portal server (default: %(default)s).")
    parser.add_argument(
        '-s', '--sb-id-code',
        default=None,
        dest='sb_id_code',
        help="The schedule block id code to load the future targets list from")
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
