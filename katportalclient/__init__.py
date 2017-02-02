###############################################################################
# SKA South Africa (http://ska.ac.za/)                                        #
# Author: cam@ska.ac.za                                                       #
# Copyright @ 2013 SKA SA. All rights reserved.                               #
#                                                                             #
# THIS SOFTWARE MAY NOT BE COPIED OR DISTRIBUTED IN ANY FORM WITHOUT THE      #
# WRITTEN PERMISSION OF SKA SA.                                               #
###############################################################################
"""Root of katportalclient package."""

from client import (
    KATPortalClient, ScheduleBlockNotFoundError, SensorNotFoundError,
    SensorHistoryRequestError, ScheduleBlockTargetsParsingError,
    ReferenceObserverConfigNotSet)
from request import JSONRPCRequest

# BEGIN VERSION CHECK
# Get package version when locally imported from repo or via -e develop install
try:
    import katversion as _katversion
except ImportError:  # pragma: no cover
    import time as _time
    __version__ = "0.0+unknown.{}".format(_time.strftime('%Y%m%d%H%M'))
else:  # pragma: no cover
    __version__ = _katversion.get_version(__path__[0])
# END VERSION CHECK
