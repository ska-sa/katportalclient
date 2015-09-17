Welcome to katportalclient's documentation
==========================================

**katportalclient** provides a websocket client exposing all PubSub related
methods for use with **katportal**.

.. toctree::
   :maxdepth: 1

 katportalclient's documentation <katportalclient.rst>

Example usage
-------------

.. code-block:: python

    import logging

    import tornado.gen

    from katportalclient import KATPortalClient


    def on_update_callback(msg):
        print 'GOT:', msg


    @tornado.gen.coroutine
    def connect(logger):
        ws_client = KATPortalClient('ws://<server>:<port>/<ws_endpoint>',
                                    on_update_callback, logger=logger)
        yield ws_client.connect()
        result = yield ws_client.subscribe('my_namespace')
        result = yield ws_client.set_sampling_strategies(
            'my_namespace', ['mode', 'azim', 'elev'], 'period 1.0')


    if __name__ == '__main__':
        io_loop = tornado.ioloop.IOLoop.current()
        logger = logging.getLogger('katportalclient.example')
        logger.setLevel(logging.INFO)
        io_loop.add_callback(connect, logger)
        io_loop.start()


Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
