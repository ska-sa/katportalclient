###############################################################################
# SKA South Africa (http://ska.ac.za/)                                        #
# Author: cam@ska.ac.za                                                       #
# Copyright @ 2013 SKA SA. All rights reserved.                               #
#                                                                             #
# THIS SOFTWARE MAY NOT BE COPIED OR DISTRIBUTED IN ANY FORM WITHOUT THE      #
# WRITTEN PERMISSION OF SKA SA.                                               #
###############################################################################
"""Tests for katportalclient."""


import logging
import StringIO
from functools import partial

import mock
import omnijson as json
from tornado import gen
from tornado import concurrent
from tornado.web import Application
from tornado.httpclient import HTTPResponse, HTTPRequest
from tornado.testing import gen_test
from tornado.test.websocket_test import (
    WebSocketBaseTestCase, TestWebSocketHandler)

from katportalclient import (
    KATPortalClient, JSONRPCRequest, ScheduleBlockNotFoundError)


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

        self.websocket_url = 'ws://localhost:%d/test' % self.get_http_port()

        # Mock the synchronous HTTP client, with our sitemap
        http_sync_client_patcher = mock.patch('tornado.httpclient.HTTPClient')
        self.addCleanup(http_sync_client_patcher.stop)
        self.mock_http_sync_client = http_sync_client_patcher.start()

        def mock_fetch(url):
            sitemap = {'client':
                       {'websocket': self.websocket_url,
                        'historic_sensor_values': r"http://0.0.0.0/history",
                        'schedule_blocks': r"http://0.0.0.0/sb",
                        'sub_nr': '3',
                        }
                       }
            body_buffer = StringIO.StringIO(json.dumps(sitemap))
            return HTTPResponse(HTTPRequest(url), 200, buffer=body_buffer)

        self.mock_http_sync_client().fetch.side_effect = mock_fetch

        # Mock the async HTTP client for other HTTP requests
        http_async_client_patcher = mock.patch('tornado.httpclient.AsyncHTTPClient')
        self.addCleanup(http_async_client_patcher.stop)
        self.mock_http_async_client = http_async_client_patcher.start()

        def on_update_callback(msg, self):
            self.logger.info("Client got update message: '{}'".format(msg))
            self.on_update_callback_call_count += 1

        self.on_update_callback_call_count = 0
        on_msg_callback = partial(on_update_callback, self=self)
        self._portal_client = KATPortalClient(
            'http://dummy.for.sitemap/api/client/3',
            on_msg_callback,
            io_loop=self.io_loop)

    def tearDown(self):
        yield self.close(self._portal_client)
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
        self.assertIsNotNone(self._portal_client)
        yield self._portal_client.connect()
        self.assertTrue(self._portal_client.is_connected)

    @gen_test
    def test_disconnect(self):
        self.assertIsNotNone(self._portal_client)
        yield self._portal_client.connect()
        self.assertTrue(self._portal_client.is_connected)
        self._portal_client.disconnect()
        self.assertFalse(self._portal_client.is_connected)

    @gen_test
    def test_add(self):
        yield self._portal_client.connect()
        result = yield self._portal_client.add(8, 67)
        self.assertEqual(result, 8+67)

    @gen_test
    def test_add_when_not_connected(self):
        with self.assertRaises(Exception):
            yield self._portal_client.add(8, 67)

    @gen_test
    def test_subscribe(self):
        yield self._portal_client.connect()
        result = yield self._portal_client.subscribe('planets', ['jupiter', 'm*'])
        self.assertEqual(result, 2)

    @gen_test
    def test_unsubscribe(self):
        yield self._portal_client.connect()
        result = yield self._portal_client.unsubscribe(
            'alpha', ['a*', 'b*', 'c*', 'd', 'e'])
        self.assertEqual(result, 5)

    @gen_test
    def test_set_sampling_strategy(self):
        yield self._portal_client.connect()
        result = yield self._portal_client.set_sampling_strategy(
            'ants', 'mode', 'period 1')
        self.assertTrue(isinstance(result, dict))
        self.assertTrue('mode' in result.keys())

    @gen_test
    def test_set_sampling_strategies(self):
        yield self._portal_client.connect()
        result = yield self._portal_client.set_sampling_strategies(
            'ants', ['mode', 'sensors_ok', 'ap_connected'], 'event-rate 1 5')
        self.assertTrue(isinstance(result, dict))
        self.assertTrue('mode' in result.keys())

    @gen_test
    def test_on_update_callback(self):
        yield self._portal_client.connect()
        # Fake a redis publish update to make sure the callback is invoked
        req = JSONRPCRequest('pubsub-test', [])
        self._portal_client._ws.write_message(req())
        yield gen.sleep(0.2)  # Give pubsub message chance to be received
        self.assertEqual(self.on_update_callback_call_count, 1)

    @gen_test
    def test_init_with_websocket_url(self):
        """Test backwards compatibility initialising directly with a websocket URL."""
        test_client = KATPortalClient(self.websocket_url, None)
        yield test_client.connect()
        self.assertTrue(test_client.is_connected)

    @gen_test
    def test_sitemap_includes_expected_endpoints(self):
        sitemap = self._portal_client._sitemap
        self.assertTrue(sitemap['websocket'].startswith('ws://'))
        self.assertTrue(sitemap['historic_sensor_values'].startswith('http://'))
        self.assertTrue(sitemap['schedule_blocks'].startswith('http://'))
        self.assertTrue(sitemap['sub_nr'] == '3')

    @gen_test
    def test_schedule_blocks_assigned_list_valid(self):
        """Test schedule block IDs are correctly extracted from JSON text."""
        def mock_fetch(url):
            body_buffer = StringIO.StringIO(
                r"""{"result":
                        "[{\"id_code\":\"20160908-0004\",\"owner\":\"CAM\",\"type\":\"OBSERVATION\",\"sub_nr\":1},
                          {\"id_code\":\"20160908-0005\",\"owner\":\"CAM\",\"type\":\"OBSERVATION\",\"sub_nr\":3},
                          {\"id_code\":\"20160908-0006\",\"owner\":\"CAM\",\"type\":\"OBSERVATION\",\"sub_nr\":2},
                          {\"id_code\":\"20160908-0007\",\"owner\":\"CAM\",\"type\":\"OBSERVATION\",\"sub_nr\":4},
                          {\"id_code\":\"20160908-0008\",\"owner\":\"CAM\",\"type\":\"OBSERVATION\",\"sub_nr\":3}
                         ]"
                    }""")
            result = HTTPResponse(HTTPRequest(url), 200, buffer=body_buffer)
            future = concurrent.Future()
            future.set_result(result)
            return future

        self.mock_http_async_client().fetch.side_effect = mock_fetch

        sb_ids = yield self._portal_client.schedule_blocks_assigned()

        # Verify that only the 2 schedule blocks for sub array 3 are returned
        self.assertTrue(len(sb_ids) == 2, "Expect exactly 2 schedule block IDs")
        self.assertIn('20160908-0005', sb_ids)
        self.assertIn('20160908-0008', sb_ids)

    @gen_test
    def test_schedule_block_detail(self):
        """Test schedule block detail is correctly extracted from JSON text."""
        def mock_fetch(url):
            if url.endswith("20160908-0005"):
                body_buffer = StringIO.StringIO(
                    r"""{"result":
                            {"id_code":"20160908-0005",
                             "owner":"CAM",
                             "actual_end_time":null,
                             "id":5,
                             "scheduled_time":"2016-09-08 09:18:53.000Z",
                             "priority":"LOW",
                             "state":"SCHEDULED",
                             "config_label":"",
                             "type":"OBSERVATION",
                             "expected_duration_seconds":89,
                             "description":"a test schedule block",
                             "sub_nr":3,
                             "desired_start_time":null,
                             "actual_start_time":null,
                             "resource_alloc":null
                            }
                        }""")
            else:
                body_buffer = StringIO.StringIO("""{"result":null}""")

            result = HTTPResponse(HTTPRequest(url), 200, buffer=body_buffer)
            future = concurrent.Future()
            future.set_result(result)
            return future

        self.mock_http_async_client().fetch.side_effect = mock_fetch

        with self.assertRaises(ScheduleBlockNotFoundError):
            yield self._portal_client.schedule_block_detail("20160908-bad")

        sb_valid = yield self._portal_client.schedule_block_detail("20160908-0005")
        self.assertTrue(sb_valid['id_code'] == "20160908-0005")
        self.assertTrue(sb_valid['sub_nr'] == 3)
        self.assertIn('description', sb_valid)
        self.assertIn('desired_start_time', sb_valid)
        self.assertIn('scheduled_time', sb_valid)
        self.assertIn('actual_start_time', sb_valid)
        self.assertIn('actual_end_time', sb_valid)
        self.assertIn('expected_duration_seconds', sb_valid)
        self.assertIn('state', sb_valid)
