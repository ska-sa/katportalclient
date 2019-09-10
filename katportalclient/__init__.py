# Copyright 2015 SKA South Africa (http://ska.ac.za/)
# BSD license - see COPYING for details
"""Root of katportalclient package."""
from __future__ import absolute_import

from .client import (
    KATPortalClient, ScheduleBlockNotFoundError, SensorNotFoundError,
    SensorHistoryRequestError, ScheduleBlockTargetsParsingError,
    SubarrayNumberUnknown, SensorLookupError, InvalidResponseError,
    create_jwt_login_token, SensorSample, SensorSampleValueTime)
from .request import JSONRPCRequest

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
