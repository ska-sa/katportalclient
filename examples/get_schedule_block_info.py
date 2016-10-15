#!/usr/bin/env python
###############################################################################
# SKA South Africa (http://ska.ac.za/)                                        #
# Author: cam@ska.ac.za                                                       #
# Copyright @ 2013 SKA SA. All rights reserved.                               #
#                                                                             #
# THIS SOFTWARE MAY NOT BE COPIED OR DISTRIBUTED IN ANY FORM WITHOUT THE      #
# WRITTEN PERMISSION OF SKA SA.                                               #
###############################################################################
"""Simple example demonstrating schedule block information queries.

This example uses HTTP access to katportal, not websocket access.  It uses a
specific subarray when initialising the KATPortalClient, as schedule blocks
are assigned to specific subarrays.
"""
import logging

import tornado.gen

from katportalclient import KATPortalClient


logger = logging.getLogger('katportalclient.example')
logger.setLevel(logging.INFO)


@tornado.gen.coroutine
def main():
    # Change URL to point to a valid portal node.  Subarray can be 1 to 4.
    # Note: if on_update_callback is set to None, then we cannot use the
    #       KATPortalClient.connect() method (i.e. no websocket access).
    subarray_number = 1
    portal_client = KATPortalClient('http://portal.mkat/api/client/{}'.
                                    format(subarray_number),
                                    on_update_callback=None, logger=logger)

    # Get the IDs of schedule blocks assigned to the subarray specified above.
    sb_ids = yield portal_client.schedule_blocks_assigned()
    print "\nSchedule block IDs:", sb_ids
    # Example output:
    #   Schedule block IDs: [u'20161010-0001', u'20161010-0002', u'20161010-0003']

    # Fetch the details for one of the schedule blocks found.
    if len(sb_ids) > 0:
        sb_detail = yield portal_client.schedule_block_detail(sb_ids[0])
        print "\nDetail for SB {}:\n{}\n".format(sb_ids[0], sb_detail)
        # Example output:
        #   Detail for SB 20161010-0001:
        #   {u'id_code': u'20161010-0001', u'owner': u'CAM', u'actual_end_time': None,
        #    u'instruction_set': u'run-obs-script ~/svn/katscripts/cam/basic-session-track.py azel,20,30 -t 10 -n off ',
        #    u'ready': True,
        #    u'resource_spec': {u'antenna_spec': u'available', u'schedule_block_id': 287,
        #                       u'controlled_resources': u'data', u'id': 287},
        #    u'id': 287, u'scheduled_time': u'2016-10-10 12:17:06.000Z',
        #    u'priority': u'LOW', u'state': u'SCHEDULED', u'config_label': u'',
        #    u'type': u'OBSERVATION', u'actual_start_time': None,
        #    u'description': u'a test sb', u'verification_state': u'VERIFIED',
        #    u'sub_nr': 1, u'desired_start_time': None, u'expected_duration_seconds': 89,
        #    u'dry_run_resource_alloc': {u'antennas': u'm011,m022',
        #                                u'schedule_block_id': 287,
        #                                u'controlled_resources': u'data_1', u'id': 304},
        #    u'notes': u'(Cloned from 20160908-0001) None', u'outcome': u'UNKNOWN',
        #    u'resource_alloc': None}


if __name__ == '__main__':
    # Start up the tornado IO loop.
    # Only a single function to run once, so use run_sync() instead of start()
    io_loop = tornado.ioloop.IOLoop.current()
    io_loop.run_sync(main)
