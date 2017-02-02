#!/usr/bin/env python
###############################################################################
# SKA South Africa (http://ska.ac.za/)                                        #
# Author: cam@ska.ac.za                                                       #
# Copyright @ 2013 SKA SA. All rights reserved.                               #
#                                                                             #
# THIS SOFTWARE MAY NOT BE COPIED OR DISTRIBUTED IN ANY FORM WITHOUT THE      #
# WRITTEN PERMISSION OF SKA SA.                                               #
###############################################################################
"""Simple example demonstrating getting pointing information by supplying a
reference observer location and time.

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
    # [{u'target': u'Moon', u'slew_time': 53.6153013706, u'track_duration': 60.0, u'start_offset': 113.6153013706}]

    portal_client.set_reference_observer_config(
        longitude=10.0,
        latitude=10.0,
        altitude=10.0,
        timestamp=time.time() + 3600)  # one hour in the future

    results = yield portal_client.future_targets_detail(
        '{sb_id_code}'.format(**vars(args)))
    print results

    # Example output:
    # [{
    #     u'name': u'Moon',
    #     u'description': u'Moon,special',
    #     u'track_duration': 60.0,
    #     u'slew_time': 53.6153013706,
    #     u'start_offset': 113.6153013706,
    #     u'azel': [3.6399178505, 1.3919397593],
    #     u'astrometric_radec': [0.180696943, 0.0180189191],
    #     u'tags': [u'special'],
    #     u'apparent_radec': [0.1830730793, 0.0169845125],
    #     u'body_type': u'special',
    #     u'galactic': [2.0531028499, -1.0774995277],
    #     u'parallactic_angle': 0.49015412010000003,
    #     u'uvw_basis': [[0.996376853, -0.0150540303, 0.0837050956],
    #                    [0.0017334140000000002, 0.9875998825000001, 0.156982379],
    #                    [-0.08503036010000001, -0.15626851320000001, 0.9840477578000001]]
    # }]

    # To use the default array reference observer, call the set_reference_observer_config
    # with no parameters. This will also then default to using utc time to calculate the
    # pointing details
    portal_client.set_reference_observer_config()
    results = yield portal_client.future_targets_detail(
        '{sb_id_code}'.format(**vars(args)))
    print results


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
