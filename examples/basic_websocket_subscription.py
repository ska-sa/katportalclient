#!/usr/bin/env python
# Copyright (c) 2016 National Research Foundation (South African Radio Astronomy Observatory)
# BSD license - see LICENSE for details
"""Simple example demonstrating websocket subscription.

This example connects to katportal via a websocket.  It subscribes to
the specified sensor group names, and keeps printing out the published messages
received every few seconds.
"""
from __future__ import print_function

import argparse
import logging
import uuid

import tornado.gen

from builtins import str

from katportalclient import KATPortalClient


logger = logging.getLogger('katportalclient.example')
logger.setLevel(logging.INFO)


def on_update_callback(msg_dict):
    """Handler for every JSON message published over the websocket."""
    print("GOT message:")
    for key, value in list(msg_dict.items()):
        if key == 'msg_data':
            print('\tmsg_data:')
            for data_key, data_value in list(msg_dict['msg_data'].items()):
                print("\t\t{}: {}".format(data_key, data_value))
        else:
            print("\t{}: {}".format(key, value))


@tornado.gen.coroutine
def main():
    # Change URL to point to a valid portal node.
    # If you are not interested in any subarray specific information
    # (e.g. schedule blocks), then the number can be omitted, as below.
    portal_client = KATPortalClient('http://{}/api/client'.format(args.host),
                                    on_update_callback, logger=logger)

    # First connect to the websocket, before subscribing.
    yield portal_client.connect()

    # Use a namespace with a unique name when subscribing to avoid a
    # clash with existing namespaces.
    namespace = 'namespace_' + str(uuid.uuid4())

    # Subscribe to the namespace (async call) - no messages will be received yet,
    # as this is a new namespace.
    result = yield portal_client.subscribe(namespace)
    print("Subscription result: {} identifier(s).".format(result))

    # Set the sampling strategies for the sensors of interest, on our custom
    # namespace.  In this example, we are interested in a number of patterns,
    # e.g. any sensor with "mode" in the name.  The response messages will
    # be published to our namespace every 5 seconds.
    result = yield portal_client.set_sampling_strategies(
        namespace, args.sensors,
        'period 5.0')
    print("\nSet sampling strategies result: {}.\n".format(result))

    # Example:
    #  ./basic_websocket_subscription.py --host 127.0.0.1 pos_actual_pointm anc_mean_wind
    # Subscription result: 1 identifier(s).
    # GOT message:
    # 	msg_pattern: namespace_93f3e645-1818-4913-ae13-f4fbc6eacf31:*
    # 	msg_channel: namespace_93f3e645-1818-4913-ae13-f4fbc6eacf31:m011_pos_actual_pointm_azim
    # 	msg_data:
    # 		status: nominal
    # 		timestamp: 1486038182.71
    # 		value: -185.0
    # 		name: m011_pos_actual_pointm_azim
    # 		received_timestamp: 1486050055.89
    # GOT message:
    # 	msg_pattern: namespace_93f3e645-1818-4913-ae13-f4fbc6eacf31:*
    # 	msg_channel: namespace_93f3e645-1818-4913-ae13-f4fbc6eacf31:m011_pos_actual_pointm_elev
    # 	msg_data:
    # 		status: nominal
    # 		timestamp: 1486038182.71
    # 		value: 15.0
    # 		name: m011_pos_actual_pointm_elev
    # 		received_timestamp: 1486050055.89
    # ...
    # GOT message:
    # 	msg_pattern: namespace_93f3e645-1818-4913-ae13-f4fbc6eacf31:*
    # 	msg_channel: namespace_93f3e645-1818-4913-ae13-f4fbc6eacf31:anc_mean_wind_speed
    # 	msg_data:
    # 		status: nominal
    # 		timestamp: 1486050057.07
    # 		value: 4.9882065556
    # 		name: anc_mean_wind_speed
    # 		received_timestamp: 1486050057.13
    # ...
    #
    # The IOLoop will continue to run until the program is aborted.
    # Push Ctrl+C to stop.


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Subscribe to websocket and print messages to stdout for "
                    "matching sensor names.")
    parser.add_argument(
        '--host',
        default='127.0.0.1',
        help="hostname or IP of the portal server (default: %(default)s).")
    parser.add_argument(
        'sensors',
        metavar='sensor',
        nargs='+',
        help="list of sensor names or filter strings to request data for "
             "(examples: wind_speed azim elev)")
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

    # Start up the tornado IO loop:
    io_loop = tornado.ioloop.IOLoop.current()
    io_loop.add_callback(main)
    io_loop.start()
