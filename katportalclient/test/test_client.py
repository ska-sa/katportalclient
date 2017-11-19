# Copyright 2015 SKA South Africa (http://ska.ac.za/)
# BSD license - see COPYING for details
"""Tests for katportalclient."""


import logging
import StringIO
import time
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
    KATPortalClient, JSONRPCRequest, ScheduleBlockNotFoundError, SensorNotFoundError,
    SensorHistoryRequestError, ScheduleBlockTargetsParsingError, create_jwt_login_token)


LOGGER_NAME = 'test_portalclient'


# Example JSON text for sensor request responses
sensor_json = {
    "anc_weather_wind_speed": """["anc_weather_wind_speed","anc",
                                  {"description":"Wind speed",
                                   "systype":"mkat",
                                   "site":"deva",
                                   "katcp_name":"anc.weather.wind-speed",
                                   "params":"[0.0, 70.0]",
                                   "units":"m\/s",
                                   "type":"float"}]""",

    "anc_mean_wind_speed": """["anc_mean_wind_speed","anc",
                                {"description":"Mean wind speed",
                                 "systype":"mkat",
                                 "site":"deva",
                                 "katcp_name":"anc.mean-wind-speed",
                                 "params":"[0.0, 70.0]",
                                 "units":"m\/s",
                                 "type":"float"}]""",

    "anc_gust_wind_speed": """["anc_gust_wind_speed","anc",
                               {"description":"Gust wind speed",
                                "systype":"mkat",
                                "site":"deva",
                                "katcp_name":"anc.gust-wind-speed",
                                "params":"[0.0, 70.0]",
                                "units":"m\/s",
                                "type":"float"}]""",

    "anc_gust_wind_speed2": """["anc_gust_wind_speed2","anc",
                               {"description":"Gust wind speed2",
                                "systype":"mkat",
                                "site":"deva",
                                "katcp_name":"anc.gust-wind-speed2",
                                "params":"[0.0, 72.0]",
                                "units":"m\/s",
                                "type":"float"}]""",

    "anc_wind_device_status": """["anc_wind_device_status","anc",
                                  {"description":"Overall status of wind system",
                                   "systype":"mkat",
                                   "site":"deva",
                                   "katcp_name":"anc.wind.device-status",
                                   "params":"['ok', 'degraded', 'fail']",
                                   "units":"",
                                   "type":"discrete"}]""",

    "anc_weather_device_status": """["anc_weather_device_status","anc",
                                     {"description":"Overall status of weather system",
                                      "systype":"mkat",
                                       "site":"deva",
                                       "katcp_name":"anc.weather.device-status",
                                       "params":"['ok', 'degraded', 'fail']",
                                       "units":"",
                                       "type":"discrete"}]""",

    "regex_error": """{"error":"invalid regular expression: quantifier operand invalid\n"}"""
}


# Example redis-pubsub message for sensor history
sensor_history_pub_messages_json = {
    "init": """{"result":[],"id":"redis-pubsub-init"}""",

    "anc_mean_wind_speed": [
        # Initial inform has done:false, and num_samples_to_be_published 0
        """{"result":{"msg_pattern":"test_namespace:*","msg_channel":"test_namespace:katstore_data","msg_data":{"inform_type":"sample_history","inform_data":{"num_samples_to_be_published":0,"sensor_name":"anc_mean_wind_speed","done":false}}},"id":"redis-pubsub"}""",
        # Next inform has done:false, and num_samples_to_be_published > 0, if
        # any data
        """{"result":{"msg_pattern":"test_namespace:*","msg_channel":"test_namespace:katstore_data","msg_data":{"inform_type":"sample_history","inform_data":{"num_samples_to_be_published":4,"sensor_name":"anc_mean_wind_speed","done":false}}},"id":"redis-pubsub"}""",

        # Multiple data messages (may be out of order)
        """{"result":{"msg_pattern":"test_namespace:*","msg_channel":"test_namespace:katstore_data","msg_data":[[1476164224429,1476164223101,1476164224429354,"5.07571614843","anc_mean_wind_speed","nominal"],[1476164225534,1476164224102,1476164225534476,"5.07574851017","anc_mean_wind_speed","nominal"]]},"id":"redis-pubsub"}""",
        """{"result":{"msg_pattern":"test_namespace:*","msg_channel":"test_namespace:katstore_data","msg_data":[[1476164228142,1476164227102,1476164228142342,"5.0883800412","anc_mean_wind_speed","nominal"]]},"id":"redis-pubsub"}""",
        """{"result":{"msg_pattern":"test_namespace:*","msg_channel":"test_namespace:katstore_data","msg_data":[[1476164226128,1476164225103,1476164226128442,"5.0753700255","anc_mean_wind_speed","nominal"]]},"id":"redis-pubsub"}""",

        # Could get more informs with done:false
        """{"result":{"msg_pattern":"test_namespace:*","msg_channel":"test_namespace:katstore_data","msg_data":{"inform_type":"sample_history","inform_data":{"num_samples_to_be_published":0,"sensor_name":"anc_mean_wind_speed","done":false}}},"id":"redis-pubsub"}""",
        # Final inform has done:true and num_samples_to_be_published: 0
        """{"result":{"msg_pattern":"test_namespace:*","msg_channel":"test_namespace:katstore_data","msg_data":{"inform_type":"sample_history","inform_data":{"num_samples_to_be_published":0,"sensor_name":"anc_mean_wind_speed","done":true}}},"id":"redis-pubsub"}"""
    ],

    "anc_gust_wind_speed": [
        # Initial inform has done:false, and num_samples_to_be_published 0
        """{"result":{"msg_pattern":"test_namespace:*","msg_channel":"test_namespace:katstore_data","msg_data":{"inform_type":"sample_history","inform_data":{"num_samples_to_be_published":0,"sensor_name":"anc_gust_wind_speed","done":false}}},"id":"redis-pubsub"}""",
        # Next inform has done:false, and num_samples_to_be_published > 0, if
        # any data
        """{"result":{"msg_pattern":"test_namespace:*","msg_channel":"test_namespace:katstore_data","msg_data":{"inform_type":"sample_history","inform_data":{"num_samples_to_be_published":3,"sensor_name":"anc_gust_wind_speed","done":false}}},"id":"redis-pubsub"}""",

        # Multiple data messages (may be out of order)
        """{"result":{"msg_pattern":"test_namespace:*","msg_channel":"test_namespace:katstore_data","msg_data":[[1476164225429,1476164224101,1476164225429354,"6.07571614843","anc_gust_wind_speed","nominal"],[1476164226534,1476164225102,1476164226534476,"6.07574851017","anc_gust_wind_speed","nominal"]]},"id":"redis-pubsub"}""",
        """{"result":{"msg_pattern":"test_namespace:*","msg_channel":"test_namespace:katstore_data","msg_data":[[1476164229142,1476164228102,1476164229142342,"6.0883800412","anc_gust_wind_speed","nominal"]]},"id":"redis-pubsub"}""",

        # Final inform has done:true and num_samples_to_be_published: 0
        """{"result":{"msg_pattern":"test_namespace:*","msg_channel":"test_namespace:katstore_data","msg_data":{"inform_type":"sample_history","inform_data":{"num_samples_to_be_published":0,"sensor_name":"anc_gust_wind_speed","done":true}}},"id":"redis-pubsub"}"""
    ]
}

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

        # Mock the synchronous HTTP client, with our sitemap
        http_sync_client_patcher = mock.patch('tornado.httpclient.HTTPClient')
        self.addCleanup(http_sync_client_patcher.stop)
        self.mock_http_sync_client = http_sync_client_patcher.start()

        def mock_fetch(url):
            sitemap = {'client':
                       {'websocket': self.websocket_url,
                        'historic_sensor_values': r"http://0.0.0.0/history",
                        'schedule_blocks': r"http://0.0.0.0/sb",
                        'subarray_sensor_values': r"http://0.0.0.0/sensor-list",
                        'target_descriptions': r"http://0.0.0.0/sources",
                        'sub_nr': '3',
                        'authorization': r"http://0.0.0.0/katauth",
                        'userlogs': r"http://0.0.0.0/katcontrol/userlogs",
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
        yield self._portal_client._websocket_message(None)
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
        yield self._portal_client._websocket_message(None)
        self._portal_client._resend_subscriptions_and_strategies.assert_called_once()

        # test another reconnect if resending the strategies did not work on a
        # reconnect
        resend_future2 = gen.Future()
        resend_future2.set_result(None)
        self._portal_client._resend_subscriptions_and_strategies = mock.MagicMock(
            return_value=resend_future2)
        self._portal_client._resend_subscriptions_and_strategies.side_effect = Exception(
            'some exception was thrown while _resend_subscriptions_and_strategies')
        self._portal_client._io_loop.call_later = mock.MagicMock()
        yield self._portal_client._websocket_message(None)
        self._portal_client._io_loop.call_later.assert_called_once()

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
        self.assertTrue('mode' in result.keys())
        self._portal_client._cache_jsonrpc_request.assert_called_once()

    @gen_test
    def test_set_sampling_strategies(self):
        self._portal_client._cache_jsonrpc_request = mock.MagicMock()
        yield self._portal_client.connect()
        result = yield self._portal_client.set_sampling_strategies(
            'ants', ['mode', 'sensors_ok', 'ap_connected'], 'event-rate 1 5')
        self.assertTrue(isinstance(result, dict))
        self.assertTrue('mode' in result.keys())
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
        self.assertTrue(sitemap['sub_nr'] == '3')

    @gen_test
    def test_schedule_blocks_assigned_list_valid(self):
        """Test schedule block IDs are correctly extracted from JSON text."""
        schedule_block_base_url = self._portal_client.sitemap[
            'schedule_blocks']

        self.mock_http_async_client().fetch.side_effect = mock_async_fetcher(
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

        self.mock_http_async_client().fetch.side_effect = mock_async_fetcher(
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

        self.mock_http_async_client().fetch.side_effect = mock_async_fetcher(
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
    def test_sensor_names_single_sensor_valid(self):
        """Test single sensor name is correctly extracted from JSON text."""
        history_base_url = self._portal_client.sitemap[
            'historic_sensor_values']
        sensor_name_filter = 'anc_weather_wind_speed'

        self.mock_http_async_client().fetch.side_effect = mock_async_fetcher(
            valid_response='[{}]'.format(
                sensor_json['anc_weather_wind_speed']),
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

        self.mock_http_async_client().fetch.side_effect = mock_async_fetcher(
            valid_response='[{}, {}]'.format(sensor_json['anc_wind_device_status'],
                                             sensor_json['anc_weather_device_status']),
            invalid_response='[]',
            starts_with=history_base_url,
            contains=sensor_name_filter)

        sensors = yield self._portal_client.sensor_names(sensor_name_filter)

        self.assertTrue(len(sensors) == 2, "Expect exactly 2 sensors")
        self.assertIn('anc_wind_device_status', sensors)
        self.assertIn('anc_weather_device_status', sensors)

    @gen_test
    def test_sensor_names_no_duplicate_sensors(self):
        """Test no duplicates if filters request duplicate sensors."""
        history_base_url = self._portal_client.sitemap[
            'historic_sensor_values']
        sensor_name_filters = [
            'anc_weather_wind_speed', 'anc_weather_wind_speed']

        self.mock_http_async_client().fetch.side_effect = mock_async_fetcher(
            valid_response='[{}]'.format(
                sensor_json['anc_weather_wind_speed']),
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

        self.mock_http_async_client().fetch.side_effect = mock_async_fetcher(
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

        self.mock_http_async_client().fetch.side_effect = mock_async_fetcher(
            valid_response=sensor_json['regex_error'],
            invalid_response='[]',
            starts_with=history_base_url)

        with self.assertRaises(SensorNotFoundError):
            yield self._portal_client.sensor_names('*bad')

    @gen_test
    def test_sensor_detail(self):
        """Test sensor's attributes are correctly extracted from JSON text."""
        history_base_url = self._portal_client.sitemap[
            'historic_sensor_values']
        sensor_name = 'anc_weather_wind_speed'

        self.mock_http_async_client().fetch.side_effect = mock_async_fetcher(
            valid_response='[{}]'.format(
                sensor_json['anc_weather_wind_speed']),
            invalid_response='[]',
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
        self.assertTrue(sensor_detail['katcp_name']
                        == "anc.weather.wind-speed")

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

        self.mock_http_async_client().fetch.side_effect = mock_async_fetcher(
            valid_response='[{}, {}]'.format(sensor_json['anc_gust_wind_speed2'],
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

        self.mock_http_async_client().fetch.side_effect = mock_async_fetcher(
            valid_response='[{}, {}]'.format(sensor_json['anc_wind_device_status'],
                                             sensor_json['anc_weather_device_status']),
            invalid_response="[]",
            starts_with=history_base_url,
            contains=sensor_name_filter)

        with self.assertRaises(SensorNotFoundError):
            yield self._portal_client.sensor_detail(sensor_name_filter)

    @gen_test
    def test_sensor_history_single_sensor_with_value_ts(self):
        """Test that time ordered data with value_timestamp is received for a single sensor request."""
        history_base_url = self._portal_client.sitemap[
            'historic_sensor_values']
        sensor_name = 'anc_mean_wind_speed'
        publish_messages = [sensor_history_pub_messages_json['init']]
        publish_messages.extend(sensor_history_pub_messages_json[sensor_name])

        self.mock_http_async_client().fetch.side_effect = mock_async_fetcher(
            valid_response='{"result":"success"}',
            invalid_response='error',
            starts_with=history_base_url,
            contains=sensor_name,
            publish_raw_messages=publish_messages,
            client_states=self._portal_client._sensor_history_states)

        samples = yield self._portal_client.sensor_history(
            sensor_name, start_time_sec=0, end_time_sec=time.time(), include_value_ts=False)
        # expect exactly 4 samples
        self.assertTrue(len(samples) == 4)

        # ensure time order is increasing
        time_sec = 0
        for sample in samples:
            self.assertGreater(sample.timestamp, time_sec)
            time_sec = sample.timestamp
            # Ensure sample contains timestamp, value, status
            self.assertEqual(len(sample), 3)

        samples = yield self._portal_client.sensor_history(
            sensor_name, start_time_sec=0, end_time_sec=time.time(), include_value_ts=True)
        # expect exactly 4 samples
        self.assertTrue(len(samples) == 4)

        # ensure time order is increasing
        time_sec = 0
        for sample in samples:
            self.assertGreater(sample.timestamp, time_sec)
            time_sec = sample.timestamp
            # Ensure sample contains timestamp, value_timestamp, value, status
            self.assertEqual(len(sample), 4)
            # Ensure value_timestamp
            self.assertGreater(sample.timestamp, sample.value_timestamp)

    @gen_test
    def test_sensor_history_single_sensor_valid_times(self):
        """Test that time ordered data is received for a single sensor request."""
        history_base_url = self._portal_client.sitemap[
            'historic_sensor_values']
        sensor_name = 'anc_mean_wind_speed'
        publish_messages = [sensor_history_pub_messages_json['init']]
        publish_messages.extend(sensor_history_pub_messages_json[sensor_name])

        self.mock_http_async_client().fetch.side_effect = mock_async_fetcher(
            valid_response='{"result":"success"}',
            invalid_response='error',
            starts_with=history_base_url,
            contains=sensor_name,
            publish_raw_messages=publish_messages,
            client_states=self._portal_client._sensor_history_states)

        samples = yield self._portal_client.sensor_history(
            sensor_name, start_time_sec=0, end_time_sec=time.time())
        # expect exactly 4 samples
        self.assertTrue(len(samples) == 4)

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
        publish_messages = [sensor_history_pub_messages_json['init']]
        # include first and last synchronisation messages, but no data
        publish_messages.append(
            sensor_history_pub_messages_json[sensor_name][0])
        publish_messages.append(
            sensor_history_pub_messages_json[sensor_name][-1])

        self.mock_http_async_client().fetch.side_effect = mock_async_fetcher(
            valid_response='{"result":"success"}',
            invalid_response='error',
            starts_with=history_base_url,
            contains=sensor_name,
            publish_raw_messages=publish_messages,
            client_states=self._portal_client._sensor_history_states)

        samples = yield self._portal_client.sensor_history(
            sensor_name, start_time_sec=0, end_time_sec=100)
        # expect no samples
        self.assertTrue(len(samples) == 0)

    @gen_test
    def test_sensor_history_exception_on_timeout(self):
        """Test that exception is raised is download exceeds timeout."""
        history_base_url = self._portal_client.sitemap[
            'historic_sensor_values']
        sensor_name = 'anc_mean_wind_speed'
        publish_messages = [sensor_history_pub_messages_json['init']]
        publish_messages.extend(sensor_history_pub_messages_json[sensor_name])

        self.mock_http_async_client().fetch.side_effect = mock_async_fetcher(
            valid_response='{"result":"success"}',
            invalid_response='error',
            starts_with=history_base_url,
            contains=sensor_name,
            publish_raw_messages=publish_messages,
            client_states=self._portal_client._sensor_history_states)

        with self.assertRaises(SensorHistoryRequestError):
            yield self._portal_client.sensor_history(
                sensor_name, start_time_sec=0, end_time_sec=100, timeout_sec=0)

    @gen_test
    def test_sensor_history_multiple_sensors_valid_times(self):
        """Test that time ordered data is received for a multiple sensor request."""
        history_base_url = self._portal_client.sitemap[
            'historic_sensor_values']
        sensor_name_filter = 'anc_.*_wind_speed'
        sensor_names = ['anc_mean_wind_speed', 'anc_gust_wind_speed']
        publish_messages = [
            [sensor_history_pub_messages_json['init']],
            [sensor_history_pub_messages_json['init']]
        ]
        publish_messages[0].extend(
            sensor_history_pub_messages_json[sensor_names[0]])
        publish_messages[1].extend(
            sensor_history_pub_messages_json[sensor_names[1]])

        # complicated way to define the behaviour for the 3 expected HTTP requests
        #  - 1st call gives sensor list
        #  - 2nd call provides the sample history for sensor 0
        #  - 3rd call provides the sample history for sensor 1
        self.mock_http_async_client().fetch.side_effect = mock_async_fetchers(
            valid_responses=[
                '[{}, {}]'.format(sensor_json[sensor_names[0]],
                                  sensor_json[sensor_names[1]]),
                '{"result":"success"}',
                '{"result":"success"}'],
            invalid_responses=['1error', '2error', '3error'],
            starts_withs=history_base_url,
            containses=[
                sensor_name_filter,
                sensor_names[0],
                sensor_names[1]],
            publish_raw_messageses=[
                None,
                publish_messages[0],
                publish_messages[1]],
            client_stateses=[
                None,
                self._portal_client._sensor_history_states,
                self._portal_client._sensor_history_states])

        histories = yield self._portal_client.sensors_histories(
            sensor_name_filter, start_time_sec=0, end_time_sec=time.time())
        # expect exactly 2 lists of samples
        self.assertTrue(len(histories) == 2)
        # expect keys to match the 2 sensor names
        self.assertIn(sensor_names[0], histories.keys())
        self.assertIn(sensor_names[1], histories.keys())
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
    def test_sensor_history_multiple_sensor_futures(self):
        """Test multiple sensor requests in list of futures."""
        history_base_url = self._portal_client.sitemap[
            'historic_sensor_values']
        sensor_names = ['anc_mean_wind_speed', 'anc_gust_wind_speed']
        publish_messages = [
            [sensor_history_pub_messages_json['init']],
            [sensor_history_pub_messages_json['init']]
        ]
        publish_messages[0].extend(
            sensor_history_pub_messages_json[sensor_names[0]])
        publish_messages[1].extend(
            sensor_history_pub_messages_json[sensor_names[1]])

        # complicated way to define the behaviour for the 2 expected HTTP requests
        #  - 1st call provides the sample history for sensor 0
        #  - 2nd call provides the sample history for sensor 1
        self.mock_http_async_client().fetch.side_effect = mock_async_fetchers(
            valid_responses=[
                '{"result":"success"}',
                '{"result":"success"}'],
            invalid_responses=['1error', '2error'],
            starts_withs=history_base_url,
            containses=[
                sensor_names[0],
                sensor_names[1]],
            publish_raw_messageses=[
                publish_messages[0],
                publish_messages[1]],
            client_stateses=[
                self._portal_client._sensor_history_states,
                self._portal_client._sensor_history_states])

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
        self.assertIn(sensor_names[0], histories.keys())
        self.assertIn(sensor_names[1], histories.keys())
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

        self.mock_http_async_client().fetch.side_effect = mock_async_fetchers(
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
            'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbWFpbCI6InRlc3RAdGVzdC'
            '50ZXN0In0.aI9/c3tgy5kaKUMfeVHn/3CWLddz4lZI4yFAqHq/JH0=')
        test_token2 = create_jwt_login_token(
            email='random text should also work, you never know!',
            password='some PeOpl3 have WEIRD pa$$words?')
        self.assertEquals(
            test_token2,
            'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbWFpbCI6InJhbmRvbSB0ZX'
            'h0IHNob3VsZCBhbHNvIHdvcmssIHlvdSBuZXZlciBrbm93ISJ9.H1aItCXEZfNO'
            '5CUP3vwKefqdEMBVpnNfMRYah5jPCAA=')

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
            buffer=StringIO.StringIO(
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
            buffer=StringIO.StringIO('{"logged_in": "False"}'))
        self._portal_client.authorized_fetch = mock.MagicMock(
            return_value=authorized_fetch_fail_future)
        authorized_fetch_fail_future.set_result(auth_fetch_fail_result)
        self._portal_client.authorized_fetch.set_result(auth_fetch_fail_result)
        yield self._portal_client.login('fail username', 'fail pass')
        # test tokens for this test is generated using a the email, password combination
        # and the standard JWT standard RFC 7519, see http://jwt.io
        self._portal_client.authorized_fetch.assert_called_with(
            auth_token='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbWFpbCI6ImZ'
                       'haWwgdXNlcm5hbWUifQ.IWU7Asuevn8Skm+qU7GJPuhLFoCvG47A'
                       'M7lyRQfAbT0=',
            url=u'http://0.0.0.0/katauth/user/verify/read_only')
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
            buffer=StringIO.StringIO(
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

        self.mock_http_async_client().fetch.side_effect = mock_async_fetchers(
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
            buffer=StringIO.StringIO(
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
            buffer=StringIO.StringIO(
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
            body=json.dumps(
                {"content": "test content",
                 "tag_ids": [1, 2, 3],
                 "start_time": "2017-02-07 08:47:22",
                 "user": self._portal_client._current_user_id,
                 "end_time": "2017-02-07 08:47:22"}),
            method='POST',
            url=self._portal_client.sitemap['userlogs'])

    @gen_test
    def test_modify_userlog(self):
        """Test userlog creation"""
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
            buffer=StringIO.StringIO(
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
            body=json.dumps(userlog_to_modify),
            method='POST',
            url='{}/{}'.format(
                self._portal_client.sitemap['userlogs'], userlog_to_modify['id']))

        # Test bad tags attribute
        with self.assertRaises(json.JSONError):
            userlog_to_modify['tags'] = 'random nonsense'
            userlog = yield self._portal_client.modify_userlog(userlog_to_modify)


def mock_async_fetchers(valid_responses, invalid_responses, starts_withs=None,
                        ends_withs=None, containses=None, publish_raw_messageses=None,
                        client_stateses=None):
    """Allows definition of multiple HTTP async fetchers."""
    num_calls = len(valid_responses)
    if starts_withs is None or isinstance(starts_withs, basestring):
        starts_withs = [starts_withs] * num_calls
    if ends_withs is None or isinstance(ends_withs, basestring):
        ends_withs = [ends_withs] * num_calls
    if containses is None or isinstance(containses, basestring):
        containses = [containses] * num_calls
    if publish_raw_messageses is None:
        publish_raw_messageses = [None] * num_calls
    if client_stateses is None:
        client_stateses = [None] * num_calls
    assert(len(invalid_responses) == num_calls)
    assert(len(starts_withs) == num_calls)
    assert(len(ends_withs) == num_calls)
    assert(len(containses) == num_calls)
    assert(len(publish_raw_messageses) == num_calls)
    assert(len(client_stateses) == num_calls)

    mock_fetches = [mock_async_fetcher(v, i, s, e, c, p, cs)
                    for v, i, s, e, c, p, cs in zip(
                        valid_responses, invalid_responses,
                        starts_withs, ends_withs, containses,
                        publish_raw_messageses, client_stateses)]
    # flip order so that poping effectively goes from first to last input
    mock_fetches.reverse()

    def mock_fetch(url):
        single_fetch = mock_fetches.pop()
        return single_fetch(url)

    return mock_fetch


def mock_async_fetcher(valid_response, invalid_response, starts_with=None,
                       ends_with=None, contains=None, publish_raw_messages=None,
                       client_states=None):
    """Returns a mock HTTP async fetch function, depending on the conditions."""

    def mock_fetch(url, method="GET", body=None):
        start_ok = starts_with is None or url.startswith(starts_with)
        end_ok = ends_with is None or url.endswith(ends_with)
        contains_ok = contains is None or contains in url

        if start_ok and end_ok and contains_ok:
            body_buffer = StringIO.StringIO(valid_response)
        else:
            body_buffer = StringIO.StringIO(invalid_response)

        # optionally send raw message from test websocket server
        if publish_raw_messages and test_websocket:
            for raw_message in publish_raw_messages:
                if isinstance(client_states, dict):
                    # we need to rewrite the namespace, since the client
                    # generates a random one per request at runtime.
                    # We have to find the state dict that contains the sensor
                    # name (in 'contains') to figure out which namespace
                    # is being used for this sensor (yes, it is hacky)
                    namespace = None
                    for key, state in client_states.items():
                        if contains == state['sensor']:
                            namespace = key
                    raw_message = raw_message.replace(
                        'test_namespace', namespace)
                test_websocket.write_message(raw_message)

        result = HTTPResponse(HTTPRequest(url), 200, buffer=body_buffer)
        future = concurrent.Future()
        future.set_result(result)
        return future

    return mock_fetch
