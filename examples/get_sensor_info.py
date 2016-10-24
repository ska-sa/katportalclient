#!/usr/bin/env python
###############################################################################
# SKA South Africa (http://ska.ac.za/)                                        #
# Author: cam@ska.ac.za                                                       #
# Copyright @ 2013 SKA SA. All rights reserved.                               #
#                                                                             #
# THIS SOFTWARE MAY NOT BE COPIED OR DISTRIBUTED IN ANY FORM WITHOUT THE      #
# WRITTEN PERMISSION OF SKA SA.                                               #
###############################################################################
"""Simple example demonstrating sensor information queries.

This example gets lists of sensor names in various ways, and gets the
detailed atttributes of a specific sensor.  It uses HTTP access to katportal,
not websocket access.
"""
import logging
import argparse

import tornado.gen

from katportalclient import KATPortalClient


logger = logging.getLogger('katportalclient.example')
logger.setLevel(logging.INFO)


@tornado.gen.coroutine
def main():
    # Change URL to point to a valid portal node.
    # If you are not interested in any subarray specific information
    # (e.g. schedule blocks), then the number can be omitted, as below.
    # Note: if on_update_callback is set to None, then we cannot use the
    #       KATPortalClient.connect() method (i.e. no websocket access).
    ## portal_client = KATPortalClient('http://127.0.0.1/api/client',
    ##                                on_update_callback=None, logger=logger)
    portal_client = KATPortalClient('http://{}/api/client'.format(args.host),
                                    on_update_callback=None, logger=logger)

    # Get the names of sensors matching the patterns
    sensor_names = yield portal_client.sensor_names(args.sensors)
    print "\nMatching sensor names for pattern {}: {}".format(args.sensors, sensor_names)

    # Get the names of sensors matching a pattern
    # pattern = 'anc_wind*.'
    # sensor_names = yield portal_client.sensor_names(pattern)
    # print "\nMatching sensor names for pattern {} : {}".format(pattern, sensor_names)
    # Example output:
    #   Matching sensor names: [u'anc_wind_device_status', u'anc_weather_device_status']

    # Get the names of sensors matching a pattern
    # pattern = 'anc_(mean|gust)_wind_speed'
    # sensor_names = yield portal_client.sensor_names(pattern)
    # print "\nMatching sensor names for pattern {} : {}".format(pattern, sensor_names)
    # Example output:
    #   Matching sensor names: [u'anc_mean_wind_speed', u'anc_gust_wind_speed']

    # Get the names of sensors matching a list of patterns
    # pattern = 'm01[12]_pos_request_base'
    # sensor_names = yield portal_client.sensor_names(pattern)
    # print "\nMatching sensor names for pattern {} : {}".format(pattern, sensor_names)
    # Example output (if sensors is 'm01[12]_pos_request_base'):
    #   Matching sensor names: [u'm011_pos_request_base_azim',
    #   u'm012_pos_request_base_ra', u'm012_pos_request_base_dec',
    #   u'm011_pos_request_base_ra', u'm012_pos_request_base_elev',
    #   u'm011_pos_request_base_dec', u'm012_pos_request_base_azim',
    #   u'm011_pos_request_base_elev']

    # Fetch the details for the sensors found.
    if len(sensor_names) == 0:
        print "No matching sensors found!"
    else:
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

    # Example: ./get_sensor_info.py --host devx.camlab.kat.ac.za anc_(mean|gust)_wind_speed
    #
    # Matching sensor names: [u'anc_mean_wind_speed', u'anc_gust_wind_speed']
    #
    # Detail for sensor anc_mean_wind_speed:
    # {'name': u'anc_mean_wind_speed', u'systype': u'mkat', 'component': u'anc',
    #   u'site': u'deva', u'katcp_name': u'anc.mean_wind_speed', u'params': u'[]',
    #   u'units': u'', u'type': u'float',
    #   u'description': u"Mean of  ['wind.wind-speed', 'weather.wind-speed']
    #                     in (600 * 1.0s) window"}
    #
    # Another Example: ./get_sensor_info.py --host devx.camlab.kat.ac.za anc_.*_wind_speed
    #
    # Matching sensor names for pattern ['anc_.*_wind_speed']: [u'anc_asc_wind_speed', u'anc_gust_wind_speed', u'anc_mean_wind_speed', u'anc_wind_wind_speed', u'anc_asccombo_wind_speed_2', u'anc_weather_wind_speed']
    

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Download sensor info and print to stdout.")
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
