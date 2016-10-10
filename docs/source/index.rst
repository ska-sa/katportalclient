Welcome to katportalclient's documentation
==========================================

A client for simple access to **katportal**, via websocket and HTTP connections.
The HTTP methods allow once-off requests, like the current list of schedule blocks.
For continuous updates, use the Pub/Sub methods, which work over a websocket.

Dependencies
------------
Details can be found in `setup.py` but basically it is only:

- katversion
- `tornado <http://www.tornadoweb.org>`_ is used as the web framework and for its asynchronous functionality.

**Note:** `setup.py` depends on katversion, so make sure that is installed before
installing the package.

Install
-------
pip install -r pip-build-requirements.txt

.. toctree::
   :maxdepth: 1

 katportalclient's documentation <katportalclient.rst>

Example usage
-------------

.. code-block:: python

    #!/usr/bin/env python
    import logging

    import tornado.gen

    from katportalclient import KATPortalClient


    def on_update_callback(msg):
        print 'GOT:', msg


    @tornado.gen.coroutine
    def connect(logger):
        portal_client = KATPortalClient('http://<portal server>/api/client/<subarray #>',
                                        on_update_callback, logger=logger)

        # HTTP access
        sb_ids = yield portal_client.schedule_blocks_assigned()
        print "\nSchedule block IDs:", sb_ids
        if len(sb_ids) > 0:
            sb_detail = yield portal_client.schedule_block_detail(sb_ids[0])
            print "\nDetail for SB {}:\n{}".format(sb_ids[0], sb_detail)

        sensor_names = yield portal_client.sensor_names('anc_w.*_device_status')
        print "\nMatching sensor names:", sensor_names
        if len(sensor_names) > 0:
            sensor_detail = yield portal_client.sensor_detail(sensor_names[0])
            print "\nDetail for sensor {}:\n{}".format(sensor_names[0], sensor_detail)
        raw_input("\nEnter to continue with Pub/Sub...")

        # Websocket access
        yield portal_client.connect()
        result = yield portal_client.subscribe('my_namespace')
        result = yield portal_client.set_sampling_strategies(
            'my_namespace', ['mode', 'azim', 'elev', 'sched_observation_schedule'],
            'period 5.0')


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
