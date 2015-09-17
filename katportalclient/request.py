import uuid

import omnijson as json


class JSONRPCRequest(object):
    """Class with structure following the JSONRPC standard."""

    id = ''
    method = ''
    params = None

    def __init__(self, method, params):
        self.jsonrpc = '2.0'
        self.id = str(uuid.uuid4().get_hex()[:10])
        self.method = method
        self.params = params

    def __call__(self):
        return json.dumps(self.__dict__)
