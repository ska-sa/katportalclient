#!/usr/bin/env python
###############################################################################
# SKA South Africa (http://ska.ac.za/)                                        #
# Author: cam@ska.ac.za                                                       #
# Copyright @ 2013 SKA SA. All rights reserved.                               #
#                                                                             #
# THIS SOFTWARE MAY NOT BE COPIED OR DISTRIBUTED IN ANY FORM WITHOUT THE      #
# WRITTEN PERMISSION OF SKA SA.                                               #
###############################################################################
"""Simple example demonstrating userlogs queries.

This example gets lists of tags and userlogs in various ways.
It uses HTTP access to katportal.
"""
import time
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
    portal_client = KATPortalClient('http://{}/api/client'.format(args.host),
                                    on_update_callback=None, logger=logger)

    # Login so that we know which user to create userlogs for!
    yield portal_client.login(username="cam@ska.ac.za", password="cam")
    tags = yield portal_client.userlog_tags()
    userlogs = yield portal_client.userlogs()

    print "There are %s userlog tags." % len(tags)
    print "=============================="
    print "Here is a list of userlogs for today:"
    print userlogs

    # To create an userlog use the following code
    # To add tags, make an array of tag id's
    userlog_tags_to_add = [tags[0].get('id'), tags[1].get('id')]
    userlog_content = "This is where you would put the content of the userlog!"
    # Start time and end times needs to be in this format 'YYYY-MM-DD HH:mm:ss'
    start_time = time.strftime('%Y-%m-%d 00:00:00')
    end_time = time.strftime('%Y-%m-%d 23:59:59')

    userlog_created = yield portal_client.create_userlog(
        content=userlog_content,
        tag_ids=userlog_tags_to_add,
        start_time=start_time,
        end_time=end_time)

    print "=============================="
    print "Created a userlog! This is the new userlog: "
    print userlog_created
    print "=============================="

    # To edit an existing userlog, user edit_userlog with the modified userlog
    userlog_to_edit = userlogs[0] if userlogs else None
    if userlog_to_edit:
        userlog_to_edit['content'] = 'This content is edited by katportalclient!'
        userlog_to_edit['end_time'] = userlog_to_edit['start_time']
        result = yield portal_client.modify_userlog(userlog_to_edit)
        print "=============================="
        print "Edited userlog! Result: "
        print result

    # Remember to logout when you are done!
    print "=============================="
    print "Logging out!"
    yield portal_client.logout()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Download userlogs and tags and print to stdout.")
    parser.add_argument(
        '--host',
        default='127.0.0.1',
        help="hostname or IP of the portal server (default: %(default)s).")
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
