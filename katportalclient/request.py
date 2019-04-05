# Copyright 2015 SKA South Africa (http://ska.ac.za/)
# BSD license - see COPYING for details
"""Module defining the JSON-RPC request class used by websocket client."""

import uuid

import omnijson as json

from builtins import object, str


class JSONRPCRequest(object):
    """
    Class with structure following the JSON-RPC standard.

        Parameters
        ----------
        method: str
            Name of the remote procedure to call.
        params: list
            List of parameters to be used for the remote procedure call.
    """

    id = ''
    method = ''
    params = None

    def __init__(self, method, params):
        self.jsonrpc = '2.0'
        self.id = str(uuid.uuid4().hex[:10])
        self.method = method
        self.params = params

    def __call__(self):
        """Return object's attribute dictionary in JSON form."""
        return json.dumps(self.__dict__)

    def __repr__(self):
        """Return a human readable string of the object"""
        return "{_class}: id: {_id}, method: {method}, params: {params}".format(
            _class=self.__class__,
            _id=self.id,
            method=self.method,
            params=self.params)

    def method_and_params_hash(self):
        """Return a hash for the methods and params attributes for easy comparison"""
        # cast self.params to string because we can only hash immutable objects
        # if params is a list or set or anything like that, this will raise a
        # TypeError
        return hash((self.method, str(self.params)))
