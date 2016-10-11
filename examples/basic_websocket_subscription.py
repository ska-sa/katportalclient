#!/usr/bin/env python
###############################################################################
# SKA South Africa (http://ska.ac.za/)                                        #
# Author: cam@ska.ac.za                                                       #
# Copyright @ 2013 SKA SA. All rights reserved.                               #
#                                                                             #
# THIS SOFTWARE MAY NOT BE COPIED OR DISTRIBUTED IN ANY FORM WITHOUT THE      #
# WRITTEN PERMISSION OF SKA SA.                                               #
###############################################################################
"""Simple example demonstrating websocket subscription.

This example connects to katportal via a websocket.  It subscribes to
a few sensor group names, and keeps printing out the published messages
received every few seconds.
"""

import logging
import uuid

import tornado.gen

from katportalclient import KATPortalClient


logger = logging.getLogger('katportalclient.example')
logger.setLevel(logging.INFO)


def on_update_callback(msg):
    """Handler for every JSON message published over the websocket."""
    print 'GOT:', msg


@tornado.gen.coroutine
def main(logger):
    # Change URL to point to a valid portal node.
    # If you are not interested in any subarray specific information
    # (e.g. schedule blocks), then the number can be omitted, as below.
    portal_client = KATPortalClient('http://portal.mkat/api/client',
                                    on_update_callback, logger=logger)

    # First connect to the websocket, before subscribing.
    yield portal_client.connect()

    # Use a namespace with a unique name when subscribing to avoid a
    # clash with existing namespaces.
    namespace = 'namespace_' + str(uuid.uuid4())

    # Subscribe to the namespace (async call) - no messages will be received yet,
    # as this is a new namespace.
    result = yield portal_client.subscribe(namespace)
    print "Subscription result: {} identifier(s).".format(result)
    # Example output:
    #   Subscription result: 1 identifier(s).

    # Set the sampling strategies for the sensors of interest, on our custom
    # namespace.  In this example, we are interested in a number of patterns,
    # e.g. any sensor with "mode" in the name.  The response messages will
    # be published to our namespace every 5 seconds.
    result = yield portal_client.set_sampling_strategies(
        namespace, ['mode', 'azim', 'elev', 'sched_observation_schedule'],
        'period 5.0')
    print "Set sampling strategies result: {}.\n".format(result)
    # Example output, printed by the callback function on_update_callback():
    #  GOT: []
    #  GOT: {u'msg_pattern': u'namespace_714a6f67-c170-4742-815a-00a7f5dcf8cd:*', u'msg_channel': u'namespace_714a6f67-c170-4742-815a-00a7f5dcf8cd:agg_m011_mode_not_error', u'msg_data': {u'status': u'nominal', u'timestamp': 1476111202.57672, u'value': True, u'name': u'agg_m011_mode_not_error', u'received_timestamp': 1476111202.669989}}
    #  GOT: {u'msg_pattern': u'namespace_714a6f67-c170-4742-815a-00a7f5dcf8cd:*', u'msg_channel': u'namespace_714a6f67-c170-4742-815a-00a7f5dcf8cd:agg_m022_mode_not_error', u'msg_data': {u'status': u'nominal', u'timestamp': 1476111200.082103, u'value': True, u'name': u'agg_m022_mode_not_error', u'received_timestamp': 1476111202.671959}}
    #  GOT: {u'msg_pattern': u'namespace_714a6f67-c170-4742-815a-00a7f5dcf8cd:*', u'msg_channel': u'namespace_714a6f67-c170-4742-815a-00a7f5dcf8cd:agg_m033_mode_not_error', u'msg_data': {u'status': u'nominal', u'timestamp': 1476111198.122401, u'value': True, u'name': u'agg_m033_mode_not_error', u'received_timestamp': 1476111202.673499}}
    #  GOT: {u'msg_pattern': u'namespace_714a6f67-c170-4742-815a-00a7f5dcf8cd:*', u'msg_channel': u'namespace_714a6f67-c170-4742-815a-00a7f5dcf8cd:agg_m044_mode_not_error', u'msg_data': {u'status': u'nominal', u'timestamp': 1476111194.420856, u'value': True, u'name': u'agg_m044_mode_not_error', u'received_timestamp': 1476111202.675499}}
    #  GOT: {u'msg_pattern': u'namespace_714a6f67-c170-4742-815a-00a7f5dcf8cd:*', u'msg_channel': u'namespace_714a6f67-c170-4742-815a-00a7f5dcf8cd:agg_m055_mode_not_error', u'msg_data': {u'status': u'nominal', u'timestamp': 1476111193.089784, u'value': True, u'name': u'agg_m055_mode_not_error', u'received_timestamp': 1476111202.677308}}
    #  GOT: {u'msg_pattern': u'namespace_714a6f67-c170-4742-815a-00a7f5dcf8cd:*', u'msg_channel': u'namespace_714a6f67-c170-4742-815a-00a7f5dcf8cd:kataware_alarm_m011_ap_mode_error', u'msg_data': {u'status': u'nominal', u'timestamp': 1475659566.07611, u'value': u"nominal,cleared,m011_ap_mode value = 'stop'. status = nominal.", u'name': u'kataware_alarm_m011_ap_mode_error', u'received_timestamp': 1476111202.720117}}
    #  GOT: {u'msg_pattern': u'namespace_714a6f67-c170-4742-815a-00a7f5dcf8cd:*', u'msg_channel': u'namespace_714a6f67-c170-4742-815a-00a7f5dcf8cd:kataware_alarm_m022_ap_mode_error', u'msg_data': {u'status': u'nominal', u'timestamp': 1475659566.11599, u'value': u"nominal,cleared,m022_ap_mode value = 'stop'. status = nominal.", u'name': u'kataware_alarm_m022_ap_mode_error', u'received_timestamp': 1476111202.721652}}
    #  ...
    #  GOT: {u'msg_pattern': u'namespace_c4a18e9c-1870-410c-aa2a-bdb570dda4f2:*', u'msg_channel': u'namespace_c4a18e9c-1870-410c-aa2a-bdb570dda4f2:sched_observation_schedule', u'msg_data': {u'status': u'nominal', u'timestamp': 1476111699.547617, u'value': u'20161010-0001', u'name': u'sched_observation_schedule', u'received_timestamp': 1476111703.4799}}
    #  GOT: {u'msg_pattern': u'namespace_c4a18e9c-1870-410c-aa2a-bdb570dda4f2:*', u'msg_channel': u'namespace_c4a18e9c-1870-410c-aa2a-bdb570dda4f2:sched_observation_schedule_1', u'msg_data': {u'status': u'nominal', u'timestamp': 1476111699.526987, u'value': u'20161010-0001', u'name': u'sched_observation_schedule_1', u'received_timestamp': 1476111703.481737}}
    #  GOT: {u'msg_pattern': u'namespace_c4a18e9c-1870-410c-aa2a-bdb570dda4f2:*', u'msg_channel': u'namespace_c4a18e9c-1870-410c-aa2a-bdb570dda4f2:sched_observation_schedule_2', u'msg_data': {u'status': u'nominal', u'timestamp': 1476111699.533452, u'value': u'', u'name': u'sched_observation_schedule_2', u'received_timestamp': 1476111703.484387}}
    #  GOT: {u'msg_pattern': u'namespace_c4a18e9c-1870-410c-aa2a-bdb570dda4f2:*', u'msg_channel': u'namespace_c4a18e9c-1870-410c-aa2a-bdb570dda4f2:sched_observation_schedule_3', u'msg_data': {u'status': u'nominal', u'timestamp': 1476111699.540772, u'value': u'', u'name': u'sched_observation_schedule_3', u'received_timestamp': 1476111703.486992}}
    #  GOT: {u'msg_pattern': u'namespace_c4a18e9c-1870-410c-aa2a-bdb570dda4f2:*', u'msg_channel': u'namespace_c4a18e9c-1870-410c-aa2a-bdb570dda4f2:sched_observation_schedule_4', u'msg_data': {u'status': u'nominal', u'timestamp': 1476111699.54758, u'value': u'', u'name': u'sched_observation_schedule_4', u'received_timestamp': 1476111703.489199}}
    #  ...

    # The IOLoop will continue to run until the program is aborted.
    # Push Ctrl+C to stop.


if __name__ == '__main__':
    # Start up the tornado IO loop:
    io_loop = tornado.ioloop.IOLoop.current()
    io_loop.add_callback(main, logger)
    io_loop.start()
