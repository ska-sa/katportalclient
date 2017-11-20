#!/usr/bin/env python
# Copyright 2016 SKA South Africa (http://ska.ac.za/)
# BSD license - see COPYING for details
"""Simple example demonstrating sensor information and history queries.

This example gets lists of sensor names in various ways, and gets the
detailed atttributes of a specific sensor.  It also gets the time history
samples for a few sensors.
"""
import logging
import argparse
import time
from datetime import datetime

import tornado.gen

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
    print "\nMatching sensor names: {}".format(sensor_names)
    # Example output (if sensors is 'm01[12]_pos_request_base'):
    #   Matching sensor names: [u'm011_pos_request_base_azim',
    #   u'm012_pos_request_base_ra', u'm012_pos_request_base_dec',
    #   u'm011_pos_request_base_ra', u'm012_pos_request_base_elev',
    #   u'm011_pos_request_base_dec', u'm012_pos_request_base_azim',
    #   u'm011_pos_request_base_elev']

    # Fetch the details for the sensors found.
    for sensor_name in sensor_names:
        sensor_detail = yield portal_client.sensor_detail(sensor_name)
        print "\nDetail for sensor {}:".format(sensor_name)
        for key in sensor_detail:
            print "    {}: {}".format(key, sensor_detail[key])
        # Example output:
        #   Detail for sensor m011_pos_request_base_azim:
        #       name: m011_pos_request_base_azim
        #       systype: mkat
        #       component: m011
        #       site: deva
        #       katcp_name: m011.pos.request-base-azim
        #       params: [-195.0, 370.0]
        #       units: deg
        #       type: float
        #       description: Requested target azimuth

    num_sensors = len(sensor_names)
    if num_sensors == 0:
        print "\nNo matching sensors found - no history to request!"
    else:
        print ("\nRequesting history for {} sensors, from {} to {}"
               .format(
                   num_sensors,
                   datetime.utcfromtimestamp(
                       args.start).strftime('%Y-%m-%dT%H:%M:%SZ'),
                   datetime.utcfromtimestamp(args.end).strftime('%Y-%m-%dT%H:%M:%SZ')))
        if len(sensor_names) == 1:
            # Request history for just a single sensor - result is timestamp, value, status
            #    If value timestamp is also required, then add the additional argument: include_value_ts=True
            #    result is then timestmap, value_timestmap, value, status
            history = yield portal_client.sensor_history(
                sensor_names[0], args.start, args.end, timeout_sec=args.timeout)
            histories = {sensor_names[0]: history}
        else:
            # Request history for all the sensors - result is timestamp, value, status
            #    If value timestamp is also required, then add the additional argument: include_value_ts=True
            #    result is then timestmap, value_timestmap, value, status
            histories = yield portal_client.sensors_histories(
                sensor_names, args.start, args.end, timeout_sec=args.timeout)

        print "Found {} sensors.".format(len(histories))
        for sensor_name, history in histories.items():
            num_samples = len(history)
            print "History for: {} ({} samples)".format(sensor_name, num_samples)
            if num_samples > 0:
                print "\tindex,timestamp,value,status"
                for count in range(0, num_samples, args.decimate):
                    print "\t{},{}".format(count, history[count].csv())

    # Example: ./get_sensor_history.py -s 1476164224 -e 1476164229 anc_mean_wind_speed
    #
    # Matching sensor names: [u'anc_mean_wind_speed']
    #
    # Detail for sensor anc_mean_wind_speed:
    # {'name': u'anc_mean_wind_speed', u'systype': u'mkat', 'component': u'anc',
    #   u'site': u'deva', u'katcp_name': u'anc.mean_wind_speed', u'params': u'[]',
    #   u'units': u'', u'type': u'float',
    #   u'description': u"Mean of  ['wind.wind-speed', 'weather.wind-speed']
    #                     in (600 * 1.0s) window"}
    #
    # Requesting history for 1 sensors, from 2016-10-11T05:37:04Z to 2016-10-11T05:37:09Z
    # Found 1 sensors.
    # History for: anc_mean_wind_speed (5 samples)
    #    index,timestamp,value,status
    #    0,1476164224.43,5.07571614843,nominal
    #    1,1476164225.43,5.07574851017,nominal
    #    2,1476164226.43,5.0753700255,nominal
    #    3,1476164227.43,5.07593196431,nominal
    #    4,1476164228.43,5.0758410904,nominal


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
        '-r', '--timeout',
        type=int,
        default=60,
        help="maximum time allowed for query [sec] (default: %(default)s).")
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
    args = parser.parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.WARNING)

    # Start up the tornado IO loop.
    # Only a single function to run once, so use run_sync() instead of start()
    io_loop = tornado.ioloop.IOLoop.current()
    io_loop.run_sync(main)
