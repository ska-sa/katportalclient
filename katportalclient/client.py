# Copyright 2015 SKA South Africa (http://ska.ac.za/)
# BSD license - see COPYING for details
"""
Websocket client and HTTP module for access to katportal webservers.
"""
from __future__ import division
from __future__ import absolute_import

from future import standard_library
standard_library.install_aliases()  # noqa: E402
import base64
import hashlib
import hmac
import logging
import time
import concurrent.futures

import omnijson as json
import tornado.gen
import tornado.httpclient
import tornado.ioloop
import tornado.locks

from builtins import bytes, object, str
from collections import namedtuple
from past.builtins import basestring
from urllib.parse import urlencode

from tornado.httpclient import HTTPRequest
from tornado.httputil import url_concat, HTTPHeaders
from tornado.ioloop import PeriodicCallback
from tornado.websocket import websocket_connect

from .request import JSONRPCRequest


MAX_SAMPLES_PER_HISTORY_QUERY = 1000000

# Websocket connect and reconnect timeouts
WS_CONNECT_TIMEOUT = 10
WS_RECONNECT_INTERVAL = 15
WS_HEART_BEAT_INTERVAL = 20000  # in milliseconds
# HTTP timeouts.  Note the request timeout includes time spent connecting,
# so it should not be less than the connect timeout.
HTTP_CONNECT_TIMEOUT = 20
HTTP_REQUEST_TIMEOUT = 60

module_logger = logging.getLogger('kat.katportalclient')


def create_jwt_login_token(email, password):
    """Creates a JWT login token. See http://jwt.io for the industry standard
    specifications.

    Parameters
    ----------
    email: str
        The email address of the user to include in the token. This email
        address needs to exist in the kaportal user database to be able to
        authenticate.
    password: str
        The password for the user specified in the email address to include
        in the JWT login token.

    Returns
    -------
    jwt_auth_token: str
        The authentication token to include in the HTTP Authorization header
        when verifying a user's credentials on katportal.
    """
    jwt_header_alg = base64.standard_b64encode(b'{"alg":"HS256","typ":"JWT"}')
    header_email = '{"email":"%s"}' % (email)
    header_email = bytes(header_email, encoding='utf-8')
    jwt_header_email = base64.standard_b64encode(header_email).strip(b'=')
    jwt_header = b'.'.join([jwt_header_alg, jwt_header_email])

    password = bytes(password, encoding='utf-8')
    password_sha = hashlib.sha256(password).hexdigest()
    password_sha = bytes(password_sha, encoding='utf-8')
    dig = hmac.new(password_sha, msg=jwt_header,
                   digestmod=hashlib.sha256).digest()
    password_encrypted = base64.b64encode(dig)
    jwt_auth_token = b'.'.join([jwt_header, password_encrypted])

    return jwt_auth_token


class SensorSample(namedtuple('SensorSample', 'sample_time, value, status')):
    """Class to represent all sensor samples.

    Fields:
        - sample_time:  float
            The timestamp (UNIX epoch) the sample was received by CAM.
            timestamp value is reported with at least millisecond precision.
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
        return '{:.6f},{},{}'.format(self.sample_time, self.value, self.status)


class SensorSampleValueTime(namedtuple(
        'SensorSampleValueTime', 'sample_time, value_time, value, status')):
    """Class to represent sensor samples, including the value_time.

    Fields:
        - sample_time:  float
            The timestamp (UNIX epoch) the sample was received by CAM.
            Timestamp value is reported with at least millisecond precision.
        - value_time:  float
            The timestamp (UNIX epoch) the sample was read at the lowest level sensor.
            value_timestamp value is reported with at least millisecond precision.
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
        return '{:.6f},{:.6f},{},{}'.format(
            self.sample_time, self.value_time, self.value, self.status)


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
        self._http_client = tornado.httpclient.AsyncHTTPClient(
            defaults=dict(connect_timeout=HTTP_CONNECT_TIMEOUT,
                          request_timeout=HTTP_REQUEST_TIMEOUT))
        self._sitemap = None
        self._reference_observer_config = None
        self._disconnect_issued = False
        self._ws_jsonrpc_cache = []
        self._heart_beat_timer = PeriodicCallback(
            self._send_heart_beat, WS_HEART_BEAT_INTERVAL)
        self._current_user_id = None

    @tornado.gen.coroutine
    def logout(self):
        """ Logs user out of katportal. Katportal then deletes the cached
        session_id for this client. In order to call HTTP requests that
        requires authentication, the user will need to login again.
        """
        try:
            if self._session_id is not None:
                url = (yield self.get_sitemap())['authorization'] + '/user/logout'
                response = yield self.authorized_fetch(
                    url=url, auth_token=self._session_id, method='POST', body='{}')
                self._logger.info("Logout result: %s", response.body)
        finally:
            # Clear the local session_id, no matter what katportal says
            self._session_id = None
            self._current_user_id = None

    @tornado.gen.coroutine
    def login(self, username, password, role='read_only'):
        """
        Logs the specified user into katportal and caches the session_id
        created by katportal in this instance of KatportalClient.

        Parameters
        ----------
        username: str
            The registered username that exists on katportal. This is an
            email address, like abc@ska.ac.za.

        password: str
            The password for the specified username as saved in the katportal
            users database.

        """
        login_token = create_jwt_login_token(username, password)
        authorization = (yield self.get_sitemap())['authorization']
        url = authorization + '/user/verify/' + role
        response = yield self.authorized_fetch(url=url, auth_token=login_token)

        try:
            response_json = json.loads(response.body)
            if not response_json.get('logged_in',
                                     False) or response_json.get('session_id'):
                self._session_id = response_json.get('session_id')
                self._current_user_id = response_json.get('user_id')

                login_url = authorization + '/user/login'
                response = yield self.authorized_fetch(
                    url=login_url, auth_token=self._session_id,
                    method='POST', body='')

                self._logger.info('Succesfully logged in as %s',
                                  response_json.get('email'))
            else:
                self._session_id = None
                self._current_user_id = None
                self._logger.error('Error in logging see response %s',
                                   response)
        except Exception:
            self._session_id = None
            self._current_user_id = None
            self._logger.exception('Error in response')

    @tornado.gen.coroutine
    def authorized_fetch(self, url, auth_token, **kwargs):
        """
        Wraps tornado.fetch to add the Authorization headers with
        the locally cached session_id.
        """
        if isinstance(auth_token, bytes):
            auth_token = auth_token.decode()
        login_header = HTTPHeaders({
            "Authorization": "CustomJWT {}".format(auth_token)})
        request = HTTPRequest(
            url, headers=login_header, **kwargs)
        response = yield self._http_client.fetch(request)
        raise tornado.gen.Return(response)

    @tornado.gen.coroutine
    def _get_sitemap(self, url):
        """
        Fetches the sitemap from the specified URL.

        See :meth:`.get_sitemap` for details, including the return value. This
        function may be run on a worker thread, so it must take care not to
        touch any members that are not thread-safe.

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
            'authorization': '',
            'historic_sensor_values': '',
            'program_blocks': '',
            'schedule_blocks': '',
            'capture_blocks': '',
            'sub_nr': '',
            'subarray': '',
            'target_descriptions': '',
            'userlogs': '',
            'websocket': '',
        }
        if (url.lower().startswith('http://') or
                url.lower().startswith('https://')):
            http_client = tornado.httpclient.AsyncHTTPClient(force_instance=True)
            try:
                try:
                    response = yield http_client.fetch(url)
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
        raise tornado.gen.Return(result)

    @tornado.gen.coroutine
    def _init_sitemap(self):
        """Initializes the sitemap if it is not already initialized.

        See :meth:`.get_sitemap` for details.
        """

        if not self._sitemap:
            self._sitemap = yield self._get_sitemap(self._url)
            self._logger.debug("Sitemap: %s.", self._sitemap)

    @property
    def sitemap(self):
        """
        Returns the sitemap using the URL specified during instantiation.

        This method is kept for convenience and backwards compatibility, but
        should not be used in code that runs on a Tornado event loop as it
        may block the event loop if the sitemap has not yet been retrieved.
        Use :meth:`.get_sitemap` instead.
        """
        if not self._sitemap:
            # Properties can't be asynchronous, so we have to resort to a
            # separate IOLoop on a helper thread to do the work. Using
            # Tornado's synchronous HTTPClient works in older Tornado
            # versions, but fails on newer ones because it's implemented
            # with IOLoop.run_sync and asyncio doesn't allow a secondary
            # event loop to be used on the same thread as the primary.
            def worker():
                io_loop = tornado.ioloop.IOLoop()
                sitemap = io_loop.run_sync(lambda: self._get_sitemap(self._url))
                io_loop.close()
                return sitemap

            self._logger.warning("Fetching sitemap synchronously")
            with concurrent.futures.ThreadPoolExecutor(1) as executor:
                self._sitemap = executor.submit(worker).result()
        return self._sitemap

    @tornado.gen.coroutine
    def get_sitemap(self):
        """
        Returns the sitemap using the URL specified during instantiation.

        The portal webserver provides a sitemap with a number of URLs.  The
        endpoints could change over time, but the keys to access them will not.
        The websever is only queried once, the first time the property is
        accessed.  Typically users will not need to access the sitemap
        directly - the class's methods make use of it.

        The sitemap can also be accessed synchronously via the :meth:`.sitemap`
        property, but that may block the Tornado event loop the first time it
        used.

        Returns
        -------
        dict:
            Sitemap endpoints, will include at least the following::

                { 'websocket': str,
                  'historic_sensor_values': str,
                  'schedule_blocks': str,
                  'capture_blocks': str,
                  'sub_nr': str,
                  ... }

                websocket: str
                    Websocket URL for Pub/Sub access.
                historic_sensor_values: str
                    URL for requesting sensor value history.
                schedule_blocks: str
                    URL for requesting observation schedule block information.
                capture_blocks: str
                    URL for requesting observation capture block information.
                sub_nr: str
                    Subarray number to access (e.g. '1', '2', '3', or '4').
                subarray_sensor_values: str
                    URL for requesting once off current sensor values.
                target_descriptions: str
                    URL for requesting target pointing descriptions for a
                    specified schedule block

        """
        yield self._init_sitemap()
        raise tornado.gen.Return(self._sitemap)

    @staticmethod
    def _parse_sub_nr(sitemap):
        """Implementation of :meth:`.sub_nr` and :meth:`.get_sub_nr`."""
        try:
            sub_nr = int(sitemap['sub_nr'])
        except ValueError:
            raise SubarrayNumberUnknown(
                "Connection URL is not subarray-specific - sitemap sub_nr: '{}'"
                .format(sitemap['sub_nr']))
        return sub_nr

    @property
    def sub_nr(self):
        """Returns subarray number, if available.

        This is equivalent to :meth:`.get_sub_nr`, but synchronous. It will
        block the Tornado event loop if the sitemap has not yet been
        retrieved, so :meth:`.get_sub_nr` is preferred.
        """
        return self._parse_sub_nr(self.sitemap)

    @tornado.gen.coroutine
    def get_sub_nr(self):
        """Returns subarray number, if available.

        This number is based on the URL used to connect to
        katportal, provided during instantiation.

        Returns
        -------
        sub_nr: int
            Subarray number.

        Raises
        ------
        SubarrayNumberUnknown:
            - If the subarray number could not be determined.
        """
        sub_nr = self._parse_sub_nr((yield self.get_sitemap()))
        raise tornado.gen.Return(sub_nr)

    @property
    def is_connected(self):
        """Return True if websocket is connected."""
        return self._ws is not None

    @tornado.gen.coroutine
    def _connect(self, reconnecting=False):
        """
        Connect the websocket connection specified during instantiation.
        When the connection drops, katportalclient will periodically attempt
        to reconnect by calling this method until a disconnect() is called.

        Params
        ------
        reconnecting: bool
            Must be True if this method was called to reconnect a previously connected
            websocket connection. If this is True the websocket connection will attempt
            to resend the subscriptions and sampling strategies that was sent while the
            websocket connection was open. If the websocket connection cannot reconnect,
            it will try again periodically. If this is false and the websocket cannot be
            connected, no further attempts will be made to connect.
        """
        # The lock is used to ensure only a single connection can be made
        with (yield self._ws_connecting_lock.acquire()):
            self._disconnect_issued = False
            websocket_url = (yield self.get_sitemap())['websocket']
            if not self.is_connected:
                self._logger.debug(
                    "Connecting to websocket %s", websocket_url)
                try:
                    if self._heart_beat_timer.is_running():
                        self._heart_beat_timer.stop()
                    self._ws = yield websocket_connect(
                        websocket_url,
                        on_message_callback=self._websocket_message,
                        connect_timeout=WS_CONNECT_TIMEOUT)
                    if reconnecting:
                        yield self._resend_subscriptions_and_strategies()
                        self._logger.info("Reconnected :)")
                    self._heart_beat_timer.start()
                except Exception:
                    self._logger.exception(
                        'Could not connect websocket to %s',
                        websocket_url)
                    if reconnecting:
                        self._logger.info(
                            'Retrying connection in %s seconds...', WS_RECONNECT_INTERVAL)
                        self._connect_later(WS_RECONNECT_INTERVAL)
                if not self.is_connected and not reconnecting:
                    self._logger.error("Failed to connect!")

    def _connect_later(self, wait_time):
        """Schedule later connection attempt."""
        # Trivial function, but useful for unit testing
        self._io_loop.call_later(wait_time, self._connect, True)

    @tornado.gen.coroutine
    def connect(self):
        """Connect to the websocket server specified during instantiation."""
        yield self._connect(reconnecting=False)

    @tornado.gen.coroutine
    def _send_heart_beat(self):
        """
        Sends a PING message to katportal to test if the websocket connection is still
        alive. If there is an error sending this message, tornado will call the
        _websocket_message callback function with None as the message, where we realise
        that the websocket connection has failed.
        """
        if self._ws is not None:
            self._ws.write_message('PING')
        else:
            self._logger.debug('Attempting to send a PING over a closed websocket!')

    def disconnect(self):
        """Disconnect from the connected websocket server."""
        if self._heart_beat_timer.is_running():
            self._heart_beat_timer.stop()

        self._disconnect_issued = True
        self._ws_jsonrpc_cache = []
        self._logger.debug("Cleared JSONRPCRequests cache.")

        if self.is_connected:
            self._ws.close()
            self._ws = None
            self._logger.debug("Disconnected client websocket.")

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

        JSONRPCRequests with identical methods and params will not be cached more than
        once.
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
            duplicate_found = False
            for req in self._ws_jsonrpc_cache:
                # check if there is a difference between the items in the dict of existing
                # JSONRPCRequests, if we find that we already have this JSONRPCRequest in
                # the cache, don't add it to the cache.
                duplicate_found = (req.method_and_params_hash() ==
                                   jsonrpc_request.method_and_params_hash())
                if duplicate_found:
                    break
            if not duplicate_found:
                self._ws_jsonrpc_cache.append(jsonrpc_request)

        for req in requests_to_remove:
            self._ws_jsonrpc_cache.remove(req)

    @tornado.gen.coroutine
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

    @tornado.gen.coroutine
    def _resend_subscriptions(self):
        """
        Resend the cached subscriptions only. This is necessary when we receive
        a redis-reconnect server message."""
        for req in self._ws_jsonrpc_cache:
            if req.method == 'subscribe':
                self._logger.info('Resending JSONRPCRequest %s', req)
                result = yield self._send(req)
                self._logger.info(
                    'Resent JSONRPCRequest, with result: %s', result)

    @tornado.gen.coroutine
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
                if self._ws is not None:
                    self._ws.close()
                    self._ws = None
                yield self._connect(reconnecting=True)
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
                yield self._resend_subscriptions()
            else:
                self._process_json_rpc_message(msg, msg_id)
        except Exception:
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
            (i.e. underscores Python identifiers).

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

        Raises
        ------
        SubarrayNumberUnknown:
            - If a subarray number could not be determined.
        """
        url = (yield self.get_sitemap())['schedule_blocks'] + '/scheduled'
        response = yield self._http_client.fetch(url)
        results = self._extract_schedule_blocks(response.body, (yield self.get_sub_nr()))
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
            [
                {
                    "track_start_offset":39.8941187859,
                    "target":"PKS 0023-26 | J0025-2602 | OB-238, radec, "
                             "0:25:49.16, -26:02:12.6, "
                             "(1410.0 8400.0 -1.694 2.107 -0.4043)",
                    "track_duration":20.0
                },
                {
                    "track_start_offset":72.5947952271,
                    "target":"PKS 0043-42 | J0046-4207, radec, "
                             "0:46:17.75, -42:07:51.5, "
                             "(400.0 2000.0 3.12 -0.7)",
                    "track_duration":20.0
                },
                {
                    "track_start_offset":114.597304821,
                    "target":"PKS 0408-65 | J0408-6545, radec, "
                             "4:08:20.38, -65:45:09.1, "
                             "(1410.0 8400.0 -3.708 3.807 -0.7202)",
                    "track_duration":20.0
                }
            ]
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
            except Exception:
                raise ScheduleBlockTargetsParsingError(
                    'There was an error parsing the schedule block (%s) '
                    'targets attribute: %s', id_code, sb_targets)
        raise tornado.gen.Return(targets_list)

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
                                   the system
                capture_block_id:
                    Capture block identifier set when capture session initiates.
                    For example: ``1555494792``.
                sub_nr: int
                    The number of the subarray the observation is scheduled on.

        Raises
        -------
        ScheduleBlockNotFoundError:
            If no information was available for the requested schedule block.
        """
        url = (yield self.get_sitemap())['schedule_blocks'] + '/' + id_code
        response = yield self._http_client.fetch(url)
        response = json.loads(response.body)
        schedule_block = response['result']
        if not schedule_block:
            raise ScheduleBlockNotFoundError(
                "Invalid schedule block ID: " + id_code)
        raise tornado.gen.Return(schedule_block)

    @tornado.gen.coroutine
    def sb_ids_by_capture_block(self, capture_block_id):
        """Return list of observation schedule blocks associated with the given
        capture block ID.

        Capture block IDs are provided by SDP and link to the science data
        archive.

        .. note::

            The websocket is not used for this request - it does not need
            to be connected.

        Parameters
        ----------
        capture_block_id: str
            Capture block identifier. For example: '1556067480'.

        Returns
        -------
        list:
            List of matching schedule block ID strings.  Could be empty.

        """
        url = (yield self.get_sitemap())['capture_blocks'] + '/sb/' + capture_block_id
        response = yield self._http_client.fetch(url)
        response = json.loads(response.body)
        schedule_block_ids = response['result']
        raise tornado.gen.Return(schedule_block_ids)

    def _extract_sensors_details(self, json_text):
        """Extract and return list of sensor names from a JSON response."""
        sensors = json.loads(json_text)
        results = []
        # Errors are returned in dict, while valid data is returned in a list.
        if isinstance(sensors, dict):
            if 'error' in sensors:
                raise SensorNotFoundError(
                    "Invalid sensor request: " + sensors['error'])
            elif 'data' in sensors:
                results = sensors['data']
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
        url = (yield self.get_sitemap())['historic_sensor_values'] + '/sensors'
        if isinstance(filters, basestring):
            filters = [filters]
        results = set()
        for filt in filters:
            query_url = url_concat(url, {"sensors": filt})
            response = yield self._http_client.fetch(query_url)
            new_sensors = self._extract_sensors_details(response.body)
            # only add sensors once, to ensure a unique list
            for sensor in new_sensors:
                results.add(sensor['name'])
        raise tornado.gen.Return(sorted(results))

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
                  'component': str,
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
                component: str
                     Name of component that provides the sensor.
                katcp_name: str
                     Internal KATCP messaging name.

        Raises
        -------
        SensorNotFoundError:
            - If no information was available for the requested sensor name.
            - If the sensor name was not a unique match for a single sensor.
        """
        url = (yield self.get_sitemap())['historic_sensor_values'] + '/sensors'
        response = yield self._http_client.fetch("{}?sensors={}".format(url, sensor_name))
        results = self._extract_sensors_details(response.body)
        if len(results) == 0:
            raise SensorNotFoundError("Sensor name not found: " + sensor_name)
        elif len(results) > 1:
            # check for exact match, before giving up
            for result in results:
                if result['name'] == sensor_name:
                    attrs = result.get('attributes')
                    result = {'name': result.get('name'),
                              'description': attrs.get('description'),
                              'params': attrs.get('params'),
                              'katcp_name': attrs.get('original_name'),
                              'units': attrs.get('units'),
                              'type': attrs.get('type'),
                              'component': result.get('component')}
                    raise tornado.gen.Return(result)
            raise SensorNotFoundError(
                "Multiple sensors ({}) found - specify a single sensor "
                "name not a pattern like: '{}'.  (Some matches: {})."
                .format(len(results),
                        sensor_name,
                        [result['name'] for result in results[0:5]]))
        else:
            attrs = results[0].get('attributes')
            result = {'name': results[0].get('name'),
                      'description': attrs.get('description'),
                      'params': attrs.get('params'),
                      'katcp_name': attrs.get('original_name'),
                      'units': attrs.get('units'),
                      'type': attrs.get('type'),
                      'component': results[0].get('component')}
            raise tornado.gen.Return(result)

    @tornado.gen.coroutine
    def sensor_value(self, sensor_name, include_value_ts=False):
        """Return the latest reading of a sensor.

        .. note::

            The websocket is not used for this request - it does not need
            to be connected.

        Parameters
        ----------
        sensor_name: str
            Exact sensor name. No regular expressions allowed.
            To get a list of sensor names based off regular expressions, see
            :meth:`.sensor_names`.
        include_value_ts: bool
            Flag to also include value timestamp.
            Default: False.

        Returns
        -------
        namedtuple:
            Instance of :class:`.SensorSampleValueTime` if `include_value_ts` is `True`,
            otherwise an instance of :class:`.SensorSample`

        Raises
        -------
        SensorNotFoundError:
            - If no information was available for the requested sensor name.
        InvalidResponseError:
            - When the katportal service returns invalid JSON
        """
        url = (yield self.get_sitemap())['monitor'] + '/list-sensors/all'

        response = yield self._http_client.fetch(
            "{}?reading_only=1&name_filter=^{}$".format(url, sensor_name))
        try:
            results = json.loads(response.body)
        except json.JSONError:
            raise InvalidResponseError(
                "Request to {} did not respond with valid JSON".format(url))

        if len(results) == 0:
            raise SensorNotFoundError("Value for sensor {} not found".format(sensor_name))

        result_to_format = None

        if len(results) > 1:
            # check for exact match, before giving up
            for result in results:
                if result['name'] == sensor_name:
                    result_to_format = result
                    break
            else:
                raise SensorNotFoundError(
                    "Multiple sensors ({}) found - specify a single sensor "
                    "name not a pattern like: '{}'.  (Some matches: {})."
                    .format(len(results),
                            sensor_name,
                            [result['name'] for result in results[0:5]]))
        else:
            result_to_format = results[0]

        if include_value_ts:
            raise tornado.gen.Return(SensorSampleValueTime(
                sample_time=result_to_format['time'],
                value_time=result_to_format['value_ts'],
                value=result_to_format['value'],
                status=result_to_format['status']))
        else:
            raise tornado.gen.Return(SensorSample(
                sample_time=result_to_format['time'],
                value=result_to_format['value'],
                status=result_to_format['status']))

    @tornado.gen.coroutine
    def sensor_values(self, filters, include_value_ts=False):
        """Return a list of latest readings of the sensors matching the
        specified pattern.

        Parameters
        ----------
        filters: str or list of str
            List of regular expression patterns to match.

            e.g. '((m0\\d\\d)|(s0\\d\\d\\d))_observer' will return the
            'observer' sensor reading for all antennas.

            See :meth:`.set_sampling_strategies` for more detail.
        include_value_ts: bool
            Flag to also include value timestamp.
            Default: False.

        Returns
        -------
        dict:
            Dict of sensor name strings and their latest readings.

        Raises
        -------
        SensorNotFoundError:
            - If no information was available for the requested filter.
        InvalidResponseError:
            - When the katportal service returns invalid JSON
        """
        url = (yield self.get_sitemap())['monitor'] + '/list-sensors/all'

        if isinstance(filters, basestring):
            filters = [filters]

        results_to_return = {}

        for filt in filters:
            query_url = url_concat(url, {"reading_only": "1", "name_filter": filt})
            response = yield self._http_client.fetch(query_url)
            try:
                results = json.loads(response.body)
            except json.JSONError:
                raise InvalidResponseError(
                    "Request to {} did not respond with valid JSON".format(url))

            if len(results) == 0:
                raise SensorNotFoundError("No values for filter {} found".format(filt))

            for result in results:
                if include_value_ts:
                    results_to_return[result['name']] = SensorSampleValueTime(
                        sample_time=result['time'],
                        value_time=result['value_ts'],
                        value=result['value'],
                        status=result['status'])
                else:
                    results_to_return[result['name']] = SensorSample(
                        sample_time=result['time'],
                        value=result['value'],
                        status=result['status'])

        raise tornado.gen.Return(results_to_return)

    @tornado.gen.coroutine
    def sensor_history(self, sensor_name, start_time_sec, end_time_sec,
                       include_value_ts=False, timeout_sec=0):
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
            Flag to also include value sample_time in addition to time series
            sample time in the result.
            Default: False.
        timeout_sec: int
            This parameter is no longer support. Here for backwards compatibility

        Returns
        -------
        list:
            List of :class:`.SensorSample` namedtuples (one per sample, with fields
            sample_time, value and status) or, if include_value_time was set, then
            list of :class:`.SensorSampleValueTime` namedtuples (one per sample, with fields
            sample_time, value_time, value and status).
            See :class:`.SensorSample` and :class:`.SensorSampleValueTime` for details.
            If the sensor named never existed, or is otherwise invalid, the
            list will be empty - no exception is raised.

        Raises
        -------
        SensorHistoryRequestError:
            - If there was an error submitting the request.
            - If the request timed out
        """

        if timeout_sec != 0:
            self._logger.warn(
                "timeout_sec is no longer supported. Default tornado timeout is used")

        params = {
            'sensor': sensor_name,
            'start_time': start_time_sec,
            'end_time': end_time_sec,
            'limit': MAX_SAMPLES_PER_HISTORY_QUERY,
            'include_value_time': include_value_ts
        }

        url = url_concat(
            (yield self.get_sitemap())['historic_sensor_values'] + '/query', params)
        self._logger.debug("Sensor history request: %s", url)
        response = yield self._http_client.fetch(url)
        data_json = json.loads(response.body)
        if 'data' not in data_json:
            raise SensorHistoryRequestError("Error requesting sensor history: {}"
                                            .format(response.body))
        data = []
        for item in data_json['data']:
            if 'value_time' in item:
                sample = SensorSampleValueTime(item['sample_time'],
                                               item['value_time'],
                                               item['value'],
                                               item['status'])
            else:
                sample = SensorSample(item['sample_time'],
                                      item['value'],
                                      item['status'])
            data.append(sample)
        result = sorted(data, key=_sort_by_sample_time)
        raise tornado.gen.Return(result)

    @tornado.gen.coroutine
    def sensors_histories(self, filters, start_time_sec, end_time_sec,
                          include_value_ts=False, timeout_sec=0):
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
            Flag to also include value sample_time in addition to time series
            sample sample in the result.
            Default: False.
        timeout_sec: int
            This parameter is no longer support. Here for backwards compatibility

        Returns
        -------
        dict:
            Dictionary of lists.  The keys are the full sensor names.
            The values are lists of :class:`.SensorSample` namedtuples,
            (one per sample, with fields sample_time, value and status)
            or, if include_value_time was set, then
            list of :class:`.SensorSampleValueTime` namedtuples (one per sample,
            with fields sample_time, value_time, value and status).
            See :class:`.SensorSample` and :class:`.SensorSampleValueTime` for details.

        Raises
        -------
        SensorHistoryRequestError:
            - If there was an error submitting the request.
            - If the request timed out
        SensorNotFoundError:
            - If any of the filters were invalid regular expression patterns.
        """

        sensors = yield self.sensor_names(filters)
        histories = {}
        for sensor in sensors:
            histories[sensor] = yield self.sensor_history(
                sensor, start_time_sec, end_time_sec,
                include_value_ts=include_value_ts, timeout_sec=timeout_sec)
        raise tornado.gen.Return(histories)

    @tornado.gen.coroutine
    def userlog_tags(self):
        """Return all userlog tags in the database.

        Returns
        -------
        list:
            List of userlog tags in the database. Example:

            [{
                'activated': True,
                'slug': '',
                'name': 'm047',
                'id': 1
            },
            {
                'activated': True,
                'slug': '',
                'name': 'm046',
                'id': 2
            },
            {
                'activated': True,
                'slug': '',
                'name': 'm045',
                'id': 3},
            {..}]

        """
        url = (yield self.get_sitemap())['userlogs'] + '/tags'
        response = yield self._http_client.fetch(url)
        raise tornado.gen.Return(json.loads(response.body))

    @tornado.gen.coroutine
    def userlogs(self, start_time=None, end_time=None):
        """
        Return a list of userlogs in the database that has an start_time
        and end_time combination that intersects with the given start_time
        and end_time. For example of an userlog has a start_time before the
        given start_time and an end time after the given end_time, the time
        window of that userlog intersects with the time window of the given
        start_time and end_time.

        If an userlog has no end_time, an end_time of infinity is assumed.
        For example, if the given end_time is after the userlog's start time,
        there is an intersection of the two time windows.

        Here are some visual representations of the time window intersections:

                                Start       End
        Userlog:                  [----------]
        Search params:                 [-----------------]
                                      Start              End

                                              Start       End
        Userlog:                                [----------]
        Search params:              [-----------------]
                                  Start              End

                                 Start                End
        Userlog:                  [--------------------]
        Search params:                 [---------]
                                     Start      End

                                 Start     End
        Userlog:                  [---------]
        Search params:     [-------------------------]
                         Start                      End

                                              Start
        Userlog:                                [-------------------*
        Search params:              [-----------------]
                                  Start              End

                                                    End
        Userlog:             *-----------------------]
        Search params:                      [-----------------]
                                          Start              End

        Userlog:            *--------------------------------------*
        Search params:              [-----------------]
                                  Start              End
        Parameters
        ----------
        start_time: str
            A formatted UTC datetime string used as the start of the time window
            to query. Format: %Y-%m-%d %H:%M:%S.
            Default: Today at %Y-%m-%d 00:00:00 (The day of year is selected from local
                     time but the time portion is in UTC. Example if you are at SAST, and
                     you call this method at 2017-01-01 01:00:00 AM SAST, the date portion
                     of start_time will be selected from local time: 2017-01-01.
                     The start_time is, however, saved as UTC, so this default will be
                     2017-01-01 00:00:00 AM UTC and NOT 2016-12-31 00:00:00 AM UTC)
        end_time: str
            A formatted UTC datetime string used as the end of the time window
            to query. Format: %Y-%m-%d %H:%M:%S.
            Default: Today at %Y-%m-%d 23:59:59 (The day of year is selected from local
                     time but the time portion is in UTC. Example if you are at SAST, and
                     you call this method at 2017-01-01 01:00:00 AM SAST, the date portion
                     of end_time will be selected from local time: 2017-01-01.
                     The end_time is, however, saved as UTC, so this default will be
                     2017-01-01 23:59:59 UTC and NOT 2016-12-31 23:59:59 UTC)

        Returns
        -------
        list:
            List of userlog that intersects with the give start_time and
            end_time. Example:

            [{
                'other_metadata': [],
                'user_id': 1,
                'attachments': [],
                'tags': '[]',
                'timestamp': '2017-02-07 08:47:22',
                'start_time': '2017-02-07 00:00:00',
                'modified': '',
                'content': 'katportalclient userlog creation content!',
                'parent_id': '',
                'user': {'email': 'cam@ska.ac.za', 'id': 1, 'name': 'CAM'},
                'attachment_count': 0,
                'id': 40,
                'end_time': '2017-02-07 23:59:59'
             }, {..}]
        """
        url = (yield self.get_sitemap())['userlogs'] + '/query?'
        if start_time is None:
            start_time = time.strftime('%Y-%m-%d 00:00:00')
        if end_time is None:
            end_time = time.strftime('%Y-%m-%d 23:59:59')
        request_params = {
            'start_time': start_time,
            'end_time': end_time
        }
        query_string = urlencode(request_params)
        response = yield self.authorized_fetch(
            url='{}{}'.format(url, query_string), auth_token=self._session_id)
        raise tornado.gen.Return(json.loads(response.body))

    @tornado.gen.coroutine
    def create_userlog(self, content, tag_ids=None, start_time=None,
                       end_time=None):
        """
        Create a userlog with specified linked tags and content, start_time
        and end_time.

        Parameters
        ----------
        content: str
            The content of the userlog, could be any text. Required.

        tag_ids: list
            A list of tag id's to link to this userlog.
            Example: [1, 2, 3, ..]
            Default: None

        start_time: str
            A formatted datetime string used as the start time of the userlog in UTC.
            Format: %Y-%m-%d %H:%M:%S.
            Default: None

        end_time: str
            A formatted datetime string used as the end time of the userlog in UTC.
            Format: %Y-%m-%d %H:%M:%S.
            Default: None

        Returns
        -------
        userlog: dict
            The userlog that was created. Example:
            {
                'other_metadata': [],
                'user_id': 1,
                'attachments': [],
                'tags': '[]',
                'timestamp': '2017-02-07 08:47:22',
                'start_time': '2017-02-07 00:00:00',
                'modified': '',
                'content': 'katportalclient userlog creation content!',
                'parent_id': '',
                'user': {'email': 'cam@ska.ac.za', 'id': 1, 'name': 'CAM'},
                'attachment_count': 0,
                'id': 40,
                'end_time': '2017-02-07 23:59:59'
             }
        """
        url = (yield self.get_sitemap())['userlogs']
        new_userlog = {
            'user': self._current_user_id,
            'content': content
        }
        if start_time is not None:
            new_userlog['start_time'] = start_time
        if end_time is not None:
            new_userlog['end_time'] = end_time
        if tag_ids is not None:
            new_userlog['tag_ids'] = tag_ids

        response = yield self.authorized_fetch(
            url=url, auth_token=self._session_id,
            method='POST', body=json.dumps(new_userlog))
        raise tornado.gen.Return(json.loads(response.body))

    @tornado.gen.coroutine
    def modify_userlog(self, userlog, tag_ids=None):
        """
        Modify an existing userlog using the dictionary provided as the
        modified attributes of the userlog.

        Parameters
        ----------
        userlog: dict
            The userlog with the new values to be modified.

        tag_ids: list
            A list of tag id's to link to this userlog. Optional, if this is
            not specified, the tags attribute of the given userlog will be
            used.
            Example: [1, 2, 3, ..]

        Returns
        -------
        userlog: dict
            The userlog that was modified. Example:
            {
                'other_metadata': [],
                'user_id': 1,
                'attachments': [],
                'tags': '[]',
                'timestamp': '2017-02-07 08:47:22',
                'start_time': '2017-02-07 00:00:00',
                'modified': '',
                'content': 'katportalclient userlog modified content!',
                'parent_id': '',
                'user': {'email': 'cam@ska.ac.za', 'id': 1, 'name': 'CAM'},
                'attachment_count': 0,
                'id': 40,
                'end_time': '2017-02-07 23:59:59'
             }
        """
        if tag_ids is None and 'tags' in userlog:
            try:
                userlog['tag_ids'] = [
                    tag_id for tag_id in json.loads(userlog['tags'])]
            except Exception:
                self._logger.exception(
                    'Could not parse the tags field of the userlog: %s', userlog)
                raise
        else:
            userlog['tag_ids'] = tag_ids
        url = '{}/{}'.format((yield self.get_sitemap())['userlogs'], userlog['id'])
        response = yield self.authorized_fetch(
            url=url, auth_token=self._session_id,
            method='POST', body=json.dumps(userlog))
        raise tornado.gen.Return(json.loads(response.body))

    @tornado.gen.coroutine
    def sensor_subarray_lookup(self, component, sensor, return_katcp_name=False):
        """Return full sensor name for generic component and sensor names.

        This method gets the full sensor name based on a generic component and
        sensor name, for a subarray.  The subarray queried is determined by
        the URL used during instantiation.  This method will raise an exception
        if the subarray is not in the 'active' or 'initialising' states.

        .. note::

            The websocket is not used for this request - it does not need
            to be connected.

        Parameters
        ----------

        component: str
            The component that has the sensor to look up.

        sensor: str or None
            The generic sensor to look up.  Can be empty or None, in
            which case just the component is looked up.

        katcp_name: bool (optional)
            True to return the katcp name, False to return the fully qualified
            Python sensor name. Default is False.

        Returns
        -------
        str:
            The full sensor name based on the given component and subarray,
            or just full component name, if no sensor was given.

        Raises
        ------
        SensorLookupError:
            - If the requested parameters could not be looked up.
        SubarrayNumberUnknown:
            - If a subarray number could not be determined.
        """
        if sensor is None or len(sensor.strip()) == 0:
            sensor = r'%20'  # use single space for component-only lookup
        url = (
            "{base_url}/{sub_nr}/sensor-lookup/{component}/{sensor}/{katcp_format}"
            .format(
                base_url=(yield self.get_sitemap())['subarray'],
                sub_nr=(yield self.get_sub_nr()),
                component=component,
                sensor=sensor,
                katcp_format=1 if return_katcp_name else 0))
        response = yield self._http_client.fetch(url)
        data = json.loads(response.body)
        if 'error' in data:
            raise SensorLookupError(data['error'])
        else:
            raise tornado.gen.Return(data['result'])


class ScheduleBlockNotFoundError(Exception):
    """Raise if requested schedule block is not found."""


class SensorNotFoundError(Exception):
    """Raise if requested sensor is not found."""


class SensorHistoryRequestError(Exception):
    """Raise if error requesting sensor sample history."""


class ScheduleBlockTargetsParsingError(Exception):
    """Raise if there was an error parsing the targets attribute of the
    ScheduleBlock"""


class SubarrayNumberUnknown(Exception):
    """Raised when subarray number is unknown"""


class SensorLookupError(Exception):
    """Raise if requested sensor lookup failed."""


class InvalidResponseError(Exception):
    """Raise if server response was invalid."""


def _sort_by_sample_time(sample):
    return float(sample.sample_time)
