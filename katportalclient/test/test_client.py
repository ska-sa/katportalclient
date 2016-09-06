###############################################################################
# SKA South Africa (http://ska.ac.za/)                                        #
# Author: cam@ska.ac.za                                                       #
# Copyright @ 2013 SKA SA. All rights reserved.                               #
#                                                                             #
# THIS SOFTWARE MAY NOT BE COPIED OR DISTRIBUTED IN ANY FORM WITHOUT THE      #
# WRITTEN PERMISSION OF SKA SA.                                               #
###############################################################################
"""Tests for katwebsocket of katportal."""


import logging
from functools import partial

import omnijson as json
from tornado import gen
from tornado.web import Application
from tornado.testing import gen_test
from tornado.test.websocket_test import (
    WebSocketBaseTestCase, TestWebSocketHandler)

from katportalclient import KATPortalClient, JSONRPCRequest


LOGGER_NAME = 'test_portalclient'


class TestWebSocket(TestWebSocketHandler):
    """Web socket test server."""

    def open(self):
        print("WebSocket opened")

    def on_message(self, message):
        """Fake the typical replies depending on the type of method called."""

        reply = {}
        message = json.loads(message)
        reply['id'] = message['id']
        if message['method'] == 'pubsub-test':
            reply['id'] = 'redis-pubsub'
            reply['result'] = {'value': 'blahdieblah'}
        elif message['method'] == 'add':
            x, y = message['params']
            reply['result'] = x + y
        elif message['method'] in ('subscribe', 'unsubscribe'):
            reply['result'] = len(message['params'][1])
        elif message['method'] in ('set_sampling_strategy',
                                   'set_sampling_strategies'):

            reply['result'] = {}
            filters = message['params'][1]
            if not isinstance(filters, list):
                filters = [filters]
            reply['result'][filters[0]] = {
                'success': True,
                'info': message['params'][2]
            }
        else:
            reply['result'] = 'unknown'
        self.write_message(json.dumps(reply))

    def on_close(self):
        print("WebSocket closed")


class TestKATPortalClient(WebSocketBaseTestCase):

    def setUp(self):
        super(TestKATPortalClient, self).setUp()

        def on_update_callback(msg, self):
            self.logger.info("Client got update message: '{}'".format(msg))
            self.on_update_callback_call_count += 1

        self.on_update_callback_call_count = 0
        on_msg_callback = partial(on_update_callback, self=self)
        self._ws_client = KATPortalClient(
            'ws://localhost:%d/test' % self.get_http_port(),
            on_msg_callback,
            io_loop=self.io_loop)

    def tearDown(self):
        yield self.close(self._ws_client)
        super(TestKATPortalClient, self).tearDown()

    def get_app(self):
        # Create application object with handlers
        self.logger = logging.getLogger(LOGGER_NAME)
        self.logger.setLevel(logging.INFO)
        self.close_future = gen.Future()
        self.application = Application([
            ('/test', TestWebSocket, dict(close_future=self.close_future)),
        ])
        self.application.logger = self.logger
        return self.application

    @gen_test
    def test_connect(self):
        self.assertIsNotNone(self._ws_client)
        yield self._ws_client.connect()
        self.assertTrue(self._ws_client.is_connected)

    @gen_test
    def test_disconnect(self):
        self.assertIsNotNone(self._ws_client)
        yield self._ws_client.connect()
        self.assertTrue(self._ws_client.is_connected)
        self._ws_client.disconnect()
        self.assertFalse(self._ws_client.is_connected)

    @gen_test
    def test_add(self):
        yield self._ws_client.connect()
        result = yield self._ws_client.add(8, 67)
        self.assertEqual(result, 8+67)

    @gen_test
    def test_add_when_not_connected(self):
        with self.assertRaises(Exception):
            yield self._ws_client.add(8, 67)

    @gen_test
    def test_subscribe(self):
        yield self._ws_client.connect()
        result = yield self._ws_client.subscribe('planets', ['jupiter', 'm*'])
        self.assertEqual(result, 2)

    @gen_test
    def test_unsubscribe(self):
        yield self._ws_client.connect()
        result = yield self._ws_client.unsubscribe(
            'alpha', ['a*', 'b*', 'c*', 'd', 'e'])
        self.assertEqual(result, 5)

    @gen_test
    def test_set_sampling_strategy(self):
        yield self._ws_client.connect()
        result = yield self._ws_client.set_sampling_strategy(
            'ants', 'mode', 'period 1')
        self.assertTrue(isinstance(result, dict))
        self.assertTrue('mode' in result.keys())

    @gen_test
    def test_set_sampling_strategies(self):
        yield self._ws_client.connect()
        result = yield self._ws_client.set_sampling_strategies(
            'ants', ['mode', 'sensors_ok', 'ap_connected'], 'event-rate 1 5')
        self.assertTrue(isinstance(result, dict))
        self.assertTrue('mode' in result.keys())

    @gen_test
    def test_on_update_callback(self):
        yield self._ws_client.connect()
        # Fake a redis publish update to make sure the callback is invoked
        req = JSONRPCRequest('pubsub-test', [])
        self._ws_client._ws.write_message(req())
        yield gen.sleep(0.2)  # Give pubsub message chance to be received
        self.assertEqual(self.on_update_callback_call_count, 1)
