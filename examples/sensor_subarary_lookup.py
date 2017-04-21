#!/usr/bin/env python
###############################################################################
# SKA South Africa (http://ska.ac.za/)                                        #
# Author: cam@ska.ac.za                                                       #
# Copyright @ 2013 SKA SA. All rights reserved.                               #
#                                                                             #
# THIS SOFTWARE MAY NOT BE COPIED OR DISTRIBUTED IN ANY FORM WITHOUT THE      #
# WRITTEN PERMISSION OF SKA SA.                                               #
###############################################################################
"""Simple example demonstrating the use of the sensor_subarray_lookup method.
This method gets the full sensor name based on a generic component and sensor
name, for a given subarray. This method will return a failed katcp response if
the given subarray is not in the 'active' or 'initialising' state.

This example uses HTTP access to katportal, not websocket access.
"""
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
    portal_client = KATPortalClient('http://{host}/api/client/1'.format(**vars(args)),
                                    on_update_callback=None, logger=logger)

    lookup_args = vars(args)
    results = yield portal_client.sensor_subarray_lookup(
        sub_nr=lookup_args['sub_nr'],
        component=lookup_args['component'],
        sensor=lookup_args['sensor'],
        return_katcp_name=lookup_args['return_katcp_name'].lower() in ['true', '1'])
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
        '-n', '--sub-nr',
        dest='sub_nr',
        help="The subarray that the component is assigned to.")
    parser.add_argument(
        '-c', '--component',
        dest='component',
        help="Component containing the sensor to be looked up.")
    parser.add_argument(
        '-s', '--sensor',
        dest='sensor',
        help="The sensor to be looked up.")
    parser.add_argument(
        '-k', '--return_katcp-name',
        default='False',
        dest='return_katcp_name',
        help="Whether to return the katcp name or the python normalised name.")
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
