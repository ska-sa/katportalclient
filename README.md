katportalclient
===============

A client for simple access to **katportal**, via websocket and HTTP connections.
The HTTP methods allow once-off requests, like the current list of schedule blocks.  
For continuous updates, use the Pub/Sub methods, which work over a websocket.

Dependencies
------------
Details can be found in `setup.py` but basically it is only:

- katversion
- [tornado](http://www.tornadoweb.org) is used as the web framework and for its asynchronous functionality.

**Note:** `setup.py` depends on katversion, so make sure that is installed before
installing the package.

Install
-------
pip install katportalclient

Example usage
-------------

See the `examples` folder for code that demonstrates some usage scenarios.
