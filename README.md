katportalclient
===============

A client for websocket connections to katportal. Specifically exposing the
following server methods:
- subscribe
- unsubscribe
- set_sampling_strategy
- set_sampling_strategies

Dependencies
------------
Details can be found in `setup.py` but basically it is only:
- katversion
- tornado

*Note:* `setup.py` depends on katversion, so make sure that is installed before
installing the package.

Install
-------
pip install -r pip-build-requirements.txt

Example usage
-------------
```python
import logging

import tornado.gen

from katportalclient import KATPortalClient


def on_update_callback(msg):
    print 'GOT:', msg


@tornado.gen.coroutine
def connect(logger):
    ws_client = KATPortalClient('ws://localhost:8830/client/websocket',
                                on_update_callback, logger=logger)
    yield ws_client.connect()
    result = yield ws_client.subscribe('testing')
    result = yield ws_client.set_sampling_strategies(
        'testing', ['mode', 'actual'], 'period 1.0')
    tornado.gen.sleep(10)


if __name__ == '__main__':
    io_loop = tornado.ioloop.IOLoop.current()
    logger = logging.getLogger('katportalclient.example')
    logger.setLevel(logging.INFO)
    io_loop.add_callback(connect, logger)
    io_loop.start()

```
