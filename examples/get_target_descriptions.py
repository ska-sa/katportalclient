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
    client = KATPortalClient('http://localhost/api/client',
                             on_update_callback=None, logger=logger)

    # Get the pointing details of a set of targets from a specified
    # reference observer location and time.
    results = yield client.get_target_descriptions(
        targets='Sun,Jupiter,Moon,Saturn',
        longitude=10.0,
        latitude=10.0,
        altitude=10.0,
        timestamp=time.time() + 3600)  # one hour in the future

    print results

    # Example output:
    # [{u'apparent_radec': [5.4887616314, -0.29992498700000003],
    #   u'astrometric_radec': [5.4847563805, -0.3010704971],
    #   u'azel': [4.4004411697, 0.0379281938],
    #   u'body_type': u'special',
    #   u'description': u'Sun, special',
    #   u'galactic': [0.529324994, -0.6162473516],
    #   u'name': u'Sun',
    #   u'parallactic_angle': 1.3759373506,
    #   u'tags': [u'special'],
    #   u'uvw_basis': [[0.09444946950000001, -0.1716449975, 0.9806208710000001],
    #    [-0.2942402405, 0.9362039477, 0.1922104296],
    #    [-0.9510530893, -0.30669229400000003, 0.0379191009]]},
    #  {u'apparent_radec': [3.5236462803, -0.1338425836],
    #   u'astrometric_radec': [3.5197356490000002, -0.1323132089],
    #   u'azel': [1.4582693576999999, -1.2722665070999999],
    #   u'body_type': u'special',
    #   u'description': u'Jupiter, special',
    #   u'galactic': [5.5499747102, 0.9469744139],
    #   u'name': u'Jupiter',
    #   u'parallactic_angle': -1.4119492999999999,
    #   u'tags': [u'special'],
    #   u'uvw_basis': [[-0.9555055370000001, 0.051833308200000004, -0.2903833274],
    #    [0.039950485200000004, 0.9981095051000001, 0.0467051874],
    #    [0.2922552436, 0.0330261103, -0.9557699245000001]]},
    #  {u'apparent_radec': [6.2454304801, -0.0559296419],
    #   u'astrometric_radec': [6.2526110484, -0.053966023200000005],
    #   u'azel': [4.4375019073, 0.8184230924],
    #   u'body_type': u'special',
    #   u'description': u'Moon, special',
    #   u'galactic': [1.5751063885, -1.0855229806],
    #   u'name': u'Moon',
    #   u'parallactic_angle': 1.2510601122,
    #   u'tags': [u'special'],
    #   u'uvw_basis': [[0.7523615662, -0.1143044787, 0.6487577050000001],
    #    [-0.0368902681, 0.9759746871, 0.2147382554],
    #    [-0.6577166425000001, -0.18549365580000002, 0.7300691213]]},
    #  {u'apparent_radec': [4.610326769, -0.3846675644],
    #   u'astrometric_radec': [4.6059450635, -0.3845379545],
    #   u'azel': [4.3407421112, -0.7886252403],
    #   u'body_type': u'special',
    #   u'description': u'Saturn, special',
    #   u'galactic': [0.0816073528, 0.0971225325],
    #   u'name': u'Saturn',
    #   u'parallactic_angle': 1.7129354285,
    #   u'tags': [u'special'],
    #   u'uvw_basis': [[-0.7062240338, -0.1212548148, 0.6975276941],
    #    [-0.26455279870000004, 0.9590535727, -0.10113387880000001],
    #    [-0.6567034573, -0.2559560795, -0.7093849833]]}]

if __name__ == '__main__':
    # Start up the tornado IO loop.
    # Only a single function to run once, so use run_sync() instead of start()
    io_loop = tornado.ioloop.IOLoop.current()
    io_loop.run_sync(main)
