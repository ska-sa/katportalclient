# Copyright 2015 SKA South Africa (http://ska.ac.za/)
# BSD license - see COPYING for details
"""Tests for katportalclient."""
from __future__ import print_function

from future import standard_library
standard_library.install_aliases()  # noqa: E402
import logging
import io
import time
from urllib.parse import quote_plus

import mock
import omnijson as json

from builtins import bytes, zip
from functools import partial
from past.builtins import basestring

from tornado import concurrent, gen
from tornado.httpclient import HTTPResponse, HTTPRequest
from tornado.test.websocket_test import WebSocketBaseTestCase, TestWebSocketHandler
from tornado.testing import gen_test
from tornado.web import Application

from katportalclient import (
    KATPortalClient, JSONRPCRequest, ScheduleBlockNotFoundError, InvalidResponseError,
    SensorNotFoundError, SensorLookupError, SensorHistoryRequestError,
    ScheduleBlockTargetsParsingError, create_jwt_login_token, SensorSample,
    SensorSampleValueTime)


LOGGER_NAME = 'test_portalclient'
NEW_WEBSOCKET_DELAY = 0.05
SITEMAP_URL = 'http://dummy.for.sitemap/api/client/3'


# Example JSON text for sensor request responses
sensor_json = {
    "anc_weather_wind_speed": """{"name":"anc_weather_wind_speed",
                                  "component": "anc",
                                  "attributes": {"description":"Wind speed",
                                   "systype":"mkat",
                                   "site":"deva",
                                   "original_name":"anc.weather.wind-speed",
                                   "params":"[0.0, 70.0]",
                                   "units":"m\/s",
                                   "type":"float"}}""",

    "anc_mean_wind_speed": """{ "name" : "anc_mean_wind_speed",
                                "component": "anc",
                                "attributes": {"description":"Mean wind speed",
                                 "systype":"mkat",
                                 "site":"deva",
                                 "original_name":"anc.mean-wind-speed",
                                 "params":"[0.0, 70.0]",
                                 "units":"m\/s",
                                 "type":"float"}}""",

    "anc_gust_wind_speed": """{"name" :"anc_gust_wind_speed",
                                     "component": "anc",
                               "attributes":{"description":"Gust wind speed",
                                "systype":"mkat",
                                "site":"deva",
                                "original_name":"anc.gust-wind-speed",
                                "params":"[0.0, 70.0]",
                                "units":"m\/s",
                                "type":"float"}}""",

    "anc_gust_wind_speed2": """{"name" :"anc_gust_wind_speed2",
                                     "component": "anc",
                               "attributes":{"description":"Gust wind speed2",
                                "systype":"mkat",
                                "site":"deva",
                                "original_name":"anc.gust-wind-speed2",
                                "params":"[0.0, 72.0]",
                                "units":"m\/s",
                                "type":"float"}}""",

    "anc_wind_device_status": """{"name" :"anc_wind_device_status",
                                     "component": "anc",
                                  "attributes":{"description":"Overall status of wind system",
                                   "systype":"mkat",
                                   "site":"deva",
                                   "original_name":"anc.wind.device-status",
                                   "params":"['ok', 'degraded', 'fail']",
                                   "units":"",
                                   "type":"discrete"}}""",

    "anc_weather_device_status": """{"name" :"anc_weather_device_status",
                                     "component": "anc",
                                     "attributes":{"description":"Overall status of weather system",
                                      "systype":"mkat",
                                       "site":"deva",
                                       "original_name":"anc.weather.device-status",
                                       "params":"['ok', 'degraded', 'fail']",
                                       "units":"",
                                       "type":"discrete"}}""",

    "regex_error": """{"error":"invalid regular expression: quantifier operand invalid\n"}""",

    "invalid_response": """{"error":"prepared invalid response"}"""
}


sensor_data1 = """{
  "url": "/katstore/api/query/?start_time=1523249984&end_time=now&interval=0&sensor=anc_mean_wind_speed&minmax=false&buffer_only=false&additional_fields=false",
  "sensor_name": "anc_mean_wind_speed",
  "title": "Sensors Query",
  "data": [
    {
      "value": 91474,
      "sample_time": 1523249992.0250809193,
      "status" : "error"
    },
    {
      "value": 91475,
      "sample_time": 1523250002.0252408981,
      "status" : "error"
    },
    {
      "value": 91476,
      "sample_time": 1523250012.0289709568,
      "status" : "error"
    },
    {
      "value": 91477,
      "sample_time": 1523250022.0292000771,
      "status" : "error"
    }
  ]
}"""

sensor_data2 = """{
  "url": "/katstore/api/query/?start_time=1523249984&end_time=now&interval=0&sensor=anc_gust_wind_speed&minmax=false&buffer_only=false&additional_fields=false",
  "sensor_name": "anc_gust_wind_speed",
  "title": "Sensors Query",
  "data": [
    {
      "value": 91475,
      "sample_time": 1523250002.0252408981,
      "status" : "error"
    },
    {
      "value": 91476,
      "sample_time": 1523250012.0289709568,
      "status" : "error"
    },
    {
      "value": 91477,
      "sample_time": 1523250022.0292000771,
      "status" : "error"
    }
  ]
}"""

sensor_data3 = """{
  "url": "/katstore/api/query/?start_time=1523249984&end_time=now&interval=0&sensor=sys_watchdogs_sys&minmax=false&buffer_only=false&additional_fields=false",
  "sensor_name": "sys_watchdogs_sys",
  "title": "Sensors Query",
  "data": [
    {
      "value": 91474,
      "sample_time": 1523249992.0250809193,
      "value_time": 1523249991.0250809193,
      "status" : "error"
    },
    {
      "value": 91475,
      "sample_time": 1523250002.0252408981,
      "value_time": 1523249991.0250809193,
      "status" : "error"
    },
    {
      "value": 91477,
      "sample_time": 1523250022.0292000771,
      "value_time": 1523249991.0250809193,
      "status" : "error"
    }
  ]
}"""

sensor_data4 = """{
  "url": "/katstore/api/query/?start_time=1523249984&end_time=now&interval=0&sensor=anc_mean_wind_speed&minmax=false&buffer_only=false&additional_fields=false",
  "sensor_name": "anc_mean_wind_speed",
  "title": "Sensors Query",
  "data": [
    {
      "value": "91474",
      "sample_time": 1523249992.0250809193,
      "value_time": 1523249991.0250809193,
      "status" : "error"
    },
    {
      "value": "91475",
      "sample_time": 1523250002.0252408981,
      "value_time": 1523249991.0250809193,
      "status" : "error"
    },
    {
      "value": "91477",
      "sample_time": 1523250022.0292000771,
      "value_time": 1523249991.0250809193,
      "status" : "error"
    },
    {
      "value": "91477",
      "sample_time": 1523250021.0292000771,
      "value_time": 1523249990.0250809193,
      "status" : "error"
    }
  ]
}"""

sensor_data_fail = """{
  "url": "/katstore/api/query/?start_time=1523249984&end_time=now&interval=0&sensor=anc_mean_wind_speed&minmax=false&buffer_only=false&additional_fields=false",
  "sensor_name": "anc_mean_wind_speed",
  "title": "Sensors Query",
  "data": []
}"""

# Keep a reference to the last test websocket handler instantiated, so that it
# can be used in tests that require injecting data from the server side.
# (yes, it is hacky)
test_websocket = None


class TestWebSocket(TestWebSocketHandler):
    """Web socket test server."""

    def open(self):
        global test_websocket
        test_websocket = self
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
        global test_websocket
        test_websocket = None
        print("WebSocket closed")


class TestKATPortalClient(WebSocketBaseTestCase):

    def setUp(self):
        super(TestKATPortalClient, self).setUp()

        self.websocket_url = 'ws://localhost:%d/test' % self.get_http_port()

        # Mock the asynchronous HTTP client, with our sitemap
        http_sync_client_patcher = mock.patch('tornado.httpclient.HTTPClient')
        self.addCleanup(http_sync_client_patcher.stop)
        self.mock_http_sync_client = http_sync_client_patcher.start()

        def mock_fetch(url):
            sitemap = {'client':
                       {'websocket': self.websocket_url,
                        'historic_sensor_values': r"http://0.0.0.0/katstore",
                        'schedule_blocks': r"http://0.0.0.0/sb",
                        'subarray_sensor_values': r"http://0.0.0.0/sensor-list",
                        'target_descriptions': r"http://0.0.0.0/sources",
                        'sub_nr': '3',
                        'authorization': r"http://0.0.0.0/katauth",
                        'userlogs': r"http://0.0.0.0/katcontrol/userlogs",
                        'subarray': r"http:/0.0.0.0/katcontrol/subarray",
                        'monitor': r"http:/0.0.0.0/katmonitor",
                        }
                       }
            body_buffer = StringIO.StringIO(json.dumps(sitemap))
            return HTTPResponse(HTTPRequest(url), 200, buffer=body_buffer)

        self.mock_http_sync_client().fetch.side_effect = mock_fetch

        # Mock the async HTTP client for other HTTP requests
        http_async_client_patcher = mock.patch(
            'tornado.httpclient.AsyncHTTPClient')
        self.addCleanup(http_async_client_patcher.stop)
        self.mock_http_async_client = http_async_client_patcher.start()
        # Set up a fetcher that just knows about the sitemap
        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetcher('')

        def on_update_callback(msg, self):
            self.logger.info("Client got update message: '{}'".format(msg))
            self.on_update_callback_call_count += 1

        self.on_update_callback_call_count = 0
        on_msg_callback = partial(on_update_callback, self=self)
        self._portal_client = KATPortalClient(
            SITEMAP_URL,
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
        self.assertTrue(self._portal_client._heart_beat_timer.is_running())
        self.assertFalse(self._portal_client._disconnect_issued)

    @gen_test
    def test_reconnect(self):
        self.assertIsNotNone(self._portal_client)
        yield self._portal_client.connect()
        self.assertTrue(self._portal_client.is_connected)
        self.assertTrue(self._portal_client._heart_beat_timer.is_running())
        connect_future = gen.Future()
        self._portal_client._connect = mock.MagicMock(
            return_value=connect_future)
        connect_future.set_result(None)
        yield test_websocket.close()
        yield gen.sleep(NEW_WEBSOCKET_DELAY)  # give ioloop time to open new websocket
        self._portal_client._connect.assert_called_with(reconnecting=True)

    @gen_test
    def test_resend_subscriptions_and_strategies_after_reconnect(self):
        self.assertIsNotNone(self._portal_client)
        yield self._portal_client.connect()
        self.assertTrue(self._portal_client.is_connected)
        self.assertTrue(self._portal_client._heart_beat_timer.is_running())
        resend_future = gen.Future()
        self._portal_client._resend_subscriptions_and_strategies = mock.MagicMock(
            return_value=resend_future)
        resend_future.set_result(None)
        yield test_websocket.close()
        yield gen.sleep(NEW_WEBSOCKET_DELAY)  # give ioloop time to open new websocket
        self._portal_client._resend_subscriptions_and_strategies.assert_called_once()

        # test another reconnect if resending the strategies did not work on a
        # reconnect
        resend_future2 = gen.Future()
        resend_future2.set_result(None)
        self._portal_client._resend_subscriptions_and_strategies = mock.MagicMock(
            return_value=resend_future2)
        self._portal_client._resend_subscriptions_and_strategies.side_effect = Exception(
            'some exception was thrown while _resend_subscriptions_and_strategies')
        self._portal_client._connect_later = mock.MagicMock()
        yield test_websocket.close()
        yield gen.sleep(NEW_WEBSOCKET_DELAY)  # give ioloop time to open new websocket
        self._portal_client._connect_later.assert_called_once()

    @gen_test
    def test_server_redis_reconnect_message(self):
        self.assertIsNotNone(self._portal_client)
        yield self._portal_client.connect()
        self.assertTrue(self._portal_client.is_connected)
        self.assertTrue(self._portal_client._heart_beat_timer.is_running())
        resend_future = gen.Future()
        self._portal_client._resend_subscriptions = mock.MagicMock(
            return_value=resend_future)
        self._portal_client._websocket_message('{"id": "redis-reconnect"}')
        resend_future.set_result(None)
        self._portal_client._resend_subscriptions.assert_called_once()

    @gen_test
    def test_resend_subscriptions(self):
        self.assertIsNotNone(self._portal_client)
        yield self._portal_client.connect()
        self.assertTrue(self._portal_client.is_connected)
        self.assertTrue(self._portal_client._heart_beat_timer.is_running())
        send_future = gen.Future()
        send_future.set_result('Test _send success')
        self._portal_client._send = mock.MagicMock(
            return_value=send_future)
        self._portal_client._ws_jsonrpc_cache = [
            JSONRPCRequest(method='subscribe', params='test params1'),
            JSONRPCRequest(method='subscribe', params='test params2'),
            JSONRPCRequest(method='not_subscribe', params='test params3'),
            JSONRPCRequest(method='unsubscribe', params='test params4'),
            JSONRPCRequest(method='subscribe', params='test params5'),
            JSONRPCRequest(method='subscribe', params='test params6')]
        yield self._portal_client._resend_subscriptions()
        # only subscribes must be resent!
        self.assertEquals(self._portal_client._send.call_count, 4)

    @gen_test
    def test_resend_subscriptions_and_strategies(self):
        self.assertIsNotNone(self._portal_client)
        yield self._portal_client.connect()
        self.assertTrue(self._portal_client.is_connected)
        self.assertTrue(self._portal_client._heart_beat_timer.is_running())
        send_future = gen.Future()
        send_future.set_result('Test _send success')
        self._portal_client._send = mock.MagicMock(
            return_value=send_future)
        self._portal_client._ws_jsonrpc_cache = [
            JSONRPCRequest(method='subscribe', params='test params1'),
            JSONRPCRequest(method='subscribe', params='test params2'),
            JSONRPCRequest(method='not_subscribe', params='test params3'),
            JSONRPCRequest(method='unsubscribe', params='test params4'),
            JSONRPCRequest(method='set_sampling_strategy',
                           params='test params5'),
            JSONRPCRequest(method='set_sampling_strategies', params='test params6')]
        yield self._portal_client._resend_subscriptions_and_strategies()
        self.assertEquals(self._portal_client._send.call_count, 6)

    @gen_test
    def test_disconnect(self):
        self.assertIsNotNone(self._portal_client)
        yield self._portal_client.connect()
        self.assertTrue(self._portal_client.is_connected)
        self._portal_client.disconnect()
        self.assertFalse(self._portal_client.is_connected)
        self.assertFalse(self._portal_client._heart_beat_timer.is_running())
        self.assertEquals(self._portal_client._ws_jsonrpc_cache, [])
        self.assertTrue(self._portal_client._disconnect_issued)

    @gen_test
    def test_add(self):
        yield self._portal_client.connect()
        result = yield self._portal_client.add(8, 67)
        self.assertEqual(result, 8 + 67)

    @gen_test
    def test_add_when_not_connected(self):
        with self.assertRaises(Exception):
            yield self._portal_client.add(8, 67)

    @gen_test
    def test_cache_jsonrpc_request(self):
        req1 = JSONRPCRequest('test1', 'test_params1')
        req2 = JSONRPCRequest('test2', ['test_params2', 'test_params2'])
        req3 = JSONRPCRequest('subscribe', ['namespace', 'sub_strings'])
        req4 = JSONRPCRequest('unsubscribe', ['namespace', 'sub_strings'])
        req5 = JSONRPCRequest('set_sampling_strategy',
                              ['namespace', 'sensor_name', 'strategy_and_params'])
        req6 = JSONRPCRequest('set_sampling_strategy',
                              ['namespace', 'sensor_name', 'none'])
        req7 = JSONRPCRequest('set_sampling_strategies',
                              ['namespace', 'sensor_name', 'strategy_and_params'])
        req8 = JSONRPCRequest('set_sampling_strategies',
                              ['namespace', 'sensor_name', 'none'])
        self._portal_client._cache_jsonrpc_request(req1)
        self.assertEquals(len(self._portal_client._ws_jsonrpc_cache), 1)
        self.assertEquals(self._portal_client._ws_jsonrpc_cache[0].id, req1.id)
        self._portal_client._cache_jsonrpc_request(req2)
        self.assertEquals(len(self._portal_client._ws_jsonrpc_cache), 2)
        self.assertEquals(self._portal_client._ws_jsonrpc_cache[0].id, req1.id)
        self.assertEquals(self._portal_client._ws_jsonrpc_cache[1].id, req2.id)
        # test no duplicates are added
        self._portal_client._cache_jsonrpc_request(req1)
        self.assertEquals(len(self._portal_client._ws_jsonrpc_cache), 2)
        self.assertEquals(self._portal_client._ws_jsonrpc_cache[0].id, req1.id)
        self.assertEquals(self._portal_client._ws_jsonrpc_cache[1].id, req2.id)
        # test subscriptions are added
        self._portal_client._cache_jsonrpc_request(req3)
        self.assertEquals(len(self._portal_client._ws_jsonrpc_cache), 3)
        self.assertEquals(self._portal_client._ws_jsonrpc_cache[0].id, req1.id)
        self.assertEquals(self._portal_client._ws_jsonrpc_cache[1].id, req2.id)
        self.assertEquals(self._portal_client._ws_jsonrpc_cache[2].id, req3.id)
        # test no duplicate subscriptions are added
        self._portal_client._cache_jsonrpc_request(req3)
        self.assertEquals(len(self._portal_client._ws_jsonrpc_cache), 3)
        self.assertEquals(self._portal_client._ws_jsonrpc_cache[0].id, req1.id)
        self.assertEquals(self._portal_client._ws_jsonrpc_cache[1].id, req2.id)
        self.assertEquals(self._portal_client._ws_jsonrpc_cache[2].id, req3.id)
        # test that an unsubscribe removes a subscribe message
        self._portal_client._cache_jsonrpc_request(req4)
        self.assertEquals(len(self._portal_client._ws_jsonrpc_cache), 2)
        self.assertEquals(self._portal_client._ws_jsonrpc_cache[0].id, req1.id)
        self.assertEquals(self._portal_client._ws_jsonrpc_cache[1].id, req2.id)
        # test set_sampling_strategy and set_sampling_strategies are added
        self._portal_client._cache_jsonrpc_request(req5)
        self._portal_client._cache_jsonrpc_request(req7)
        self.assertEquals(len(self._portal_client._ws_jsonrpc_cache), 4)
        self.assertEquals(self._portal_client._ws_jsonrpc_cache[2].id, req5.id)
        self.assertEquals(self._portal_client._ws_jsonrpc_cache[3].id, req7.id)
        # test set_sampling_strategy and set_sampling_strategies are not
        # duplicated
        self._portal_client._cache_jsonrpc_request(req5)
        self._portal_client._cache_jsonrpc_request(req7)
        self.assertEquals(len(self._portal_client._ws_jsonrpc_cache), 4)
        self.assertEquals(self._portal_client._ws_jsonrpc_cache[2].id, req5.id)
        self.assertEquals(self._portal_client._ws_jsonrpc_cache[3].id, req7.id)
        # test that set_sampling_strategy and set_sampling_strategies are removed
        # when a strategy of none is given
        self._portal_client._cache_jsonrpc_request(req6)
        self._portal_client._cache_jsonrpc_request(req8)
        self.assertEquals(len(self._portal_client._ws_jsonrpc_cache), 2)
        self.assertEquals(self._portal_client._ws_jsonrpc_cache[0].id, req1.id)
        self.assertEquals(self._portal_client._ws_jsonrpc_cache[1].id, req2.id)
        # test cache is cleared on a disconnect
        self._portal_client.disconnect()
        self.assertEquals(len(self._portal_client._ws_jsonrpc_cache), 0)

    @gen_test
    def test_subscribe(self):
        self._portal_client._cache_jsonrpc_request = mock.MagicMock()
        yield self._portal_client.connect()
        result = yield self._portal_client.subscribe('planets', ['jupiter', 'm*'])
        self.assertEqual(result, 2)
        self._portal_client._cache_jsonrpc_request.assert_called_once()

    @gen_test
    def test_unsubscribe(self):
        self._portal_client._cache_jsonrpc_request = mock.MagicMock()
        yield self._portal_client.connect()
        result = yield self._portal_client.unsubscribe(
            'alpha', ['a*', 'b*', 'c*', 'd', 'e'])
        self.assertEqual(result, 5)
        self._portal_client._cache_jsonrpc_request.assert_called_once()

    @gen_test
    def test_set_sampling_strategy(self):
        self._portal_client._cache_jsonrpc_request = mock.MagicMock()
        yield self._portal_client.connect()
        result = yield self._portal_client.set_sampling_strategy(
            'ants', 'mode', 'period 1')
        self.assertTrue(isinstance(result, dict))
        self.assertTrue('mode' in list(result.keys()))
        self._portal_client._cache_jsonrpc_request.assert_called_once()

    @gen_test
    def test_set_sampling_strategies(self):
        self._portal_client._cache_jsonrpc_request = mock.MagicMock()
        yield self._portal_client.connect()
        result = yield self._portal_client.set_sampling_strategies(
            'ants', ['mode', 'sensors_ok', 'ap_connected'], 'event-rate 1 5')
        self.assertTrue(isinstance(result, dict))
        self.assertTrue('mode' in list(result.keys()))
        self._portal_client._cache_jsonrpc_request.assert_called_once()

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
        sitemap = self._portal_client.sitemap
        self.assertTrue(sitemap['websocket'].startswith('ws://'))
        self.assertTrue(
            sitemap['historic_sensor_values'].startswith('http://'))
        self.assertTrue(sitemap['schedule_blocks'].startswith('http://'))
        self.assertTrue(sitemap['capture_blocks'].startswith('http://'))
        self.assertTrue(sitemap['sub_nr'] == '3')

    @gen_test
    def test_schedule_blocks_assigned_list_valid(self):
        """Test schedule block IDs are correctly extracted from JSON text."""
        schedule_block_base_url = self._portal_client.sitemap[
            'schedule_blocks']

        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetcher(
            valid_response=r"""
                {"result":
                    "[{\"id_code\":\"20160908-0004\",\"owner\":\"CAM\",\"type\":\"OBSERVATION\",\"sub_nr\":1},
                      {\"id_code\":\"20160908-0005\",\"owner\":\"CAM\",\"type\":\"OBSERVATION\",\"sub_nr\":3},
                      {\"id_code\":\"20160908-0006\",\"owner\":\"CAM\",\"type\":\"OBSERVATION\",\"sub_nr\":2},
                      {\"id_code\":\"20160908-0007\",\"owner\":\"CAM\",\"type\":\"OBSERVATION\",\"sub_nr\":4},
                      {\"id_code\":\"20160908-0008\",\"owner\":\"CAM\",\"type\":\"OBSERVATION\",\"sub_nr\":3}
                     ]"
                }""",
            invalid_response="""{"result":null}""",
            starts_with=schedule_block_base_url)

        sb_ids = yield self._portal_client.schedule_blocks_assigned()

        # Verify that only the 2 schedule blocks for subarray 3 are returned
        self.assertTrue(len(sb_ids) == 2,
                        "Expect exactly 2 schedule block IDs")
        self.assertIn('20160908-0005', sb_ids)
        self.assertIn('20160908-0008', sb_ids)

    @gen_test
    def test_schedule_blocks_assigned_list_empty(self):
        """Test with no schedule block IDs on a subarray."""
        schedule_block_base_url = self._portal_client.sitemap[
            'schedule_blocks']

        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetcher(
            valid_response=r"""
                {"result":
                    "[{\"id_code\":\"20160908-0004\",\"owner\":\"CAM\",\"type\":\"OBSERVATION\",\"sub_nr\":1},
                      {\"id_code\":\"20160908-0005\",\"owner\":\"CAM\",\"type\":\"OBSERVATION\",\"sub_nr\":2}
                     ]"
                }""",
            invalid_response="""{"result":null}""",
            starts_with=schedule_block_base_url)

        sb_ids = yield self._portal_client.schedule_blocks_assigned()

        # Verify that there are no schedule blocks (since tests work on
        # subarray 3)
        self.assertTrue(len(sb_ids) == 0, "Expect no schedule block IDs")

    @gen_test
    def test_schedule_block_detail(self):
        """Test schedule block detail is correctly extracted from JSON text."""
        schedule_block_base_url = self._portal_client.sitemap[
            'schedule_blocks']
        schedule_block_id = "20160908-0005"

        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetcher(
            valid_response=r"""
                {"result":
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
                }""",
            invalid_response="""{"result":null}""",
            starts_with=schedule_block_base_url,
            contains=schedule_block_id)

        with self.assertRaises(ScheduleBlockNotFoundError):
            yield self._portal_client.schedule_block_detail("20160908-bad")

        sb_valid = yield self._portal_client.schedule_block_detail(schedule_block_id)
        self.assertTrue(sb_valid['id_code'] == schedule_block_id)
        self.assertTrue(sb_valid['sub_nr'] == 3)
        self.assertIn('description', sb_valid)
        self.assertIn('desired_start_time', sb_valid)
        self.assertIn('scheduled_time', sb_valid)
        self.assertIn('actual_start_time', sb_valid)
        self.assertIn('actual_end_time', sb_valid)
        self.assertIn('expected_duration_seconds', sb_valid)
        self.assertIn('state', sb_valid)

    @gen_test
    def test_sb_ids_by_capture_block_valid(self):
        """Test SB IDs are extracted for valid capture block ID."""
        capture_block_base_url = self._portal_client.sitemap[
            'capture_blocks']
        capture_block_id = "1556092846"

        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetcher(
            valid_response=r"""
                {"result":["20190424-0009", "20190424-0010"]}""",
            invalid_response=r"""{"result":null}""",
            starts_with=capture_block_base_url)
        sb_ids = yield self._portal_client.sb_ids_by_capture_block(capture_block_id)
        # Verify that sb_id has been returned to the list
        self.assertTrue(len(sb_ids) == 2,
                        "Expect exactly 2 schedule block IDs")
        self.assertIn('20190424-0009', sb_ids)
        self.assertIn('20190424-0010', sb_ids)

    @gen_test
    def test_sb_ids_by_capture_block_empty(self):
        """Test no SB IDs are extracted for unused capture block ID."""
        capture_block_base_url = self._portal_client.sitemap[
            'capture_blocks']
        capture_block_id = "123456"

        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetcher(
            valid_response=r"""{"result":[]}""",
            invalid_response=r"""{"result":null}""",
            starts_with=capture_block_base_url)
        sb_ids = yield self._portal_client.sb_ids_by_capture_block(capture_block_id)
        # Verify that empty list returned
        self.assertTrue(len(sb_ids) == 0,
                        "Expect no schedule block IDs")

    @gen_test
    def test_sensor_names_single_sensor_valid(self):
        """Test single sensor name is correctly extracted from JSON text."""
        history_base_url = self._portal_client.sitemap[
            'historic_sensor_values']
        sensor_name_filter = 'anc_weather_wind_speed'

        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetcher(
            valid_response=('{"data": [%s]}' % sensor_json['anc_weather_wind_speed']),
            invalid_response='[]',
            starts_with=history_base_url,
            contains=sensor_name_filter)

        sensors = yield self._portal_client.sensor_names(sensor_name_filter)

        self.assertTrue(len(sensors) == 1, "Expect exactly 1 sensor")
        self.assertTrue(sensors[0] == sensor_name_filter)

    @gen_test
    def test_sensor_names_multiple_sensors_valid(self):
        """Test multiple sensors correctly extracted from JSON text."""
        history_base_url = self._portal_client.sitemap[
            'historic_sensor_values']
        sensor_name_filter = 'anc_w.*_device_status'

        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetcher(
            valid_response='{"data":[%s, %s]}' % (sensor_json['anc_wind_device_status'],
                                                  sensor_json['anc_weather_device_status']),
            invalid_response='[]',
            starts_with=history_base_url,
            contains=quote_plus(sensor_name_filter))

        sensors = yield self._portal_client.sensor_names(sensor_name_filter)

        self.assertTrue(len(sensors) == 2, "Expect exactly 2 sensors")
        self.assertTrue(sensors[0] == 'anc_weather_device_status')
        self.assertTrue(sensors[1] == 'anc_wind_device_status')

    @gen_test
    def test_sensor_names_no_duplicate_sensors(self):
        """Test no duplicates if filters request duplicate sensors."""
        history_base_url = self._portal_client.sitemap[
            'historic_sensor_values']
        sensor_name_filters = [
            'anc_weather_wind_speed', 'anc_weather_wind_speed']

        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetcher(
            valid_response=('{"data":[%s]}' % sensor_json['anc_weather_wind_speed']),
            invalid_response='[]',
            starts_with=history_base_url,
            contains=sensor_name_filters[0])

        sensors = yield self._portal_client.sensor_names(sensor_name_filters)

        self.assertTrue(len(sensors) == 1, "Expect exactly 1 sensor")
        self.assertTrue(sensors[0] == sensor_name_filters[0])

    @gen_test
    def test_sensor_names_empty_list(self):
        """Test with sensor name that does not exist."""
        history_base_url = self._portal_client.sitemap[
            'historic_sensor_values']

        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetcher(
            valid_response='[]',
            invalid_response='[{}]'.format(
                sensor_json['anc_weather_wind_speed']),
            starts_with=history_base_url)

        sensors = yield self._portal_client.sensor_names('non_existant_sensor')

        self.assertTrue(len(sensors) == 0, "Expect exactly 0 sensors")

    @gen_test
    def test_sensor_names_exception_for_invalid_regex(self):
        """Test that invalid regex raises exception."""
        history_base_url = self._portal_client.sitemap[
            'historic_sensor_values']

        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetcher(
            valid_response=sensor_json['regex_error'],
            invalid_response=sensor_json['invalid_response'],
            starts_with=history_base_url)

        with self.assertRaises(SensorNotFoundError):
            yield self._portal_client.sensor_names('*bad')

    @gen_test
    def test_sensor_detail(self):
        """Test sensor's attributes are correctly extracted from JSON text."""
        history_base_url = self._portal_client.sitemap['historic_sensor_values']
        sensor_name = 'anc_weather_wind_speed'
        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetcher(
            valid_response=('{{"data":[{}]}}'.format( sensor_json['anc_weather_wind_speed'])),
            invalid_response=sensor_json['invalid_response'],
            starts_with=history_base_url,
            contains=sensor_name)

        with self.assertRaises(SensorNotFoundError):
            yield self._portal_client.sensor_detail('invalid_sensor_name')

        sensor_detail = yield self._portal_client.sensor_detail(sensor_name)

        self.assertTrue(sensor_detail['name'] == sensor_name)
        self.assertTrue(sensor_detail['description'] == "Wind speed")
        self.assertTrue(sensor_detail['params'] == "[0.0, 70.0]")
        self.assertTrue(sensor_detail['units'] == "m/s")
        self.assertTrue(sensor_detail['type'] == "float")
        self.assertTrue(sensor_detail['component'] == "anc")
        self.assertTrue(sensor_detail['katcp_name'] == "anc.weather.wind-speed")

    @gen_test
    def test_sensor_detail_for_multiple_sensors_but_exact_match(self):
        """Test sensor detail request with many matches, but one exact match.

        In this case, there is a sensor name that also happens to be a prefix
        for other sensor names.  E.g. if we have "sensor_foo", and "sensor_foo2",
        the details of "sensor_foo" must be available, even though there are
        multiple sensors that match that pattern.
        """
        history_base_url = self._portal_client.sitemap[
            'historic_sensor_values']
        sensor_name_filter = 'anc_gust_wind_speed'

        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetcher(
            valid_response='{{"data" : [{}, {}]}}'.format (sensor_json['anc_gust_wind_speed2'],
                                                          sensor_json['anc_gust_wind_speed']),
            invalid_response="[]",
            starts_with=history_base_url,
            contains=sensor_name_filter)

        sensor_detail = yield self._portal_client.sensor_detail('anc_gust_wind_speed')
        self.assertTrue(sensor_detail['name'] == 'anc_gust_wind_speed')

    @gen_test
    def test_sensor_detail_exception_for_multiple_sensors(self):
        """Test exception raised if sensor name is not unique for detail request."""
        history_base_url = self._portal_client.sitemap[
            'historic_sensor_values']
        sensor_name_filter = 'anc_w.*_device_status'

        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetcher(
            valid_response='[{}, {}]'.format(sensor_json['anc_wind_device_status'],
                                             sensor_json['anc_weather_device_status']),
            invalid_response="[]",
            starts_with=history_base_url,
            contains=sensor_name_filter)

        with self.assertRaises(SensorNotFoundError):
            yield self._portal_client.sensor_detail(sensor_name_filter)

    @gen_test
    def test_sensor_value_invalid_results(self):
        """test that we handle the monitor server returning an invalid string"""
        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetcher('')
        with self.assertRaises(InvalidResponseError):
            yield self._portal_client.sensor_value("INVALID_SENSOR")

    @gen_test
    def test_sensor_value_no_results(self):
        """Test that we handle no matches"""
        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetcher('[]')
        with self.assertRaises(SensorNotFoundError):
            yield self._portal_client.sensor_value("INVALID_SENSOR")

    @gen_test
    def test_sensor_value_multiple_results_one_match(self):
        """Test that we handle multiple results correctly with one match"""

        mon_response = ('[{"status":"nominal",'
                        '"name":"anc_tfr_m018_l_band_offset","component":"anc",'
                        '"value":43680.0,'
                        '"value_ts":1530713112,"time":1531302437},'
                        '{"status":"nominal",'
                        '"name":"some_other_sample","component":"anc","value":43680.0,'
                        '"value_ts":111.111,"time":222.222}]')

        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetcher(mon_response)
        result = yield self._portal_client.sensor_value("anc_tfr_m018_l_band_offset")
        expected_result = SensorSample(sample_time=1531302437, value=43680.0,
                                       status='nominal')
        assert result == expected_result

        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetcher(mon_response)
        result = yield self._portal_client.sensor_value("anc_tfr_m018_l_band_offset",
                                                        include_value_ts=True)
        expected_result = SensorSampleValueTime(sample_time=1531302437,
                                                value_time=1530713112,
                                                value=43680.0, status='nominal')
        assert result == expected_result

    @gen_test
    def test_sensor_value_multiple_results_no_match(self):
        """Test that we handle multiple results correctly with no matches"""

        mon_response = ('[{"status":"nominal",'
                        '"name":"some_other_sample","component":"anc",'
                        '"value":43680.0,'
                        '"value_ts":1530713112.9800000191,"time":1531302437},'
                        '{"status":"nominal",'
                        '"name":"some_other_sample1","component":"anc","value":43680.0,'
                        '"value_ts":111.111,"time":222.222}]')

        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetcher(mon_response)
        with self.assertRaises(SensorNotFoundError):
            yield self._portal_client.sensor_value("anc_tfr_m018_l_band_offset_average")

    @gen_test
    def test_sensor_value_one_result(self):
        """Test that we can handle single result"""
        mon_response = ('[{"status":"nominal",'
                        '"name":"some_other_sample","component":"anc","value":43680.0,'
                        '"value_ts":111.111,"time":222.222}]')

        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetcher(mon_response)
        expected_result = SensorSample(sample_time=222.222, value=43680.0, status='nominal')
        res = yield self._portal_client.sensor_value("anc_tfr_m018_l_band_offset_average")
        assert res == expected_result

        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetcher(mon_response)
        expected_result = SensorSampleValueTime(sample_time=222.222, value_time=111.111,
                                                value=43680.0, status=u'nominal')
        res = yield self._portal_client.sensor_value("anc_tfr_m018_l_band_offset_average",
                                                     include_value_ts=True)
        assert res == expected_result

    @gen_test
    def test_sensor_values_invalid_results(self):
        """test that we handle the monitor server returning an invalid string"""
        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetcher('')
        with self.assertRaises(InvalidResponseError):
            yield self._portal_client.sensor_values("INVALID_FILTER")

    @gen_test
    def test_sensor_values_no_results(self):
        """Test that we handle no matches"""
        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetcher('[]')
        with self.assertRaises(SensorNotFoundError):
            yield self._portal_client.sensor_values("INVALID_FILTER")

    @gen_test
    def test_sensor_values_one_filter_multiple_matches(self):
        """Test that we handle multiple matches correctly with one filter"""

        mon_response = ('[{"status":"nominal",'
                        '"name":"anc_tfr_m018_l_band_offset","component":"anc",'
                        '"value":43680.0,'
                        '"value_ts":1530713112,"time":1531302437},'
                        '{"status":"nominal",'
                        '"name":"some_other_sample","component":"anc","value":43680.0,'
                        '"value_ts":111.111,"time":222.222}]')

        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetcher(mon_response)
        result = yield self._portal_client.sensor_values("ARBITRARY_FILTER")
        expected_result = {
            "anc_tfr_m018_l_band_offset": SensorSample(sample_time=1531302437,
                                                       value=43680.0,
                                                       status='nominal'),
            "some_other_sample": SensorSample(sample_time=222.222,
                                              value=43680.0,
                                              status='nominal')}
        assert result == expected_result

        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetcher(mon_response)
        result = yield self._portal_client.sensor_values("ARBITRARY_FILTER",
                                                         include_value_ts=True)
        expected_result = {
            "anc_tfr_m018_l_band_offset": SensorSampleValueTime(sample_time=1531302437,
                                                              value_time=1530713112,
                                                              value=43680.0,
                                                              status='nominal'),
            "some_other_sample": SensorSampleValueTime(sample_time=222.222,
                                                     value_time=111.111,
                                                     value=43680.0,
                                                     status='nominal')}
        assert result == expected_result

    @gen_test
    def test_sensor_values_multiple_filters_multiple_matches(self):
        """Test that we handle multiple matches correctly with multiple filters"""

        mon_response_0 = ('[{"status":"nominal",'
                          '"name":"some_other_sample_0",'
                          '"component":"anc","value":43480.0,'
                          '"value_ts":110.111,"time":220.222}]')
        mon_response_1 = ('[{"status":"nominal",'
                          '"name":"some_other_sample_1",'
                          '"component":"anc","value":43580.0,'
                          '"value_ts":111.111,"time":221.222}]')

        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetchers(
            valid_responses=[mon_response_0, mon_response_1],
            invalid_responses=['1error', '2error'],
            containses=["sample_0", "sample_1"]
            )

        expected_result = {"some_other_sample_0": SensorSample(sample_time=220.222,
                                                               value=43480.0,
                                                               status='nominal'),
                           "some_other_sample_1": SensorSample(sample_time=221.222,
                                                               value=43580.0,
                                                               status='nominal')}
        res = yield self._portal_client.sensor_values(["some_other_sample_0",
                                                       "some_other_sample_1"])
        assert res == expected_result, res

    @gen_test
    def test_sensor_history_single_sensor_without_value_time(self):
        """Test that time ordered data without value_time is received for a
        single sensor request.
        """
        history_base_url = self._portal_client.sitemap[
            'historic_sensor_values']
        sensor_name = 'anc_mean_wind_speed'

        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetcher(
            valid_response=sensor_data1,
            invalid_response='error',
            starts_with=history_base_url,
            contains=sensor_name)

        samples = yield self._portal_client.sensor_history(
            sensor_name, start_time_sec=0, end_time_sec=time.time(),
            include_value_ts=False)
        # expect exactly 4 samples
        self.assertTrue(len(samples) == 4)

        # ensure time order is increasing
        time_sec = 0.0
        for sample in samples:
            self.assertGreater(sample.sample_time, time_sec)
            time_sec = sample.sample_time
            # Ensure sample contains sample_time, value, status
            self.assertEqual(len(sample), 3)

    @gen_test
    def test_sensor_history_single_sensor_with_value_time(self):
        """Test that time ordered data with value_time is received for a single sensor request."""
        history_base_url = self._portal_client.sitemap[
            'historic_sensor_values']
        sensor_name = 'anc_mean_wind_speed'
        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetcher(
            valid_response=sensor_data3,
            invalid_response='error',
            starts_with=history_base_url,
            contains=sensor_name)

        samples = yield self._portal_client.sensor_history(
            sensor_name, start_time_sec=0, end_time_sec=time.time(), include_value_ts=True)
        # expect exactly 3 samples
        self.assertTrue(len(samples) == 3)

        # ensure time order is increasing
        time_sec = 0
        for sample in samples:
            self.assertGreater(sample.sample_time, time_sec)
            time_sec = sample.sample_time
            # Ensure sample contains sample_time, value_time, value, status
            self.assertEqual(len(sample), 4)
            # Ensure value_time
            self.assertGreater(sample.sample_time, sample.value_time)

    @gen_test
    def test_sensor_history_single_sensor_valid_times(self):
        """Test that time ordered data is received for a single sensor request."""
        history_base_url = self._portal_client.sitemap[
            'historic_sensor_values']
        sensor_name = 'anc_mean_wind_speed'
        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetcher(
            valid_response=sensor_data3,
            invalid_response='error',
            starts_with=history_base_url,
            contains=sensor_name)

        samples = yield self._portal_client.sensor_history(
            sensor_name, start_time_sec=0, end_time_sec=time.time())
        # expect exactly 3 samples
        self.assertTrue(len(samples) == 3)

        # ensure time order is increasing
        time_sec = 0
        for sample in samples:
            self.assertGreater(sample[0], time_sec)
            time_sec = sample[0]

    @gen_test
    def test_sensor_history_single_sensor_invalid_times(self):
        """Test that no data is received for a single sensor request."""
        history_base_url = self._portal_client.sitemap[
            'historic_sensor_values']
        sensor_name = 'anc_mean_wind_speed'

        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetcher(
            valid_response=sensor_data_fail,
            invalid_response='error',
            starts_with=history_base_url,
            contains=sensor_name)

        samples = yield self._portal_client.sensor_history(
            sensor_name, start_time_sec=0, end_time_sec=100)
        # expect no samples
        self.assertTrue(len(samples) == 0)

    @gen_test
    def test_sensor_history_multiple_sensors_valid_times(self):
        """Test that time ordered data is received for a multiple sensor request."""
        history_base_url = self._portal_client.sitemap[
            'historic_sensor_values']
        sensor_name_filter = 'anc_.*_wind_speed'
        sensor_names = ['anc_gust_wind_speed', 'anc_mean_wind_speed']
        # complicated way to define the behaviour for the 3 expected HTTP requests
        #  - 1st call gives sensor list
        #  - 2nd call provides the sample history for sensor 0
        #  - 3rd call provides the sample history for sensor 1
        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetchers(
            valid_responses=[
                '{{"data" : [{}, {}]}}'.format(sensor_json[sensor_names[0]],
                                               sensor_json[sensor_names[1]]),
                sensor_data2, sensor_data1
            ],
            invalid_responses=['1error', '2error', '3error'],
            starts_withs=history_base_url,
            containses=[
                quote_plus(sensor_name_filter),
                sensor_names[0],
                sensor_names[1]])

        histories = yield self._portal_client.sensors_histories(sensor_name_filter,
                                                                start_time_sec=0,
                                                                end_time_sec=time.time())
        # expect exactly 2 lists of samples
        self.assertTrue(len(histories) == 2)
        # expect keys to match the 2 sensor names
        self.assertIn(sensor_names[0], list(histories.keys()))
        self.assertIn(sensor_names[1], list(histories.keys()))
        # expect 3 samples for 1st, and 4 samples for 2nd
        self.assertTrue(len(histories[sensor_names[0]]) == 3)
        self.assertTrue(len(histories[sensor_names[1]]) == 4)

        # ensure time order is increasing, per sensor
        for sensor in histories:
            time_sec = 0
            for sample in histories[sensor]:
                self.assertGreater(sample[0], time_sec)
                time_sec = sample[0]

    @gen_test
    def test_sensor_history_multiple_sensor_futures(self):
        """Test multiple sensor requests in list of futures."""
        history_base_url = self._portal_client.sitemap[
            'historic_sensor_values']
        sensor_names = ['anc_mean_wind_speed', 'anc_gust_wind_speed']

        # complicated way to define the behaviour for the 2 expected HTTP requests
        #  - 1st call provides the sample history for sensor 0
        #  - 2nd call provides the sample history for sensor 1
        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetchers(
            valid_responses=[
                sensor_data4,
                sensor_data3],
            invalid_responses=['1error', '2error'],
            starts_withs=history_base_url,
            containses=[
                sensor_names[0],
                sensor_names[1]])

        futures = []
        futures.append(self._portal_client.sensor_history(
            sensor_names[0], start_time_sec=0, end_time_sec=time.time()))
        futures.append(self._portal_client.sensor_history(
            sensor_names[1], start_time_sec=0, end_time_sec=time.time()))
        yield futures
        histories = {}
        for future, sensor_name in zip(futures, sensor_names):
            histories[sensor_name] = future.result()
        # expect exactly 2 lists of samples
        self.assertTrue(len(histories) == 2)
        # expect keys to match the 2 sensor names
        self.assertIn(sensor_names[0], list(histories.keys()))
        self.assertIn(sensor_names[1], list(histories.keys()))
        # expect 4 samples for 1st, and 3 samples for 2nd
        self.assertTrue(len(histories[sensor_names[0]]) == 4)
        self.assertTrue(len(histories[sensor_names[1]]) == 3)

        # ensure time order is increasing, per sensor
        for sensor in histories:
            time_sec = 0
            for sample in histories[sensor]:
                self.assertGreater(sample[0], time_sec)
                time_sec = sample[0]

    @gen_test
    def test_future_targets(self):
        sb_base_url = self._portal_client.sitemap['schedule_blocks']
        sb_id_code_1 = "20160908-0005"
        sb_id_code_2 = "20160908-0006"
        sb_id_code_3 = "20160908-0007"

        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetchers(
            valid_responses=[
                r"""
                {"result":
                    {"id_code":"20160908-0005",
                     "targets":""
                    }
                }""",
                r"""
                {"result":
                    {"id_code":"20160908-0006",
                     "targets":""
                    }
                }""",
                r"""
                {"result":
                    {"id_code":"20160908-0007",
                     "targets":"[{\"key\": \"some json body\"}]"
                    }
                }"""],
            invalid_responses=[
                """{"result":null}""",
                """{"result":null}""",
                """{"result":null}"""],
            starts_withs=sb_base_url,
            containses=[sb_id_code_1, sb_id_code_2, sb_id_code_3])

        with self.assertRaises(ScheduleBlockTargetsParsingError):
            yield self._portal_client.future_targets(sb_id_code_1)
        with self.assertRaises(ScheduleBlockNotFoundError):
            yield self._portal_client.future_targets('bad sb id code')
        targets_list = yield self._portal_client.future_targets(sb_id_code_3)
        self.assertEquals(targets_list, [{u'key': u'some json body'}])

    def test_create_jwt_login_token(self):
        """Test that our jwt encoding works as expected"""
        test_token = create_jwt_login_token(
            email='test@test.test', password='testpassword')
        # test tokens for this test is generated using a the email, password combination
        # and the standard JWT standard RFC 7519, see http://jwt.io
        self.assertEquals(
            test_token,
            b'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbWFpbCI6InRlc3RAdGVzdC'
            b'50ZXN0In0.aI9/c3tgy5kaKUMfeVHn/3CWLddz4lZI4yFAqHq/JH0=')
        test_token2 = create_jwt_login_token(
            email='random text should also work, you never know!',
            password='some PeOpl3 have WEIRD pa$$words?')
        self.assertEquals(
            test_token2,
            b'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbWFpbCI6InJhbmRvbSB0ZX'
            b'h0IHNob3VsZCBhbHNvIHdvcmssIHlvdSBuZXZlciBrbm93ISJ9.H1aItCXEZfNO'
            b'5CUP3vwKefqdEMBVpnNfMRYah5jPCAA=')

    @gen_test
    def test_login(self):
        """Test the login procedure.
        1. Verify username, password and role.
        2. Login with the resulting session id token
        3. Check that the session id is included as an Authorization header in
           subsequent calls"""
        auth_base_url = self._portal_client.sitemap['authorization']
        authorized_fetch_future = gen.Future()
        self._portal_client.authorized_fetch = mock.MagicMock(
            return_value=authorized_fetch_future)
        auth_fetch_result = HTTPResponse(
            HTTPRequest(auth_base_url), 200,
            buffer=buffer_bytes_io(
                '{"session_id": "token generated by katportal", "user_id": "123"}'))
        authorized_fetch_future.set_result(auth_fetch_result)

        yield self._portal_client.login('testusername@test.org', 'testpass')
        self._portal_client.authorized_fetch.assert_called_with(
            auth_token='token generated by katportal',
            url=self._portal_client.sitemap['authorization'] + '/user/login',
            body='', method='POST')
        self.assertEquals(self._portal_client._session_id,
                          'token generated by katportal')
        self.assertEquals(self._portal_client._current_user_id, '123')

        # Test a failed login
        authorized_fetch_fail_future = gen.Future()
        auth_fetch_fail_result = HTTPResponse(
            HTTPRequest(auth_base_url), 200,
            buffer=buffer_bytes_io('{"logged_in": "False"}'))
        self._portal_client.authorized_fetch = mock.MagicMock(
            return_value=authorized_fetch_fail_future)
        authorized_fetch_fail_future.set_result(auth_fetch_fail_result)
        self._portal_client.authorized_fetch.set_result(auth_fetch_fail_result)
        yield self._portal_client.login('fail username', 'fail pass')
        # test tokens for this test is generated using a the email, password combination
        # and the standard JWT standard RFC 7519, see http://jwt.io
        self._portal_client.authorized_fetch.assert_called_with(
            auth_token=b'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbWFpbCI6ImZ'
                       b'haWwgdXNlcm5hbWUifQ.IWU7Asuevn8Skm+qU7GJPuhLFoCvG47A'
                       b'M7lyRQfAbT0=',
            url='http://0.0.0.0/katauth/user/verify/read_only')
        self.assertEquals(self._portal_client._session_id, None)
        self.assertEquals(self._portal_client._current_user_id, None)

    @gen_test
    def test_logout(self):
        """Test logout procedure
        1. Login
        2. Logout
        3. Check if _session_id and _current_user_id has been cleared"""
        auth_base_url = self._portal_client.sitemap['authorization']
        # login
        authorized_fetch_future = gen.Future()
        self._portal_client.authorized_fetch = mock.MagicMock(
            return_value=authorized_fetch_future)
        auth_fetch_result = HTTPResponse(
            HTTPRequest(auth_base_url), 200,
            buffer=buffer_bytes_io(
                '{"session_id": "token generated by katportal", "user_id": "123"}'))
        authorized_fetch_future.set_result(auth_fetch_result)

        yield self._portal_client.login('testusername@test.org', 'testpass')
        self._portal_client.authorized_fetch.assert_called_with(
            auth_token='token generated by katportal',
            url=self._portal_client.sitemap['authorization'] + '/user/login',
            body='', method='POST')
        self.assertEquals(self._portal_client._session_id,
                          'token generated by katportal')
        self.assertEquals(self._portal_client._current_user_id, '123')

        # logout
        yield self._portal_client.logout()
        self.assertEquals(self._portal_client._session_id, None)
        self.assertEquals(self._portal_client._current_user_id, None)
        self._portal_client.authorized_fetch.assert_called_with(
            auth_token='token generated by katportal',
            url=self._portal_client.sitemap['authorization'] + '/user/logout',
            body='{}', method='POST')

    @gen_test
    def test_userlog_tags(self):
        """Test userlogs tags listing"""
        base_url = self._portal_client.sitemap['userlogs'] + '/tags'

        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetchers(
            valid_responses=[r"""[{
                "activated": "True",
                "slug": "",
                "name": "m047",
                "id": "1"
            },{
                "activated": "True",
                "slug": "",
                "name": "m046",
                "id": "2"
            }]"""],
            invalid_responses=['error'],
            starts_withs=base_url)

        tags = yield self._portal_client.userlog_tags()
        self.assertEquals(len(tags), 2)
        self.assertEquals(tags[0]['id'], '1')
        self.assertEquals(tags[1]['id'], '2')

    @gen_test
    def test_userlogs(self):
        """Test userlogs listing"""
        # fake a login
        self._portal_client._session_id = 'some token'
        self._portal_client._current_user_id = 1
        # then list userlogs

        userlogs_base_url = self._portal_client.sitemap['userlogs']
        authorized_fetch_future = gen.Future()
        self._portal_client.authorized_fetch = mock.MagicMock(
            return_value=authorized_fetch_future)
        auth_fetch_result = HTTPResponse(
            HTTPRequest(userlogs_base_url), 200,
            buffer=buffer_bytes_io(
                r"""
                [{
                    "other_metadata": "[]",
                    "user_id": "1",
                    "attachments": "[]",
                    "tags": "[]",
                    "timestamp": "2017-02-07 08:47:22",
                    "start_time": "2017-02-07 00:00:00",
                    "modified": "",
                    "content": "katportalclient userlog creation content!",
                    "parent_id": "",
                    "user": {"email": "cam@ska.ac.za", "id": 1, "name": "CAM"},
                    "attachment_count": "0",
                    "id": "40",
                    "end_time": "2017-02-07 23:59:59"
                 },{
                     "other_metadata": [],
                     "user_id": 2,
                     "attachments": [],
                     "tags": "[]",
                     "timestamp": "2017-02-07 01:00:00",
                     "start_time": "2017-02-07 00:00:00",
                     "modified": "",
                     "content": "katportalclient userlog creation content 2!",
                     "parent_id": "",
                     "user": {"email": "cam2@ska.ac.za", "id": 2, "name": "CAM2"},
                     "attachment_count": "0",
                     "id": "41",
                     "end_time": "2017-02-07 23:59:59"
                  }]
                """))
        authorized_fetch_future.set_result(auth_fetch_result)

        userlogs = yield self._portal_client.userlogs()
        self.assertEquals(len(userlogs), 2)
        self.assertEquals(userlogs[0]['id'], '40')
        self.assertEquals(userlogs[1]['id'], '41')

    @gen_test
    def test_create_userlog(self):
        """Test userlog creation"""
        # fake a login
        self._portal_client._session_id = 'some token'
        self._portal_client._current_user_id = 1
        # then list userlogs

        userlogs_base_url = self._portal_client.sitemap['userlogs']
        authorized_fetch_future = gen.Future()
        self._portal_client.authorized_fetch = mock.MagicMock(
            return_value=authorized_fetch_future)
        auth_fetch_result = HTTPResponse(
            HTTPRequest(userlogs_base_url), 200,
            buffer=buffer_bytes_io(
                r"""
                {
                    "other_metadata": "[]",
                    "user_id": "1",
                    "attachments": "[]",
                    "tags": "[]",
                    "timestamp": "2017-02-07 08:47:22",
                    "start_time": "2017-02-07 00:00:00",
                    "modified": "",
                    "content": "test content",
                    "parent_id": "",
                    "user": {"email": "cam@ska.ac.za", "id": 1, "name": "CAM"},
                    "attachment_count": "0",
                    "id": "40",
                    "end_time": "2017-02-07 23:59:59"
                }
                """))
        authorized_fetch_future.set_result(auth_fetch_result)

        userlog = yield self._portal_client.create_userlog(
            content='test content',
            tag_ids=[1, 2, 3],
            start_time='2017-02-07 08:47:22',
            end_time='2017-02-07 08:47:22')
        self.assertEquals(
            userlog,
            {u'other_metadata': u'[]', u'user_id': u'1', u'attachments': u'[]',
             u'tags': u'[]', u'timestamp': u'2017-02-07 08:47:22',
             u'start_time': u'2017-02-07 00:00:00', u'modified': u'',
             u'content': u'test content',
             u'parent_id': u'',
             u'user': {u'email': u'cam@ska.ac.za', u'name': u'CAM', u'id': 1},
             u'attachment_count': u'0', u'id': u'40',
             u'end_time': u'2017-02-07 23:59:59'})

        self._portal_client.authorized_fetch.assert_called_once_with(
            auth_token='some token',
            body=mock.ANY,
            method='POST',
            url=self._portal_client.sitemap['userlogs'])
        call_kwargs = self._portal_client.authorized_fetch.call_args[1]
        actual_body_dict = json.loads(call_kwargs['body'])
        expected_body_dict = {
            "content": "test content",
            "tag_ids": [1, 2, 3],
            "start_time": "2017-02-07 08:47:22",
            "user": self._portal_client._current_user_id,
            "end_time": "2017-02-07 08:47:22"}
        self.assertDictEqual(actual_body_dict, expected_body_dict)

    @gen_test
    def test_modify_userlog(self):
        """Test userlog modification"""
        # fake a login
        self._portal_client._session_id = 'some token'
        self._portal_client._current_user_id = 1
        # then list userlogs

        userlogs_base_url = self._portal_client.sitemap['userlogs']
        userlog_fetch_future = gen.Future()
        self._portal_client.authorized_fetch = mock.MagicMock(
            return_value=userlog_fetch_future)
        fetch_result = HTTPResponse(
            HTTPRequest(userlogs_base_url), 200,
            buffer=buffer_bytes_io(
                r"""
                {
                    "other_metadata": "[]",
                    "user_id": "1",
                    "attachments": "[]",
                    "tags": "[]",
                    "timestamp": "2017-02-07 08:47:22",
                    "start_time": "2017-02-07 00:00:00",
                    "modified": "",
                    "content": "test content modified",
                    "parent_id": "",
                    "user": {"email": "cam@ska.ac.za", "id": 1, "name": "CAM"},
                    "attachment_count": "0",
                    "id": "40",
                    "end_time": "2017-02-07 23:59:59"
                }
                """))
        userlog_fetch_future.set_result(fetch_result)

        userlog_to_modify = {
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
        userlog = yield self._portal_client.modify_userlog(userlog_to_modify, [1, 2, 3])
        self.assertEquals(
            userlog,
            {u'other_metadata': u'[]', u'user_id': u'1', u'attachments': u'[]',
             u'tags': u'[]', u'timestamp': u'2017-02-07 08:47:22',
             u'start_time': u'2017-02-07 00:00:00', u'modified': u'',
             u'content': u'test content modified',
             u'parent_id': u'',
             u'user': {u'email': u'cam@ska.ac.za', u'name': u'CAM', u'id': 1},
             u'attachment_count': u'0', u'id': u'40',
             u'end_time': u'2017-02-07 23:59:59'})

        self._portal_client.authorized_fetch.assert_called_once_with(
            auth_token='some token',
            body=mock.ANY,
            method='POST',
            url='{}/{}'.format(
                self._portal_client.sitemap['userlogs'], userlog_to_modify['id']))
        call_kwargs = self._portal_client.authorized_fetch.call_args[1]
        actual_body_dict = json.loads(call_kwargs['body'])
        self.assertDictEqual(actual_body_dict, userlog_to_modify)

        # Test bad tags attribute
        with self.assertRaises(json.JSONError):
            userlog_to_modify['tags'] = 'random nonsense'
            userlog = yield self._portal_client.modify_userlog(userlog_to_modify)

    @gen_test
    def test_sensor_subarray_lookup(self):
        """Test sensor subarray lookup is correctly extracted."""
        lookup_base_url = (self._portal_client.sitemap['subarray'] +
                           '/3/sensor-lookup/cbf/device_status/0')
        sensor_name_filter = 'device_status'
        expected_sensor_name = 'cbf_3_device_status'

        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetcher(
            valid_response='{"result":"cbf_3_device_status"}',
            invalid_response=['error'],
            starts_with=lookup_base_url,
            contains=sensor_name_filter)
        sensor = yield self._portal_client.sensor_subarray_lookup(
            'cbf', sensor_name_filter, False)
        self.assertTrue(sensor == expected_sensor_name)

    @gen_test
    def test_sensor_subarray_katcp_name_lookup(self):
        """Test sensor subarray lookup returns the correct katcp name."""
        lookup_base_url = (self._portal_client.sitemap['subarray'] +
                           '/3/sensor-lookup/cbf/device-status/1')
        sensor_name_filter = 'device-status'
        expected_sensor_name = 'cbf_3.device-status'

        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetcher(
            valid_response='{"result":"cbf_3.device-status"}',
            invalid_response=['error'],
            starts_with=lookup_base_url,
            contains=sensor_name_filter)
        sensor = yield self._portal_client.sensor_subarray_lookup(
            'cbf', sensor_name_filter, True)
        self.assertTrue(sensor == expected_sensor_name)

    @gen_test
    def test_sensor_subarray_invalid_sensor_lookup(self):
        """Test that sensor subarray lookup can correctly handle an invalid sensor name."""
        lookup_base_url = (self._portal_client.sitemap['subarray'] +
                           '/3/sensor-lookup/anc/device_status/0')
        sensor_name_filter = 'device_status'
        self.mock_http_async_client().fetch.side_effect = self.mock_async_fetcher(
            valid_response='{"error":"SensorLookupError: Could not lookup the sensor '
                           'on component. Could not determine component."}',
            invalid_response='[]',
            starts_with=lookup_base_url,
            contains=sensor_name_filter)
        with self.assertRaises(SensorLookupError):
            yield self._portal_client.sensor_subarray_lookup(
                'anc', sensor_name_filter, False)


    def mock_async_fetchers(self, valid_responses, invalid_responses, starts_withs=None,
                            ends_withs=None, containses=None):
        """Allows definition of multiple HTTP async fetchers."""
        num_calls = len(valid_responses)
        if starts_withs is None or isinstance(starts_withs, basestring):
            starts_withs = [starts_withs] * num_calls
        if ends_withs is None or isinstance(ends_withs, basestring):
            ends_withs = [ends_withs] * num_calls
        if containses is None or isinstance(containses, basestring):
            containses = [containses] * num_calls
        assert(len(invalid_responses) == num_calls)
        assert(len(starts_withs) == num_calls)
        assert(len(ends_withs) == num_calls)
        assert(len(containses) == num_calls)
        mock_fetches = [self.mock_async_fetcher(v, i, s, e, c)
                        for v, i, s, e, c in zip(
                            valid_responses, invalid_responses,
                            starts_withs, ends_withs, containses)]
        # flip order so that poping effectively goes from first to last input
        mock_fetches.reverse()

        def mock_fetch(url):
            if url == SITEMAP_URL:
                # Don't consume from the list, because it's not the request
                # we're looking for.
                single_fetch = mock_fetches[-1]
            else:
                single_fetch = mock_fetches.pop()
            return single_fetch(url)

        return mock_fetch


    def mock_async_fetcher(self, valid_response, invalid_response=None, starts_with=None,
                           ends_with=None, contains=None):
        """Returns a mock HTTP async fetch function, depending on the conditions."""

        def mock_fetch(url, method="GET", body=None):
            if url == SITEMAP_URL:
                sitemap = {'client':
                           {'websocket': self.websocket_url,
                            'historic_sensor_values': r"http://0.0.0.0/history",
                            'schedule_blocks': r"http://0.0.0.0/sb",
                            'capture_blocks': r"http://0.0.0.0/cb",
                            'subarray_sensor_values': r"http://0.0.0.0/sensor-list",
                            'target_descriptions': r"http://0.0.0.0/sources",
                            'sub_nr': '3',
                            'authorization': r"http://0.0.0.0/katauth",
                            'userlogs': r"http://0.0.0.0/katcontrol/userlogs",
                            'subarray': r"http:/0.0.0.0/katcontrol/subarray",
                            'monitor': r"http:/0.0.0.0/katmonitor",
                            }
                           }
                response = json.dumps(sitemap)
            else:
                start_ok = starts_with is None or url.startswith(starts_with)
                end_ok = ends_with is None or url.endswith(ends_with)
                contains_ok = contains is None or contains in url

                if (start_ok and end_ok and contains_ok) or invalid_response is None:
                    response = valid_response
                else:
                    response = invalid_response

            body_buffer = buffer_bytes_io(response)
            result = HTTPResponse(HTTPRequest(url), 200, buffer=body_buffer)
            future = concurrent.Future()
            future.set_result(result)
            return future


        return mock_fetch


def buffer_bytes_io(message):
    """Return a string as BytesIO, in Python 2 and 3."""
    return io.BytesIO(bytes(message, encoding='utf-8'))
