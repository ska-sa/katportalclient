###############################################################################
# SKA South Africa (http://ska.ac.za/)                                        #
# Author: cam@ska.ac.za                                                       #
# Copyright @ 2013 SKA SA. All rights reserved.                               #
#                                                                             #
# THIS SOFTWARE MAY NOT BE COPIED OR DISTRIBUTED IN ANY FORM WITHOUT THE      #
# WRITTEN PERMISSION OF SKA SA.                                               #
###############################################################################
"""
Websocket client and HTTP module for access to katportal webservers.
"""

import logging

import tornado.gen
import tornado.ioloop
import tornado.httpclient
import omnijson as json
from tornado.websocket import websocket_connect

from request import JSONRPCRequest


module_logger = logging.getLogger('kat.katportalclient')


class KATPortalClient(object):
    """
    Client providing simple access to katportal.

    Wraps functions available on katportal webservers via the Pub/Sub capability,
    and HTTP requests.

    Parameters
    ----------
    url: str
        |  Client sitemap URL: ``http://<portal server>/api/client/<subarray #>``.
        |  E.g. for subarray 2:  ``http://1.2.3.4/api/client/2``
        |  (**Deprecated**:  use a websocket URL, e.g. ``ws://...``)
    on_update_callback: function
        Callback that should be invoked every time a Pub/Sub update message
        is received. Signature has to include a single argument for the
        message, e.g. `def on_update(message)`.
    io_loop: tornado.ioloop.IOLoop
        Optional IOLoop instance (default=None).
    logger: logging.Logger
        Optional logger instance (default=None).
    """

    def __init__(self, url, on_update_callback,
                 io_loop=None, logger=None):
        self._logger = logger or module_logger
        self._url = url
        self._ws = None
        self._io_loop = io_loop or tornado.ioloop.IOLoop.current()
        self._on_update = on_update_callback
        self._pending_requests = {}
        self._http_client = tornado.httpclient.AsyncHTTPClient()
        self._sitemap = None

    def _get_sitemap(self, url):
        """
        Fetches the sitemap from the specified URL.

        See :meth:`.sitemap` for details, including the return value.

        Parameters
        ----------
        url: str
            URL to query for the sitemap, if it is an HTTP(S) address.  Otherwise
            it is assumed to be a websocket URL (this is for backwards
            compatibility).  In the latter case, the other endpoints will not be
            valid in the return value.

        Returns
        -------
        dict:
            Sitemap endpoints - see :meth:`.sitemap`.
        """
        result = {
            'websocket': '',
            'historic_sensor_values': '',
            'schedule_blocks': '',
            'sub_nr': '',
        }
        if (url.lower().startswith('http://')
                or url.lower().startswith('https://')):
            http_client = tornado.httpclient.HTTPClient()
            try:
                try:
                    response = http_client.fetch(url)
                    response = json.loads(response.body)
                    result.update(response['client'])
                except tornado.httpclient.HTTPError:
                    self._logger.exception("Failed to get sitemap!")
                except json.JSONError:
                    self._logger.exception("Failed to parse sitemap!")
                except KeyError:
                    self._logger.exception("Failed to parse sitemap!")
            finally:
                http_client.close()
        else:
            result['websocket'] = url
        return result

    @property
    def sitemap(self):
        """
        Returns the sitemap using the URL specified during instantiation.

        The portal webserver provides a sitemap with a number of URLs.  The
        endpoints could change over time, but the keys to access them will not.
        The websever is only queried once, the first time the property is
        accessed.  Typically users will not need to access the sitemap
        directly - the class's methods make use of it.

        Returns
        -------
        dict:
            Sitemap endpoints, will include at least the following::

                { 'websocket': str,
                  'historic_sensor_values': str,
                  'schedule_blocks': str,
                  'sub_nr': str,
                  ... }

                websocket: str
                    Websocket URL for Pub/Sub access.
                historic_sensor_values: str
                    URL for requesting sensor value history.
                schedule_blocks: str
                    URL for requesting observation schedule block information.
                sub_nr: str
                    Subarray number to access (e.g. '1', '2', '3', or '4').

        """
        if not self._sitemap:
            self._sitemap = self._get_sitemap(self._url)
            self._logger.debug("Sitemap: %s.", self._sitemap)
        return self._sitemap

    @property
    def is_connected(self):
        """Return True if websocket is connected."""
        return self._ws is not None

    @tornado.gen.coroutine
    def connect(self):
        """Connect to the websocket server specified during instantiation."""
        if not self.is_connected:
            # TODO(TA): check the connect_timeout option
            self._logger.debug("Connecting to websocket %s", self.sitemap['websocket'])
            self._ws = yield websocket_connect(
                self.sitemap['websocket'], io_loop=self._io_loop)
            if self.is_connected:
                self._io_loop.add_callback(self._run)
            else:
                self._logger.error("Failed to connect!")

    def disconnect(self):
        """Disconnect from the connected websocket server."""
        if self.is_connected:
            self._ws.close()
            self._ws = None
            self._logger.debug("Disconnected client websocket.")

    @tornado.gen.coroutine
    def _run(self):
        """
        Start the main message loop.

        This loop listens for all messages received from the websocket
        server and handles them appropriately.
        """
        # TODO(TA):
        # - Add timeouts
        self._logger.info("Connected! Start listening for messages "
                          "received from websocket server.")
        while self.is_connected:
            msg = yield self._ws.read_message()
            if msg is None:
                self._logger.info("Websocket server disconnected!")
                break
            try:
                msg = json.loads(msg)
                self._logger.debug("Message received: %s", msg)
                msg_id = str(msg['id'])
                if msg_id.startswith('redis-pubsub'):
                    self._io_loop.add_callback(self._on_update, msg['result'])
                else:
                    future = self._pending_requests.get(msg_id, None)
                    if future:
                        error = msg.get('error', None)
                        result = msg.get('result', None)
                        if error:
                            future.set_result(error)
                        else:
                            future.set_result(result)
                    else:
                        self._logger.error(
                            "Message received without a matching pending "
                            "request! '{}'".format(msg))
            except:
                self._logger.warn(
                    "Message received that is not JSON formatted! {}"
                    .format(msg))
                self._io_loop.add_callback(self._on_update, msg)
        self._logger.info("Disconnected! Stop listening for messages "
                          "received from websocket server.")

    def _send(self, req):
        future = tornado.gen.Future()
        if self.is_connected:
            req_id = str(req.id)
            self._pending_requests[req_id] = future
            self._ws.write_message(req())
            return future
        else:
            err_msg = "Failed to send request! Not connected."
            self._logger.error(err_msg)
            future.set_exception(Exception(err_msg))
            return future

    @tornado.gen.coroutine
    def add(self, x, y):
        """Simple method useful for testing."""
        req = JSONRPCRequest('add', [x, y])
        result = yield self._send(req)
        raise tornado.gen.Return(result)

    @tornado.gen.coroutine
    def subscribe(self, namespace, sub_strings=None):
        r"""Subscribe to the specified string identifiers in a namespace.

        A namespace provides grouping and consist of channels that can be
        subscribed to, e.g.

            namespace_1
                channel_A
                channel_B
            namespace_2
                channel_A
                channel_Z

        Messages are then published to namespace channels and delivered to all
        subscribers.

        This method supports both exact string identifiers and redis glob-style
        pattern string identifiers. Example of glob-style redis patterns:

        - h?llo subscribes to hello, hallo and hxllo
        - h*llo subscribes to hllo and heeeello
        - h[ae]llo subscribes to hello and hallo, but not hillo

        Use \ to escape special characters if you want to match them verbatim.

        Examples of subscriptions:
        --------------------------
            - Subscribe to 'data_1' channel in the 'alarms' namespace

                subscribe('alarms', 'data_1')

            - Subscribe to all channels in the 'alarms' namespace

                subscribe('alarms')

            - Subscribe to all 'componentA' channels in namespace 'elementX'

                subscribe('elementX', 'componentA*')

            - Subscribe to a list of subscription identifiers with mixed
              patterns

                subscribe('my_namespace', ['data_5', 'data_[abc]', 'data_1*'])


        Examples of KATCP sensor subscription strings:
        ----------------------------------------------
            Here the channels are the normalised KATCP sensor names
            (i.e. underscores python identifiers).

            - Single sensor in the general namespace

                subscribe('', 'm063_ap_mode')

            - List of specific sensors in the 'antennas' namespace

                subscribe('antennas',
                          ['m063_ap_mode',
                           'm062_ap_mode',
                           'mon:m063_inhibited'])

            - List of sensor pattern strings in the 'antennas' namespace

                subscribe('antennas',
                          ['m063_ap_mode',
                           'm062_ap_actual*',
                           'm063_rsc_rx[lsxu]*'])

        Parameters
        ----------
        namespace: str
            Namespace to subscribe to. If an empty string '', the general
            namespace will be used automatically.
        sub_strings: str or list of str
            The exact and pattern string identifiers to subscribe to.
            Format = [namespace:]channel. Optional (default='*')

        Returns
        -------
        int
            Number of strings identifiers subscribed to.
        """
        req = JSONRPCRequest('subscribe', [namespace, sub_strings])
        result = yield self._send(req)
        raise tornado.gen.Return(result)

    @tornado.gen.coroutine
    def unsubscribe(self, namespace, unsub_strings=None):
        """Unsubscribe from the specified string identifiers in a namespace.

        Method supports both exact string identifiers and redis glob-style
        pattern string identifiers. For more information refer to the docstring
        of the `subscribe` method.

        .. note::

            Redis requires that the unsubscribe names and patterns must match
            the original subscribed names and patterns (including any
            namespaces).

        Parameters
        ----------
        namespace: str
            Namespace to unsubscribe. If an empty string '', the general
            namespace will be used automatically.
        unsub_strings: str or list of str
            The exact and pattern string identifiers to unsubscribe from.
            Optional (default='*').

        Returns
        -------
        int
            Number of strings identifiers unsubscribed from.
        """
        req = JSONRPCRequest('unsubscribe', [namespace, unsub_strings])
        result = yield self._send(req)
        raise tornado.gen.Return(result)

    @tornado.gen.coroutine
    def set_sampling_strategy(self, namespace, sensor_name,
                              strategy_and_params, persist_to_redis=False):
        """Set up a specified sensor strategy for a specific single sensor.

        Parameters
        ----------
        namespace: str
            Namespace with the relevant sensor subscriptions. If empty string
            '', the general namespace will be used.
        sensor_name: str
            The exact sensor name for which the sensor strategy should be set.
            Sensor name has to be the fully normalised sensor name (i.e. python
            identifier of sensor with all underscores) including the resource
            the sensor belongs to e.g. 'm063_ap_connected'
        strategy_and_params: str
            A string with the strategy and its optional parameters specified in
            space-separated form according the KATCP specification e.g.
            '<strat_name> <strat_parm1> <strat_parm2>'
            Examples:
                'event'
                'period 0.5'
                'event-rate 1.0 5.0'
        persist_to_redis: bool
            Whether to persist the sensor updates to redis or not, if persisted
            to redis, the last updated values can be  retrieved from redis
            without having to wait for the next KATCP sensor update.
            (default=False)

        Returns
        -------
        dict
            Dictionary with sensor name as key and result as value
        """
        req = JSONRPCRequest(
            'set_sampling_strategy',
            [namespace, sensor_name, strategy_and_params, persist_to_redis]
        )
        result = yield self._send(req)
        raise tornado.gen.Return(result)

    @tornado.gen.coroutine
    def set_sampling_strategies(self, namespace, filters,
                                strategy_and_params, persist_to_redis=False):
        """
        Set up a specified sensor strategy for a filtered list of sensors.

        Parameters
        ----------
        namespace: str
            Namespace with the relevant sensor subscriptions. If empty string
            '', the general namespace will be used.
        filters: str or list of str
            The regular expression filters to use to select the sensors to
            which to apply the specified strategy. Use "" to match all
            sensors. Is matched using KATCP method `list_sensors`.  Can be a
            single string or a list of strings.
            For example:
                1 filter  = 'm063_rsc_rxl'
                3 filters = ['m063_sensors_ok', 'ap_connected', 'sensors_ok']
        strategy_and_params : str
            A string with the strategy and its optional parameters specified in
            space-separated form according the KATCP specification e.g.
            '<strat_name> <strat_parm1> <strat_parm2>'
            Examples:
                'event'
                'period 0.5'
                'event-rate 1.0 5.0'
        persist_to_redis: bool
            Whether to persist the sensor updates to redis or not, if persisted
            to redis, the last updated values can be  retrieved from redis
            without having to wait for the next KATCP sensor update.
            (default=False)

        Returns
        -------
        dict
            Dictionary with matching sensor names as keys and the
            :meth:`.set_sampling_strategy` result as value::

                { <matching_sensor1_name>:
                    { success: bool,
                    info: string },
                ...
                <matching_sensorN_name>:
                    { success: bool,
                    info: string },
                }

                success: bool
                    True if setting succeeded for this sensor, else False.
                info: string
                    Normalised sensor strategy and parameters as string if
                    success == True else, string with the error that occured.
        """
        req = JSONRPCRequest(
            'set_sampling_strategies',
            [namespace, filters, strategy_and_params, persist_to_redis]
        )
        result = yield self._send(req)
        raise tornado.gen.Return(result)

    def _extract_schedule_blocks(self, json_text, subarray_number):
        """Extract and return list of schedule block IDs from a JSON response."""
        data = json.loads(json_text)
        results = []
        if data['result']:
            schedule_blocks = json.loads(data['result'])
            for schedule_block in schedule_blocks:
                if (schedule_block['sub_nr'] == subarray_number
                        and schedule_block['type'] == 'OBSERVATION'):
                    results.append(schedule_block['id_code'])
        return results

    @tornado.gen.coroutine
    def schedule_blocks_assigned(self):
        """Return list of assigned observation schedule blocks.

        The schedule blocks have already been verified and assigned to
        a single subarray.  The subarray queried is determined by
        the URL used during instantiation.  For detail about
        a schedule block, use :meth:`.schedule_block_detail`.

        Alternatively, subscribe to a sensor like ``sched_observation_schedule_3``
        for updates on the list assigned to subarray number 3 - see :meth:`.subscribe`.

        .. note::

            The websocket is not used for this request - it does not need
            to be connected.

        Returns
        -------
        list:
            List of scheduled block ID strings.  Ordered according to
            priority of the schedule blocks (first has hightest priority).

        """
        url = self.sitemap['schedule_blocks'] + '/scheduled'
        response = yield self._http_client.fetch(url)
        results = self._extract_schedule_blocks(response.body,
                                                int(self.sitemap['sub_nr']))
        raise tornado.gen.Return(results)

    @tornado.gen.coroutine
    def schedule_block_detail(self, id_code):
        """Return detailed information about an observation schedule block.

        For a list of schedule block IDs, see :meth:`.schedule_blocks_assigned`.

        .. note::

            The websocket is not used for this request - it does not need
            to be connected.

        Parameters
        ----------
        id_code: str
            Schedule block identifier.  For example: ``20160908-0010``.

        Returns
        -------
        dict:
            Detailed information about the schedule block.  Some of the
            more useful fields are indicated::

                { 'description': str,
                  'scheduled_time': str,
                  'desired_start_time': str,
                  'actual_start_time': str,
                  'actual_end_time': str,
                  'expected_duration_seconds': int,
                  'state': str,
                  'sub_nr': int,
                  ... }

                description: str
                    Free text description of the observation.
                scheduled_time: str
                     Time (UTC) at which the Schedule Block went SCHEDULED.
                desired_start_time: str
                     Time (UTC) at which user would like the Schedule Block to start.
                actual_start_time: str
                     Time (UTC) at which the Schedule Block went ACTIVE.
                actual_end_time: str
                     Time (UTC) at which the Schedule Block went to COMPLETED
                     or INTERRUPTED.
                expected_duration_seconds: int
                     Length of time (seconds) the observation is expected to take
                     in total.
                state: str
                    'DRAFT': created, in process of being defined, but not yet
                             ready for scheduling.
                    'SCHEDULED': observation is scheduled for later execution, once
                                 resources (receptors, correlator, etc.) become available.
                    'ACTIVE':  observation is currently being executed.
                    'COMPLETED': observation completed naturally (may have been
                                 successful, or failed).
                    'INTERRUPTED': observation was stopped or cancelled by a user or
                                   the system.
                sub_nr: int
                    The number of the subarray the observation is scheduled on.

        Raises
        -------
        ScheduleBlockNotFoundError:
            If no information was available for the requested schedule block.
        """
        url = self.sitemap['schedule_blocks'] + '/' + id_code
        response = yield self._http_client.fetch(url)
        response = json.loads(response.body)
        schedule_block = response['result']
        if not schedule_block:
            raise ScheduleBlockNotFoundError("Invalid schedule block ID: " + id_code)
        raise tornado.gen.Return(schedule_block)


class ScheduleBlockNotFoundError(Exception):
    """Raise if requested schedule block is not found."""
