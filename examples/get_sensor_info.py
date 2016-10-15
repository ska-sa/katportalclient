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
    portal_client = KATPortalClient('http://portal.mkat/api/client',
                                    on_update_callback=None, logger=logger)

    # Get the names of sensors matching a pattern
    sensor_names = yield portal_client.sensor_names('anc_w.*_device_status')
    print "\nMatching sensor names:", sensor_names
    # Example output:
    #   Matching sensor names: [u'anc_wind_device_status', u'anc_weather_device_status']

    # Get the names of sensors matching a list of patterns
    sensor_names = yield portal_client.sensor_names('m01[12]_pos_request_base')
    print "\nMatching sensor names:", sensor_names
    # Example output (if sensors is 'm01[12]_pos_request_base'):
    #   Matching sensor names: [u'm011_pos_request_base_azim',
    #   u'm012_pos_request_base_ra', u'm012_pos_request_base_dec',
    #   u'm011_pos_request_base_ra', u'm012_pos_request_base_elev',
    #   u'm011_pos_request_base_dec', u'm012_pos_request_base_azim',
    #   u'm011_pos_request_base_elev']

    # Fetch the details for one of the sensors found.
    if len(sensor_names) > 0:
        sensor_detail = yield portal_client.sensor_detail(sensor_names[0])
        print "\nDetail for sensor {}:\n{}\n".format(sensor_names[0], sensor_detail)
        # Example output:
        #   Detail for sensor m011_pos_request_base_azim:
        #   {'name': u'm011_pos_request_base_azim', u'systype': u'mkat',
        #    'component': u'm011', u'site': u'deva',
        #    u'katcp_name': u'm011.pos.request-base-azim',
        #    u'params': u'[-195.0, 370.0]', u'units': u'deg', u'type': u'float',
        #    u'description': u'Requested target azimuth'}

if __name__ == '__main__':
    # Start up the tornado IO loop.
    # Only a single function to run once, so use run_sync() instead of start()
    io_loop = tornado.ioloop.IOLoop.current()
    io_loop.run_sync(main)
