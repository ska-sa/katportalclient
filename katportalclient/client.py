"""
Websocket client module providing wrapper functions as available on
katportal webservers support websockets and the PubSub capability.
"""

import logging

import tornado.gen
import tornado.ioloop
import omnijson as json
from tornado.websocket import websocket_connect

from request import JSONRPCRequest


module_logger = logging.getLogger('kat.katportalclient')


class KATPortalClient(object):
    """
    Katportal client class serving as a websocket client and wrappingx
    functions as available on katportal webservers for the PubSub capability.
    """

    def __init__(self, ws_url, on_update_callback,
                 io_loop=None, logger=None):
        """Initialise method.

        Parameters
        ----------
        ws_url: str
            Websocket server url to connect to.
        on_update_callback: function
            Callback that should be invoked every time a PubSub update message
            is received. Signature has to include a single argument for the
            message, e.g. `def on_update(message)`.
        io_loop: tornado.ioloop.IOLoop
            Optional IOLoop instance (default=None).
        logger: logging.Logger
            Optional logger instance (default=None).
        """
        self._logger = logger or module_logger
        self._ws = None
        self._ws_url = ws_url
        self._io_loop = io_loop or tornado.ioloop.IOLoop.current()
        self._on_update = on_update_callback
        self._pending_requests = {}

    @property
    def is_connected(self):
        return self._ws is not None

    @tornado.gen.coroutine
    def connect(self):
        """Connect to the websocket server specified during instantiation."""
        if not self.is_connected:
            # TODO(TA): check the connect_timeout option
            self._ws = yield websocket_connect(
                self._ws_url, io_loop=self._io_loop)
            if self.is_connected:
                self._io_loop.add_callback(self._run)
            else:
                self._logger.error("Failed to connect!")

    def disconnect(self):
        """Disconnect from the connected websocket server."""
        if self.is_connected:
            self._ws.close()
            self._ws = None

    @tornado.gen.coroutine
    def _run(self):
        """
        Start a loop that listens for all messages received from the websocket
        server and handle them appropriately.
        """
        # TODO(TA):
        # - Add timeouts
        self._logger.info("Connected! Start listening for messages "
                          "received from websocket server.")
        while self.is_connected:
            msg = yield self._ws.read_message()
            msg = json.loads(msg)
            self._logger.debug("Message received: '{}'".format(msg))
            if msg['id'].startswith('redis-pubsub'):
                self._io_loop.add_callback(self._on_update, msg['result'])
            else:
                future = self._pending_requests.get(msg['id'], None)
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
        self._logger.info("Disconnected! Stop listening for messages "
                          "received from websocket server.")

    def _send(self, req):
        future = tornado.gen.Future()
        if self.is_connected:
            self._pending_requests[req.id] = future
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
        """Subscribe to the specified string identifiers in a namespace.

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
                              strategy_and_params):
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
        strategy_and_params : str
            A string with the strategy and its optional parameters specified in
            space-separated form according the KATCP specification e.g.
            '<strat_name> <strat_parm1> <strat_parm2>'
            Examples:
                'event'
                'period 0.5'
                'event-rate 1.0 5.0'

        Returns
        -------
        result: dict
            Dictionary with sensor name as key and result as value
        """
        req = JSONRPCRequest('set_sampling_strategy',
                             [namespace, sensor_name, strategy_and_params])
        result = yield self._send(req)
        raise tornado.gen.Return(result)

    @tornado.gen.coroutine
    def set_sampling_strategies(self, namespace, filters,
                                strategy_and_params):
        """
        Set up a specified sensor strategy for all sensors maching a specified
        set of filters.

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

        Returns
        -------
        result: dict
            Dictionary with matching sensor names as keys and the
            set_sampling_strategy result as value::

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
        req = JSONRPCRequest('set_sampling_strategies',
                             [namespace, filters, strategy_and_params])
        result = yield self._send(req)
        raise tornado.gen.Return(result)
