#!/usr/bin/env python
# Copyright 2016 SKA South Africa (http://ska.ac.za/)
# BSD license - see COPYING for details
"""Simple example demonstrating sensor information and history queries.

This example gets lists of sensor names in various ways, and gets the
detailed atttributes of a specific sensor.  It also gets the time history
samples for a few sensors.
"""
from __future__ import print_function

import logging
import argparse
import time

import tornado.gen

from builtins import range
from datetime import datetime

from katportalclient import KATPortalClient


logger = logging.getLogger('katportalclient.example')


@tornado.gen.coroutine
def main():
    # Change URL to point to a valid portal node.
    # If you are not interested in any subarray specific information
    # (e.g. schedule blocks), then the number can be omitted, as below.
    # Note: if on_update_callback is set to None, then we cannot use the
    #       KATPortalClient.connect() and subscribe() methods here.
    portal_client = KATPortalClient('http://{host}/api/client'.format(**vars(args)),
                                    on_update_callback=None, logger=logger)

    # Get the names of sensors matching the patterns
    sensor_names = yield portal_client.sensor_names(args.sensors)
    print("\nMatching sensor names: {}".format(sensor_names))
    # Example output (if sensors is 'm01[12]_pos_request_base'):
    #   Matching sensor names: [u'm011_pos_request_base_azim',
    #   u'm012_pos_request_base_ra', u'm012_pos_request_base_dec',
    #   u'm011_pos_request_base_ra', u'm012_pos_request_base_elev',
    #   u'm011_pos_request_base_dec', u'm012_pos_request_base_azim',
    #   u'm011_pos_request_base_elev']

    # Fetch the details for the sensors found.
    for sensor_name in sensor_names:
        sensor_detail = yield portal_client.sensor_detail(sensor_name)
        print("\nDetail for sensor {}:".format(sensor_name))
        for key in sorted(sensor_detail):
            print("    {}: {}".format(key, sensor_detail[key]))
        # Example output:
        #   Detail for sensor m011_pos_request_base_azim:
        #       component: m011
        #       description: Requested target azimuth
        #       katcp_name: m011.pos.request-base-azim
        #       name: m011_pos_request_base_azim
        #       params: [-195.0, 370.0]
        #       site: deva
        #       systype: mkat
        #       type: float
        #       units: deg

    num_sensors = len(sensor_names)
    if num_sensors == 0:
        print("\nNo matching sensors found - no history to request!")
    else:
        print ("\nRequesting history for {} sensors, from {} to {}"
               .format(
                   num_sensors,
                   datetime.utcfromtimestamp(
                       args.start).strftime('%Y-%m-%dT%H:%M:%SZ'),
                   datetime.utcfromtimestamp(args.end).strftime('%Y-%m-%dT%H:%M:%SZ')))
        value_time = args.include_value_time
        if len(sensor_names) == 1:
            # Request history for just a single sensor - result is
            # sample_time, value, status
            #    If value timestamp is also required, then add the additional argument:
            #        include_value_time=True
            #    result is then sample_time, value_time, value, status
            history = yield portal_client.sensor_history(
                sensor_names[0], args.start, args.end,
                include_value_ts=value_time)
            histories = {sensor_names[0]: history}
        else:
            # Request history for all the sensors - result is sample_time, value, status
            #    If value timestamp is also required, then add the additional argument:
            #        include_value_time=True
            #    result is then sample_time, value_time, value, status
            histories = yield portal_client.sensors_histories(sensor_names, args.start,
                                                              args.end,
                                                              include_value_ts=value_time)

        print("Found {} sensors.".format(len(histories)))
        for sensor_name, history in list(histories.items()):
            num_samples = len(history)
            print("History for: {} ({} samples)".format(sensor_name, num_samples))
            if num_samples > 0:
                for count in range(0, num_samples, args.decimate):
                    item = history[count]
                    if count == 0:
                        print("\tindex,{}".format(",".join(item._fields)))
                    print("\t{},{}".format(count, item.csv()))

    # Example: ./get_sensor_history.py -s 1522756324 -e 1522759924 sys_watchdogs_sys
    # Matching sensor names: [u'sys_watchdogs_sys']
    # Detail for sensor sys_watchdogs_sys:
    # attributes: {u'component': u'sys', u'original_name': u'sys.watchdogs.sys', u'params': u'[0, 4294967296]', u'description': u'Count of watchdogs received from component sys on 10.8.67.220:2025', u'type': u'integer'}
    # component: sys
    # name: sys_watchdogs_sys
    # Requesting history for 1 sensors, from 2018-04-03T11:52:08Z to 2018-04-03T12:52:08Z
    # Found 1 sensors.
    # History for: sys_watchdogs_sys (360 samples)
    #	index,sample_time,value,status
    #	0,1522756329.5110459328,42108,nominal
    #	1,1522756339.511122942,42109,nominal
    #	2,1522756349.5113239288,42110,nominal
    #	3,1522756359.5115270615,42111,nominal
    #	4,1522756369.5126268864,42112,nominal
    #	5,1522756379.5129699707,42113,nominal
    #	6,1522756389.513215065,42114,nominal
    #	7,1522756399.514425993,42115,nominal
    #	8,1522756409.5146770477,42116,nominal
    #	9,1522756419.5149009228,42117,nominal


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Downloads sample histories and prints to stdout.")
    parser.add_argument(
        '--host',
        default='127.0.0.1',
        help="hostname or IP of the portal server (default: %(default)s).")
    parser.add_argument(
        '-s', '--start',
        default=time.time() - 3600,
        type=int,
        help="start time of sample query [sec since UNIX epoch] (default: 1h ago).")
    parser.add_argument(
        '-e', '--end',
        type=int,
        default=time.time(),
        help="end time of sample query [sec since UNIX epoch] (default: now).")
    parser.add_argument(
        '-d', '--decimate',
        type=int,
        metavar='N',
        default=1,
        help="decimation level - only every Nth sample is output (default: %(default)s).")
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
    parser.add_argument(
        '-i', '--include-value-time',
        dest="include_value_time", action="store_false",
        help="include value timestamp")

    args = parser.parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.WARNING)

    # Start up the tornado IO loop.
    # Only a single function to run once, so use run_sync() instead of start()
    io_loop = tornado.ioloop.IOLoop.current()
    io_loop.run_sync(main)
