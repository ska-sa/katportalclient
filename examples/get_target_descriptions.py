#!/usr/bin/env python
###############################################################################
# SKA South Africa (http://ska.ac.za/)                                        #
# Author: cam@ska.ac.za                                                       #
# Copyright @ 2013 SKA SA. All rights reserved.                               #
#                                                                             #
# THIS SOFTWARE MAY NOT BE COPIED OR DISTRIBUTED IN ANY FORM WITHOUT THE      #
# WRITTEN PERMISSION OF SKA SA.                                               #
###############################################################################
"""Simple example demonstrating getting future pointing information by supplying
a schedule block id code.

This example uses HTTP access to katportal, not websocket access.
"""
import logging
import argparse
import time
import katpoint

import tornado.gen

from katportalclient import KATPortalClient


logger = logging.getLogger('katportalclient.example')
logger.setLevel(logging.INFO)


@tornado.gen.coroutine
def main():
    # Change URL to point to a valid portal node.  Subarray can be 1 to 4.
    # Note: if on_update_callback is set to None, then we cannot use the
    #       KATPortalClient.connect() method (i.e. no websocket access).
    portal_client = KATPortalClient('http://{host}/api/client/1'.format(**vars(args)),
                                    on_update_callback=None, logger=logger)

    results = yield portal_client.future_targets(
        '{sb_id_code}'.format(**vars(args)))
    print results

    # Example output:
    # [
    #     {
    #         "track_start_offset":39.8941187859,
    #         "target":"PKS 0023-26 | J0025-2602 | OB-238, radec, 0:25:49.16, -26:02:12.6, (1410.0 8400.0 -1.694 2.107 -0.4043)",
    #         "track_duration":20.0
    #     },
    #     {
    # input type:
    #         "track_start_offset":72.5947952271,
    #         "target":"PKS 0043-42 | J0046-4207, radec, 0:46:17.75, -42:07:51.5, (400.0 2000.0 3.12 -0.7)",
    #         "track_duration":20.0
    #     },
    #     {
    #         "track_start_offset":114.597304821,
    #         "target":"PKS 0408-65 | J0408-6545, radec, 4:08:20.38, -65:45:09.1, (1410.0 8400.0 -3.708 3.807 -0.7202)",
    #         "track_duration":20.0
    #     }
    # ]

    # Create the antenna object that is used as the reference observer for
    # the coordinate calculations.
    # The parameters for the antenna object is as follows:
    #     name : string or :class:`Antenna` object
    #         Name of antenna, or full description string or existing antenna object
    #     latitude : string or float, optional
    #         Geodetic latitude, either in 'D:M:S' string format or float in radians
    #     longitude : string or float, optional
    #         Longitude, either in 'D:M:S' string format or a float in radians
    #     altitude : string or float, optional
    #         Altitude above WGS84 geoid, in metres
    #     diameter : string or float, optional
    #         Dish diameter, in metres
    #     delay_model : :class:`DelayModel` object or equivalent, optional
    #         Delay model for antenna, either as a direct object, a file-like object
    #         representing a parameter file, or a string or sequence of float params.
    #         The first three parameters form an East-North-Up offset from WGS84
    #         reference position, in metres.
    #     pointing_model : :class:`PointingModel` object or equivalent, optional
    #         Pointing model for antenna, either as a direct object, a file-like
    #         object representing a parameter file, or a string or sequence of
    #         float parameters from which the :class:`PointingModel` object can
    #         be instantiated
    #     beamwidth : string or float, optional
    #         Full width at half maximum (FWHM) average beamwidth, as a multiple of
    #         lambda / D (wavelength / dish diameter). This depends on the dish
    #         illumination pattern, and ranges from 1.03 for a uniformly illuminated
    #         circular dish to 1.22 for a Gaussian-tapered circular dish (the
    #         default).
    antenna = katpoint.Antenna(name='Custom Reference Observer Antenna Name',
                               latitude=20.0,
                               longitude=20.0,
                               altitude=10.0)
    # The timestamp_for_calcs is used to calculate the coordinates for targets
    # at a certain time of day. This can be any date and time, meaning that
    # you can calculate future and past target coordinates
    # input type: float, string, :class:`ephem.Date` object or None
    #          Timestamp, in various formats (if None, defaults to now)
    timestamp_for_calcs = katpoint.Timestamp(timestamp=time.time())

    for future_target in results:
        # Create the katpoint.Target object
        # The body argument is the full description string as specified in the
        # "target" attribute of the future_targets results.
        # The antenna parameter is a katpoint.Antenna object that defines
        # the reference observer for the coordinates calculation.
        # An alternative to specifying the antenna in the target object
        # would be to pass the antenna object as a parameter to any of
        # the calculation methods.

        # Please see the katpoint.Target class docstring for a detailed
        # explanation of the usage and input parameters.
        target = katpoint.Target(body=future_target['target'],
                                 antenna=antenna)
        print "-" * 80
        # Short human-friendly string representation of target object.
        print "Target: {}".format(target)
        # Complete string representation of target object, sufficient to
        # reconstruct it.
        print "\tdescription: {}".format(target.description)
        # Type of target body, as a string tag.
        print "\tbody_type: {}".format(target.body_type)
        # Calculate target (az, el) coordinates as seen from antenna at
        # time(s).
        print "\tazel: {}".format(target.azel(timestamp=timestamp_for_calcs))
        # Calculate target's apparent (ra, dec) coordinates as seen from antenna at time(s).
        # This calculates the *apparent topocentric position* of the target for
        # the epoch-of-date in equatorial coordinates. Take note that this is
        # *not* the "star-atlas" position of the target, but the position as is
        # actually seen from the antenna at the given times. The difference is on
        # the order of a few arcminutes. These are the coordinates that a telescope
        # with an equatorial mount would use to track the target. Some targets are
        # unable to provide this (due to a limitation of pyephem), notably
        # stationary (*azel*) targets, and provide the *astrometric geocentric
        # position* instead.
        print "\tapparent_radec: {}".format(
            target.apparent_radec(timestamp=timestamp_for_calcs))
        # Calculate target's astrometric (ra, dec) coordinates as seen from antenna at time(s).
        # This calculates the J2000 *astrometric geocentric position* of the
        # target, in equatorial coordinates. This is its star atlas position for
        # the epoch of J2000.
        print "\tastrometric_radec: {}".format(
            target.astrometric_radec(timestamp=timestamp_for_calcs))
        # Calculate target's galactic (l, b) coordinates as seen from antenna at time(s).
        # This calculates the galactic coordinates of the target, based on the
        # J2000 *astrometric* equatorial coordinates. This is its position relative
        # to the Galactic reference frame for the epoch of J2000.
        print "\tgalactic: {}".format(target.galactic(timestamp=timestamp_for_calcs))
        # Calculate parallactic angle on target as seen from antenna at time(s).
        # This calculates the *parallactic angle*, which is the position angle of
        # the observer's vertical on the sky, measured from north toward east.
        # This is the angle between the great-circle arc connecting the celestial
        # North pole to the target position, and the great-circle arc connecting
        # the zenith above the antenna to the target, or the angle between the
        # *hour circle* and *vertical circle* through the target, at the given
        # timestamp(s).
        print "\tparallactic_angle: {}".format(
            target.parallactic_angle(timestamp=timestamp_for_calcs))

    # Example output:
    # --------------------------------------------------------------------------------
    # Target: PKS 0023-26 (J0025-2602, OB-238), tags=radec, 0:25:49.16 -26:02:12.6, flux defined for 1410 - 8400 MHz
    #     description: PKS 0023-26 | J0025-2602 | OB-238, radec, 0:25:49.16, -26:02:12.6, (1410.0 8400.0 -1.694 2.107 -0.4043)
    #     body_type: radec
    #     azel: (2.6852309703826904, -0.07934337109327316)
    #     apparent_radec: (0.11626834312746936, -0.4528470669175264)
    #     astrometric_radec: (0.11265809433414732, -0.45442846845967694)
    #     galactic: (0.737839670058081, -1.4690447007394833)
    #     parallactic_angle: -0.201351834408
    # --------------------------------------------------------------------------------
    # Target: PKS 0043-42 (J0046-4207), tags=radec, 0:46:17.75 -42:07:51.5, flux defined for 400 - 2000 MHz
    #     description: PKS 0043-42 | J0046-4207, radec, 0:46:17.75, -42:07:51.5, (400.0 2000.0 3.12 -0.7)
    #     body_type: radec
    #     azel: (2.6755282878875732, -0.3695283532142639)
    #     apparent_radec: (0.20537825871631094, -0.7337815110666293)
    #     astrometric_radec: (0.20200368040530206, -0.7353241823440498)
    #     galactic: (5.351322507432435, -1.3083084615323348)
    #     parallactic_angle: -0.249510196222
    # --------------------------------------------------------------------------------
    # Target: 3C 48 (J0137+3309), tags=radec, 1:37:41.30 33:09:35.1, flux defined for 1408 - 23780 MHz
    #     description: 3C 48 | J0137+3309, radec, 1:37:41.30, 33:09:35.1, (1408.0 23780.0 2.465 -0.004 -0.1251)
    #     body_type: radec
    #     azel: (2.0180811882019043, 0.821528434753418)
    #     apparent_radec: (0.43045833891817115, 0.5802468926346598)
    #     astrometric_radec: (0.4262457643630985, 0.5787468166381896)
    #     galactic: (2.338087971687879, -0.5012483563409715)
    #     parallactic_angle: -0.455535950384
    # --------------------------------------------------------------------------------
    # Target: PKS 0316+16 (J0318+1628, CTA 21), tags=radec, 3:18:57.80 16:28:32.7, flux defined for 1410 - 8400 MHz
    #     description: PKS 0316+16 | J0318+1628 | CTA 21, radec, 3:18:57.80, 16:28:32.7, (1410.0 8400.0 1.717 0.2478 -0.1594)
    #     body_type: radec
    #     azel: (1.7292250394821167, 0.38660863041877747)
    #     apparent_radec: (0.8723107486945224, 0.28858452929189576)
    #     astrometric_radec: (0.8681413143524127, 0.2875560842354557)
    #     galactic: (2.9083411725795085, -0.5863595073035497)
    #     parallactic_angle: -0.433835448811
    # --------------------------------------------------------------------------------
    # Target: For A (J0322-3712, Fornax A, NGC 1316, PKS 0320-37), tags=radec, 3:22:41.51 -37:12:33.4, flux defined for 1200 - 2000 MHz
    #     description: For A | J0322-3712 | Fornax A | NGC 1316 | PKS 0320-37, radec, 3:22:41.51, -37:12:33.4, (1200.0 2000.0 2.097)
    #     body_type: radec
    #     azel: (2.1072041988372803, -0.4763931930065155)
    #     apparent_radec: (0.8872067982786673, -0.6484923060219283)
    #     astrometric_radec: (0.8844099646425649, -0.6494244095113811)
    #     galactic: (4.191667715692746, -0.9894384083155107)
    #     parallactic_angle: -0.455723041705
    # --------------------------------------------------------------------------------
    # Target: PKS 0408-65 (J0408-6545), tags=radec, 4:08:20.38 -65:45:09.1, flux defined for 1410 - 8400 MHz
    #     description: PKS 0408-65 | J0408-6545, radec, 4:08:20.38, -65:45:09.1, (1410.0 8400.0 -3.708 3.807 -0.7202)
    #     body_type: radec
    #     azel: (2.3527166843414307, -0.9555976390838623)
    #     apparent_radec: (1.0841209870004445, -1.14695824889687)
    #     astrometric_radec: (1.0835862116596364, -1.1475981012312526)
    #     galactic: (4.8632537597104, -0.7134665360827386)
    #     parallactic_angle: -0.78112011371
    # --------------------------------------------------------------------------------
    # Target: PKS 0410-75 (J0408-7507), tags=radec, 4:08:49.07 -75:07:13.7, flux defined for 200 - 12000 MHz
    #     description: PKS 0410-75 | J0408-7507, radec, 4:08:49.07, -75:07:13.7, (200.0 12000.0 1.362 0.7345 -0.254)
    #     body_type: radec
    #     azel: (2.589509963989258, -1.0602085590362549)
    #     apparent_radec: (1.083933909716081, -1.3104608809263385)
    #     astrometric_radec: (1.0856726073362912, -1.3110995759307191)
    #     galactic: (5.043567016155924, -0.6305471158619853)
    #     parallactic_angle: -0.981741957496


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Gets the target list and target pointing descriptions "
                    "from katportal catalogues.")
    parser.add_argument(
        '--host',
        default='127.0.0.1',
        help="hostname or IP of the portal server (default: %(default)s).")
    parser.add_argument(
        '-s', '--sb-id-code',
        default=None,
        dest='sb_id_code',
        help="The schedule block id code to load the future targets list from")
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
