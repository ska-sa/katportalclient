#!/usr/bin/env python
# Copyright 2018 SKA South Africa (http://ska.ac.za/)
# BSD license - see COPYING for details
"""Simple example demonstrating retrieving the latest sensor value.

This example gets lists of sensor names, and gets the
latest value of a specific sensor.  It uses HTTP access to katportal.
"""
import logging
import argparse

import tornado.gen

from katportalclient import KATPortalClient
from katportalclient.client import SensorNotFoundError


logger = logging.getLogger('katportalclient.example')
logger.setLevel(logging.INFO)


@tornado.gen.coroutine
def main():
    # Change URL to point to a valid portal node.
    portal_client = KATPortalClient('http://{}/api/client'.format(args.host),
                                    on_update_callback=None, logger=logger)

    # Get the names of sensors matching the patterns
    # See examples/get_sensor_info.py for details on sensor name pattern matching
    sensor_names = yield portal_client.sensor_names(args.sensors)
    print "\nMatching sensor names for pattern {}: {}".format(args.sensors, sensor_names)

    # Fetch the details for the sensors found.
    if len(sensor_names) == 0:
        print "No matching sensors found!"
    else:
        for sensor_name in sensor_names:
            try:
                sensor_value = yield portal_client.sensor_value(sensor_name,
                                                                include_value_ts=True)
            except SensorNotFoundError, exc:
                print "\n", exc
                continue
            print "\nValue for sensor {}:".format(sensor_name)
            print sensor_value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Download latest sensor value and print to stdout.")
    parser.add_argument(
        '--host',
        default='127.0.0.1',
        help="hostname or IP of the portal server (default: %(default)s).")
    parser.add_argument(
        'sensors',
        metavar='sensor',
        nargs='+',
        help="list of sensor names or filter strings to request data for")
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
