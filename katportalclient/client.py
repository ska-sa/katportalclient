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
import uuid
import time
from urllib import urlencode
from datetime import timedelta
from collections import namedtuple

import tornado.gen
import tornado.ioloop
import tornado.httpclient
import tornado.locks
import omnijson as json
from tornado.websocket import websocket_connect
from tornado.httputil import url_concat

from request import JSONRPCRequest


# Limit for sensor history queries, in order to preserve memory on katportal.
MAX_SAMPLES_PER_HISTORY_QUERY = 1000000
# Pick a reasonable chunk size for sample downloads.  The samples are
# published in blocks, so many at a time.
# 43200 = 12 hour chunks if 1 sample every second
SAMPLE_HISTORY_CHUNK_SIZE = 43200
# Request sample times  in milliseconds for better precision
SAMPLE_HISTORY_REQUEST_TIME_TYPE = 'ms'
SAMPLE_HISTORY_REQUEST_MULTIPLIER_TO_SEC = 1000.0

# Websocket connect and reconnect timeouts
WS_CONNECT_TIMEOUT = 10
WS_RECONNECT_INTERVAL = 15

module_logger = logging.getLogger('kat.katportalclient')


class SensorSample(namedtuple('SensorSample', 'timestamp, value, status')):
    """Class to represent all sensor samples.

    Fields:
        - timestamp:  float
            The timestamp (UNIX epoch) the sample was received by CAM.
            timestamp value is reported with millisecond precision.
        - value:  str
            The value of the sensor when sampled.  The units depend on the
            sensor, see :meth:`.sensor_detail`.
        - status:  str
            The status of the sensor when the sample was taken. As defined
            by the KATCP protocol. Examples: 'nominal', 'warn', 'failure', 'error',
            'critical', 'unreachable', 'unknown', etc.
    """
    def csv(self):
        """Returns sample in comma separated values format."""
        return '{},{},{}'.format(self.timestamp, self.value, self.status)


class SensorSampleValueTs(namedtuple(
        'SensorSampleValueTs', 'timestamp, value_timestamp, value, status')):
    """Class to represent sensor samples, including the value_timestamp.

    Fields:
        - timestamp:  float
            The timestamp (UNIX epoch) the sample was received by CAM.
            Timestamp value is reported with millisecond precision.
        - value_timestamp:  float
            The timestamp (UNIX epoch) the sample was read at the lowest level sensor.
            value_timestamp value is reported with millisecond precision.
        - value:  str
            The value of the sensor when sampled.  The units depend on the
            sensor, see :meth:`.sensor_detail`.
        - status:  str
            The status of the sensor when the sample was taken. As defined
            by the KATCP protocol. Examples: 'nominal', 'warn', 'failure', 'error',
            'critical', 'unreachable', 'unknown', etc.
    """
    def csv(self):
        """Returns sample in comma separated values format."""
        return '{},{},{},{}'.format(
            self.timestamp, self.value_timestamp, self.value, self.status)


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

    def __init__(self, url, on_update_callback, io_loop=None, logger=None):
        self._logger = logger or module_logger
        self._url = url
        self._ws = None
        self._ws_connecting_lock = tornado.locks.Lock()
        self._io_loop = io_loop or tornado.ioloop.IOLoop.current()
        self._on_update = on_update_callback
        self._pending_requests = {}
        self._http_client = tornado.httpclient.AsyncHTTPClient()
        self._sitemap = None
        self._sensor_history_states = {}
        self._reference_observer_config = None
        self._disconnect_issued = False
        self._ws_jsonrpc_cache = []

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
            'subarray_sensor_values': '',
            'target_descriptions': ''
        }
        if (url.lower().startswith('http://') or
                url.lower().startswith('https://')):
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
                subarray_sensor_values: str
                    URL for requesting once off current sensor values.
                target_descriptions: str
                    URL for requesting target pointing descriptions for a
                    specified schedule block

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
        # The lock is used to ensure only a single connection can be made
        with (yield self._ws_connecting_lock.acquire()):
            self._disconnect_issued = False
            if not self.is_connected:
                self._logger.debug(
                    "Connecting to websocket %s", self.sitemap['websocket'])
                try:
                    self._ws = yield websocket_connect(
                        self.sitemap['websocket'],
                        on_message_callback=self._websocket_message,
                        connect_timeout=WS_CONNECT_TIMEOUT)
                except:
                    self._logger.exception(
                        'Could not connect websocket to %s',
                        self.sitemap['websocket'])
                if not self.is_connected:
                    self._logger.error("Failed to connect!")

    def disconnect(self):
        """Disconnect from the connected websocket server."""
        if self.is_connected:
            self._disconnect_issued = True
            self._ws_jsonrpc_cache = []
            self._ws.close()
            self._ws = None
            self._logger.debug("Disconnected client websocket.")

    def _reconnect_ws(self):
        """
        Immediately try to reconnect the websocket. If that failed, retry
        the connect every 15 seconds or until the client issues a
        disconnect."""
        if not self._disconnect_issued:
            self._logger.info("Reconnecting the websocket...")
            self.connect()
            if self.is_connected:
                self._resend_subscriptions_and_strategies()
                self._logger.info("Reconnected :)")
            else:
                # Retry the connect in WS_RECONNECT_INTERVAL seconds
                self._io_loop.call_later(
                    WS_RECONNECT_INTERVAL, self._reconnect_ws)

    def _cache_jsonrpc_request(self, jsonrpc_request):
        """
        If the websocket is connected, cache all the the jsonrpc requests.
        When the websocket connection closes unexpectedly, we will attempt
        to reconnect. When the reconnection was successful, we will resend
        all of the jsonrpc applicable requests to ensure that we set the same
        subscriptions and sampling strategies that was set while the
        websocket was connected.

        .. note::

        When an unsubscribe or set_sampling_strategy and set_sampling_strategies
        with a none value is cached, we remove the matching converse call for
        that pattern. For example, if we cache a subscribe message for a
        namespace, then later cache an unsubscribe message for that same
        namespace, we will remove the subscribe message from the cache and not
        add the unsubscribe message to the cache. If we cache a
        set_sampling_strategy for a sensor, then later cache a call to
        set_sampling_strategy for the same sensor with none (clearing the
        strategy on the sensor), we remove the set_sampling_strategy from the
        cache and do not add the set_sampling_strategy to the cache that had
        a strategy of none. The same counts for set_sampling_strategies,
        except that we match on the sensor name pattern.
        We do not cache unsubscribe because creating a new websocket
        connection has no subscriptions on katportal. Also when we receive a
        'redis-reconnect' message, we do not have any subscriptions on
        katportal.
        """
        requests_to_remove = []
        if jsonrpc_request.method == 'unsubscribe':
            for req in self._ws_jsonrpc_cache:
                # match namespace and subscription string for subscribes
                if (req.method == 'subscribe' and
                        req.params == jsonrpc_request.params):
                    requests_to_remove.append(req)
        elif (jsonrpc_request.method.startswith('set_sampling_strat') and
              jsonrpc_request.params[2] == 'none'):
            # index 2 of params is always the sampling strategy
            for req in self._ws_jsonrpc_cache:
                # match the namespace and sensor/filter combination
                # namespace is always at index 0 of params and sensor/filter
                # is always at index 1
                if (req.method == jsonrpc_request.method and
                        req.params[0] == jsonrpc_request.params[0] and
                        req.params[1] == jsonrpc_request.params[1]):
                    requests_to_remove.append(req)
        else:
            self._ws_jsonrpc_cache.append(jsonrpc_request)

        for req in requests_to_remove:
            self._ws_jsonrpc_cache.remove(req)

    def _resend_subscriptions_and_strategies(self):
        """
        Resend the cached subscriptions and strategies that has been set while
        the websocket connection was connected. This cache is cleared when a
        disconnect is issued by the client. The cache is a list of
        JSONRPCRequests"""
        for req in self._ws_jsonrpc_cache:
            self._logger.info('Resending JSONRPCRequest %s', req)
            result = yield self._send(req)
            self._logger.info('Resent JSONRPCRequest, with result: %s', result)

    def _resend_subscriptions(self):
        """
        Resend the cached subscriptions only. This is necessary when we receive
        a redis-reconnect server message."""
        for req in self._ws_jsonrpc_cache:
            if req.method == 'subscribe':
                self._logger.info('Resending JSONRPCRequest %s', req)
                result = yield self._send(req)
                self._logger.info('Resent JSONRPCRequest, with result: %s', result)

    def _websocket_message(self, msg):
        """
        All websocket messages calls this method.
        If the message is None, the websocket connection was closed. When
        the websocket is closed by a disconnect that was not issued by the
        client, we need to reconnect, resubscribe and reset sampling
        strategies.

        There are different types of websocket messages that we receive:

            - json RPC message, the result for setting sampling strategies or
              subscribing/unsubscribing to namespaces
            - pub-sub message
            - redis-reconnect - when portal reconnects to redis. When this
              happens we need to resend our subscriptions
        """
        if msg is None:
            self._logger.warn("Websocket server disconnected!")
            if not self._disconnect_issued:
                self._periodic_reconnect_ws()
            return
        try:
            msg = json.loads(msg)
            self._logger.debug("Message received: %s", msg)
            msg_id = str(msg['id'])
            if msg_id.startswith('redis-pubsub'):
                self._process_redis_message(msg, msg_id)
            elif msg_id.startswith('redis-reconnect'):
                # only resubscribe to namespaces, the server will still
                # publish sensor value updates to redis because the client
                # did not disconnect, katportal lost its own connection
                # to redis
                self._resend_subscriptions()
            else:
                self._process_json_rpc_message(msg, msg_id)
        except:
            self._logger.exception(
                "Error processing websocket message! {}".format(msg))
            if self._on_update:
                self._io_loop.add_callback(self._on_update, msg)
            else:
                self._logger.warn('Ignoring message (no on_update_callback): %s',
                                  msg)

    @tornado.gen.coroutine
    def _process_redis_message(self, msg, msg_id):
        """Internal handler for Redis messages."""
        msg_result = msg['result']
        processed = False
        if msg_id == 'redis-pubsub-init':
            processed = True  # Nothing to do really.
        elif 'msg_channel' in msg_result:
            namespace = msg_result['msg_channel'].split(':', 1)[0]
            if namespace in self._sensor_history_states:
                state = self._sensor_history_states[namespace]
                msg_data = msg_result['msg_data']
                if (isinstance(msg_data, dict) and
                        'inform_type' in msg_data and
                        msg_data['inform_type'] == 'sample_history'):
                    # inform message which provides synchronisation information.
                    inform = msg_data['inform_data']
                    num_new_samples = inform['num_samples_to_be_published']
                    state['num_samples_pending'] += num_new_samples
                    if inform['done']:
                        state['done_event'].set()
                elif isinstance(msg_data, list):
                    num_received = 0
                    for sample in msg_data:
                        if len(sample) == 6:
                            # assume sample data message, extract fields of interest
                            # (timestamp returned in milliseconds, so scale to seconds)
                            # example:  [1476164224429L, 1476164223640L,
                            #            1476164224429354L, u'5.07571614843',
                            #            u'anc_mean_wind_speed', u'nominal']
                            if state['include_value_ts']:
                                # Requesting value_timestamp in addition to sample timestamp
                                sensor_sample = SensorSampleValueTs(
                                    timestamp=sample[0]/SAMPLE_HISTORY_REQUEST_MULTIPLIER_TO_SEC,
                                    value_timestamp=sample[1]/SAMPLE_HISTORY_REQUEST_MULTIPLIER_TO_SEC,
                                    value=sample[3],
                                    status=sample[5])
                            else:
                                # Only sample timestamp
                                sensor_sample = SensorSample(
                                    timestamp=sample[0]/SAMPLE_HISTORY_REQUEST_MULTIPLIER_TO_SEC,
                                    value=sample[3],
                                    status=sample[5])
                            state['samples'].append(sensor_sample)
                            num_received += 1
                    state['num_samples_pending'] -= num_received
                else:
                    self._logger.warn('Ignoring unexpected message: %s', msg_result)
                processed = True
        if not processed:
            if self._on_update:
                self._io_loop.add_callback(self._on_update, msg_result)
            else:
                self._logger.warn('Ignoring message (no on_update_callback): %s',
                                  msg_result)

    @tornado.gen.coroutine
    def _process_json_rpc_message(self, msg, msg_id):
        """Internal handler for JSON RPC response messages."""
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
                "Message received without a matching pending request! '{}'".format(msg))

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
        self._cache_jsonrpc_request(req)
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
        self._cache_jsonrpc_request(req)
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
        self._cache_jsonrpc_request(req)
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
        self._cache_jsonrpc_request(req)
        raise tornado.gen.Return(result)

    def _extract_schedule_blocks(self, json_text, subarray_number):
        """Extract and return list of schedule block IDs from a JSON response."""
        data = json.loads(json_text)
        results = []
        if data['result']:
            schedule_blocks = json.loads(data['result'])
            for schedule_block in schedule_blocks:
                if (schedule_block['sub_nr'] == subarray_number and
                        schedule_block['type'] == 'OBSERVATION'):
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
    def future_targets(self, id_code):
        """
        Return a list of future targets as determined by the dry run of the
        schedule block.

        The schedule block will only have future targets (in the targets
        attribute) if the schedule block has been through a dry run and
        has the verification_state of VERIFIED. The future targets are
        only applicable to schedule blocks of the OBSERVATION type.

        Parameters
        ----------
        id_code: str
            Schedule block identifier. For example: ``20160908-0010``.

        Returns
        -------
        list:
            Ordered list of future targets that was determined by the
            verification dry run.
            Example:
            [{
                'name': 'Moon',
                'track_duration': 60.0,
                'slew_time': 53.6153013706
                'start_offset': 0.0,
            },
                'name': 'Sun',
                'track_duration': 60.0,
                'slew_time': 20.9873
                'start_offset': 113.6153013706,
            }, {..}]
        Raises
        ------
        ScheduleBlockTargetsParsingError:
            If there is an error parsing the schedule block's targets string.
        ScheduleBlockNotFoundError:
            If no information was available for the requested schedule block.
        """
        sb = yield self.schedule_block_detail(id_code)
        targets_list = []
        sb_targets = sb.get('targets')
        if sb_targets is not None:
            try:
                targets_list = json.loads(sb_targets)
            except:
                raise ScheduleBlockTargetsParsingError(
                    'There was an error parsing the schedule block (%s) '
                    'targets attribute: %s', id_code, sb_targets)
        raise tornado.gen.Return(targets_list)

    @tornado.gen.coroutine
    def future_targets_detail(self, id_code):
        """
        Return a detailed list of future targets as determined by the dry run
        of the schedule block. This method requires that you have set the
        reference observer before calling it, using the
        set_reference_observer_config method in this class.

        The schedule block will only have future targets (in the targets
        attribute) if the schedule block has been through a dry run and
        has the verification_state of VERIFIED. The future targets are
        only applicable to schedule blocks of the OBSERVATION type.

        Parameters
        ----------
        id_code: str
            Schedule block identifier. For example: ``20160908-0010``.

        Returns
        -------
        list:
            Ordered list of future targets that was determined by the
            verification dry run with pointing details calculated by using
            the reference observer set by set_reference_observer_config
            Example:
            [{
                'name': 'Moon',
                'body_type': 'special',
                'description': 'Moon,special',
                'track_duration': 60.0,
                'slew_time': 53.6153013706
                'start_offset': 0.0,
                'azel': [3.6399178505, 1.3919397593],
                'astrometric_radec': [0.180696943, 0.0180189191],
                'apparent_radec': [0.1830730793, 0.0169845125],
                'tags': ['special'],
                'galactic': [2.0531028499, -1.0774995277],
                'parallactic_angle': 0.49015412010000003,
                'uvw_basis': [[0.996376853, -0.0150540303, 0.0837050956],
                              [..], [..]]
            }, {..}]

            Example for a target that is not found in the catalogue:
            [{..}, {
                'name': 'FAKETARGET',
                'slew_time': 41.6139953136,
                'track_duration': 21.0,
                'error': 'Target not in catalogues!',
                'start_offset': 137.8720090389},
            }, {..}]

        Raises
        ------
        ReferenceObserverConfigNotSet:
            If the reference observer config has not been set before
            calling this method.
        ScheduleBlockTargetsParsingError:
            If there is an error parsing the schedule block's targets string.
        ScheduleBlockNotFoundError:
            If no information was available for the requested schedule block.
        ValueError:
            If the returned target description value is not a list. This
            could happen when there is an exception on katportal loading
            the target details from the catalogues.
        """
        if self._reference_observer_config is None:
            raise ReferenceObserverConfigNotSet(
                'Reference Observer config not set. '
                'Please set the reference observer config using '
                'the set_reference_observer_config method.')
        sb = yield self.schedule_block_detail(id_code)
        targets_list = []
        sb_targets = sb.get('targets')
        if sb_targets is not None:
            try:
                targets_list = json.loads(sb_targets)
            except:
                raise ScheduleBlockTargetsParsingError(
                    'There was an error parsing the schedule block (%s) '
                    'targets attribute: %s', id_code, sb_targets)
            config_label = yield self.config_label_for_subarray(
                int(self.sitemap['sub_nr']))
            target_names = [target.get('name') for target in targets_list]
            targets_csv = ','.join(target_names)
            target_descriptions = yield self._get_target_descriptions(
                targets=targets_csv,
                longitude=self._reference_observer_config['longitude'],
                latitude=self._reference_observer_config['latitude'],
                altitude=self._reference_observer_config['altitude'],
                timestamp=self._reference_observer_config['timestamp'],
                config_label=config_label)
            if isinstance(target_descriptions, list):
                for target_desc in target_descriptions:
                    targets_list_index = targets_list.index(
                        filter(lambda n: n.get('name') == target_desc.get('name'),
                               targets_list)[0])
                    targets_list[targets_list_index].update(target_desc)
            else:
                raise ValueError(
                    'The returned target descriptions is not a list of '
                    'targets, it is instead: %s' % target_descriptions)

        raise tornado.gen.Return(targets_list)

    def set_reference_observer_config(
            self, longitude=None, latitude=None, altitude=None, timestamp=None):
        """
        Set the reference observer config to be used when retrieving
        the future target list from a schedule block.

        .. note::

            If longitude, latitude or altitude is None then katpoint will use
            the array's default reference observer. If timestamp is None,
            katpoint will use the current utc time to calculate the pointing
            details.

        Parameters
        ----------
        longitude: float
            Unit: degrees
            The longitude of the reference observer used in calculating the
            pointing details.
            Default: None, if longitude, latitude or altitude is None then
            katpoint will use the array's
        latitude: float
            Unit: degrees
            The latitude of the reference observer used in calculating the
            pointing details.
            Default: None, if this is None katpoint will use the array's
            default reference observer
        altitude: float
            Unit: meters
            The altitude of the reference observer used in calculating the
            pointing details.
            Default: None, if this is None katpoint will use the array's
            default reference observer
        timestamp: float
            Unit: seconds after the unix epoch
            The unix timestamp (UTC) of the time of the reference observer
            used to calculate the pointing details.
            Default: None, katpoint uses current utc time to calculate
            pointing details.
        """
        if self._reference_observer_config is None:
            self._reference_observer_config = {}
        self._reference_observer_config['longitude'] = longitude
        self._reference_observer_config['latitude'] = latitude
        self._reference_observer_config['altitude'] = altitude
        self._reference_observer_config['timestamp'] = timestamp

    @tornado.gen.coroutine
    def config_label_for_subarray(self, sub_nr):
        """Get the config label for the specified sub_nr. Returns None if
        the subarray has an empty config_label. An active subarray will
        always have a config_label.

        Parameters
        ----------
        sub_nr: int
            The subarray's config label to get, can be 1,2,3,4

        Returns
        -------
        str:
            A csv string that is used as a config_label in the CAM system.
            The config_label is used to select the version of the catalogue
            files when calculating the pointing details.
        """
        url = self.sitemap['subarray_sensor_values'] + '/config_label'
        response = yield self._http_client.fetch(url)
        config_label_sensor_result = json.loads(response.body)[0]
        raise tornado.gen.Return(config_label_sensor_result.get('value'))

    @tornado.gen.coroutine
    def _get_target_descriptions(
            self, targets, longitude, latitude, altitude,
            timestamp, config_label):
        """
        Return a list of targets with their pointing information calculated
        by using the longitude, latitude, altitude as the reference observer
        and timestamp as the time of the reference observer.
        Using the config_label to select a specific version of the catalogues
        files.

        Parameters
        ----------
        targets: str
            A CSV list of target names to retrieve the pointing details.
        longitude: float
            The longitude of the reference observer used in calculating the
            pointing details.
        latitude: float
            The latitude of the reference observer used in calculating the
            pointing details.
        altitude: float
            The altitude of the reference observer used in calculating the
            pointing details.
        timestamp: float
            The unix timestamp (UTC) of the time of the reference observer
            used to calculate the pointing details.
        config_label: str
            The config_label to use to select the version of the catalogue
            files when calculating the pointing details.

        Returns
        -------
        list:
            A list of dictionaries containing pointing information calculated
            taking the reference observer into account.
        """
        url = self.sitemap['target_descriptions']
        request_data = {
            'targets': targets,
            'longitude': longitude,
            'latitude': latitude,
            'altitude': altitude,
            'timestamp': timestamp,
            'config_label': config_label
        }
        request_body = urlencode(request_data)
        response = yield self._http_client.fetch(url, method='POST', body=request_body)
        raise tornado.gen.Return(json.loads(response.body))

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

    def _extract_sensors_details(self, json_text):
        """Extract and return list of sensor names from a JSON response."""
        sensors = json.loads(json_text)
        results = []
        # Errors are returned in dict, while valid data is returned in a list.
        if isinstance(sensors, dict):
            if 'error' in sensors:
                raise SensorNotFoundError("Invalid sensor request: " + sensors['error'])
        else:
            for sensor in sensors:
                sensor_info = {}
                sensor_info['name'] = sensor[0]
                sensor_info['component'] = sensor[1]
                sensor_info.update(sensor[2])
                results.append(sensor_info)
        return results

    @tornado.gen.coroutine
    def sensor_names(self, filters):
        """Return list of matching sensor names.

        Provides the list of available sensors in the system that match the
        specified pattern.  For detail about a sensor's attributes,
        use :meth:`.sensor_detail`.

        .. note::

            The websocket is not used for this request - it does not need
            to be connected.

        Parameters
        ----------
        filters: str or list of str
            List of regular expression patterns to match.
            See :meth:`.set_sampling_strategies` for more detail.

        Returns
        -------
        list:
            List of sensor name strings.

        Raises
        -------
        SensorNotFoundError:
            - If any of the filters were invalid regular expression patterns.
        """
        url = self.sitemap['historic_sensor_values'] + '/sensors'
        if isinstance(filters, str):
            filters = [filters]
        results = set()
        for filt in filters:
            response = yield self._http_client.fetch("{}?sensors={}".format(url, filt))
            new_sensors = self._extract_sensors_details(response.body)
            # only add sensors once, to ensure a unique list
            for sensor in new_sensors:
                results.add(sensor['name'])
        raise tornado.gen.Return(list(results))

    @tornado.gen.coroutine
    def sensor_detail(self, sensor_name):
        """Return detailed attribute information for a sensor.

        For a list of sensor names, see :meth:`.sensors_list`.

        .. note::

            The websocket is not used for this request - it does not need
            to be connected.

        Parameters
        ----------
        sensor_name: str
            Exact sensor name - see description in :meth:`.set_sampling_strategy`.

        Returns
        -------
        dict:
            Detailed attribute information for the sensor.  Some of the
            more useful fields are indicated::

                { 'name': str,
                  'description': str,
                  'params': str,
                  'units': str,
                  'type': str,
                  'resource': str,
                  'katcp_name': str,
                  ... }

                name: str
                    Normalised sensor name, as requested in input parameters.
                description: str
                    Free text description of the sensor.
                params: str
                     Limits or possible states for the sensor value.
                units: str
                     Measurement units for sensor value, e.g. 'm/s'.
                type: str
                     Sensor type, e.g. 'float', 'discrete', 'boolean'
                resource: str
                     Name of resource that provides the sensor.
                katcp_name: str
                     Internal KATCP messaging name.

        Raises
        -------
        SensorNotFoundError:
            - If no information was available for the requested sensor name.
            - If the sensor name was not a unique match for a single sensor.
        """
        url = self.sitemap['historic_sensor_values'] + '/sensors'
        response = yield self._http_client.fetch("{}?sensors={}".format(url, sensor_name))
        results = self._extract_sensors_details(response.body)
        if len(results) == 0:
            raise SensorNotFoundError("Sensor name not found: " + sensor_name)
        elif len(results) > 1:
            raise SensorNotFoundError("Multiple sensors found - specify a single sensor "
                                      "not a pattern like: " + sensor_name)
        else:
            raise tornado.gen.Return(results[0])

    @tornado.gen.coroutine
    def sensor_history(self, sensor_name, start_time_sec, end_time_sec, include_value_ts=False, timeout_sec=300):
        """Return time history of sample measurements for a sensor.

        For a list of sensor names, see :meth:`.sensors_list`.

        Parameters
        ----------
        sensor_name: str
            Exact sensor name - see description in :meth:`.set_sampling_strategy`.
        start_time_sec: float
            Start time for sample history query, in seconds since the UNIX epoch
            (1970-01-01 UTC).
        end_time_sec: float
            End time for sample history query, in seconds since the UNIX epoch.
        include_value_ts: bool
            Flag to also include value timestamp in addition to time series sample timestamp in the result.
            Default: False.
        timeout_sec: float
            Maximum time (in sec) to wait for the history to be retrieved.  An exception will
            be raised if the request times out. (default:300)

        Returns
        -------
        list:
            List of :class:`.SensorSample` namedtuples (one per sample, with fields
            timestamp, value and status) or, if include_value_ts was set, then
            list of :class:`.SensorSampleValueTs` namedtuples (one per sample, with fields
            timestamp, value_timestamp, value and status).
            See :class:`.SensorSample` and :class:`.SensorSampleValueTs` for details.
            If the sensor named never existed, or is otherwise invalid, the
            list will be empty - no exception is raised.

        Raises
        -------
        SensorHistoryRequestError:
            - If there was an error submitting the request.
            - If the request timed out
        """
        # create new namespace and state variables per query, to allow multiple
        # request simultaneously
        state = {
            'sensor': sensor_name,
            'done_event': tornado.locks.Event(),
            'num_samples_pending': 0,
            'include_value_ts': include_value_ts,
            'samples': []
        }
        namespace = str(uuid.uuid4())
        self._sensor_history_states[namespace] = state
        # ensure connected, and subscribed before sending request
        yield self.connect()
        yield self.subscribe(namespace, ['*'])

        params = {
            'sensor': sensor_name,
            'time_type': SAMPLE_HISTORY_REQUEST_TIME_TYPE,
            'start': start_time_sec * SAMPLE_HISTORY_REQUEST_MULTIPLIER_TO_SEC,
            'end': end_time_sec * SAMPLE_HISTORY_REQUEST_MULTIPLIER_TO_SEC,
            'namespace': namespace,
            'request_in_chunks': 1,
            'chunk_size': SAMPLE_HISTORY_CHUNK_SIZE,
            'limit': MAX_SAMPLES_PER_HISTORY_QUERY
        }
        url = url_concat(self.sitemap['historic_sensor_values'] + '/samples', params)
        self._logger.debug("Sensor history request: %s", url)
        response = yield self._http_client.fetch(url)
        data = json.loads(response.body)
        if isinstance(data, dict) and data['result'] == 'success':
            download_start_sec = time.time()
            # Query accepted by portal - data will be returned via websocket, but
            # we need to wait until it has arrived.  For synchronisation, we wait
            # for a 'done_event'. This event is updated in _process_redis_message().
            try:
                timeout_delta = timedelta(seconds=timeout_sec)
                yield state['done_event'].wait(timeout=timeout_delta)

                self._logger.debug('Done in %d seconds, fetched %s samples.' % (
                    time.time() - download_start_sec,
                    len(state['samples'])))
            except tornado.gen.TimeoutError:
                raise SensorHistoryRequestError("Sensor history request timed out")

        else:
            raise SensorHistoryRequestError("Error requesting sensor history: {}"
                                            .format(response.body))

        def sort_by_timestamp(sample):
            return sample.timestamp
        # return a sorted copy, as data may have arrived out of order
        result = sorted(state['samples'], key=sort_by_timestamp)

        if len(result) >= MAX_SAMPLES_PER_HISTORY_QUERY:
            self._logger.warn(
                'Maximum sample limit (%d) hit - there may be more data available.',
                MAX_SAMPLES_PER_HISTORY_QUERY)

        # Free the state variables that were only required for the duration of
        # the download.  Do not disconnect - there may be websocket activity
        # initiated by another call.
        yield self.unsubscribe(namespace, ['*'])
        del self._sensor_history_states[namespace]

        raise tornado.gen.Return(result)

    @tornado.gen.coroutine
    def sensors_histories(self, filters, start_time_sec, end_time_sec, include_value_ts=False, timeout_sec=300):
        """Return time histories of sample measurements for multiple sensors.

        Finds the list of available sensors in the system that match the
        specified pattern, and then requests the sample history for each one.

        If only a single sensor's data is required, use :meth:`.sensor_history`.

        Parameters
        ----------
        filters: str or list of str
            List of regular expression patterns to match.
            See :meth:`.set_sampling_strategies` for more detail.
        start_time_sec: float
            Start time for sample history query, in seconds since the UNIX epoch
            (1970-01-01 UTC).
        end_time_sec: float
            End time for sample history query, in seconds since the UNIX epoch.
        include_value_ts: bool
            Flag to also include value timestamp in addition to time series sample timestamp in the result.
            Default: False.
        timeout_sec: float
            Maximum time to wait for all sensors' histories to be retrieved.
            An exception will be raised if the request times out.

        Returns
        -------
        dict:
            Dictonary of lists.  The keys are the full sensor names.
            The values are lists of :class:`.SensorSample` namedtuples,
            (one per sample, with fields timestamp, value and status)
            or, if include_value_ts was set, then
            list of :class:`.SensorSampleValueTs` namedtuples (one per sample, with fields
            timestamp, value_timestamp, value and status).
            See :class:`.SensorSample` and :class:`.SensorSampleValueTs` for details.

        Raises
        -------
        SensorHistoryRequestError:
            - If there was an error submitting the request.
            - If the request timed out
        SensorNotFoundError:
            - If any of the filters were invalid regular expression patterns.
        """
        request_start_sec = time.time()
        sensors = yield self.sensor_names(filters)
        histories = {}
        for sensor in sensors:
            elapsed_time_sec = time.time() - request_start_sec
            timeout_left_sec = timeout_sec - elapsed_time_sec
            histories[sensor] = yield self.sensor_history(
                sensor, start_time_sec, end_time_sec, timeout_left_sec)
        raise tornado.gen.Return(histories)


class ScheduleBlockNotFoundError(Exception):
    """Raise if requested schedule block is not found."""


class SensorNotFoundError(Exception):
    """Raise if requested sensor is not found."""


class SensorHistoryRequestError(Exception):
    """Raise if error requesting sensor sample history."""


class ReferenceObserverConfigNotSet(Exception):
    """Raise if reference observer config has not been set."""


class ScheduleBlockTargetsParsingError(Exception):
    """Raise if there was an error parsing the targets attribute of the
    ScheduleBlock"""
