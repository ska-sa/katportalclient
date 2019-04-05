#!/usr/bin/env python
# Copyright 2016 SKA South Africa (http://ska.ac.za/)
# BSD license - see COPYING for details
"""Simple example demonstrating schedule block information queries.

This example uses HTTP access to katportal, not websocket access.  It uses a
specific subarray when initialising the KATPortalClient, as schedule blocks
are assigned to specific subarrays.
"""
from __future__ import print_function

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
    portal_client = KATPortalClient('http://{}/api/client/{}'.
                                    format(args.host, args.sub_nr),
                                    on_update_callback=None, logger=logger)

    # Get the IDs of schedule blocks assigned to the subarray specified above.
    sb_ids = yield portal_client.schedule_blocks_assigned()
    print("\nSchedule block IDs on subarray {}\n{}".format(args.sub_nr, sb_ids))
    # Example output:
    #   Schedule block IDs on subarray 1:
    #   [u'20161010-0001', u'20161010-0002', u'20161010-0003']

    # Fetch the details for one of the schedule blocks found.
    if len(sb_ids) > 0:
        sb_detail = yield portal_client.schedule_block_detail(sb_ids[0])
        print("\nDetail for SB {}:\n{}\n".format(sb_ids[0], sb_detail))
        # Example output:
        # Detail for SB 20161010-0001:
        # {u'antennas_dry_run_alloc': u'm011',
        #  u'id_code': u'20170208-0001',
        #  u'obs_readiness': u'READY_TO_EXECUTE',
        #  u'owner': u'CAM',
        #  u'actual_end_time': None,
        #  u'antennas_alloc': None,
        #  u'instruction_set': u'run-obs-script ~/scripts/cam/basic-script.py '
        #                      u'-t 20 -m 360 --proposal-id=CAM_AQF '
        #                      u'--program-block-id=CAM_basic_script',
        #  u'controlled_resources_alloc': None,
        #  u'targets': u'[{"track_start_offset":73.0233476162,"target":"PKS 0023-26 '
        #              u'| J0025-2602 | OB-238, radec, 0:25:49.16, -26:02:12.6, '
        #              u'(1410.0 8400.0 -1.694 2.107 -0.4043)","track_duration":20.0}]',
        #              u'scheduled_time': u'2017-02-08 11:53:34.000Z',
        #              u'lead_operator_priority': None,
        #              u'id': 156,
        #              u'antenna_spec': u'm011',
        #              u'state': u'SCHEDULED',
        #              u'config_label': u'',
        #              u'pb_id': None,
        #              u'type': u'OBSERVATION',
        #              u'actual_start_time': None,
        #              u'description': u'Track for m011',
        #              u'verification_state': u'VERIFIED',
        #              u'sb_order': None,
        #              u'sub_nr': 1,
        #              u'desired_start_time': None,
        #              u'sb_sequence': None,
        #              u'expected_duration_seconds': 400,
        #              u'action_time': u'2017-02-08 11:53:34.000Z',
        #              u'controlled_resources_spec': u'',
        #              u'controlled_resources_dry_run_alloc': u'',
        #              u'notes': u'(Cloned from 20170123-0017) ',
        #              u'outcome': u'UNKNOWN',
        #              u'data_quality': None}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Download schedule block info for a subarray and print to stdout.")
    parser.add_argument(
        '--host',
        default='127.0.0.1',
        help="hostname or IP of the portal server (default: %(default)s).")
    parser.add_argument(
        '-s', '--sub_nr',
        default='1',
        type=int,
        help="subarray number (1, 2, 3, or 4) to request schedule for "
             "(default: %(default)s).")
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
