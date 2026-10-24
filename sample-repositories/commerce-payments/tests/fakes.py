class FakeHTTP:
    """In-process request dispatcher. Routes explicitly identify remote ownership."""
    def __init__(self):
        self.routes = {}
        self.calls = []
    def register(self, target, path, handler):
        self.routes[(target,path)] = handler
    def post(self, target, path, payload):
        self.calls.append({"target":target,"method":"POST","path":path,"payload":payload})
        handler = self.routes.get((target,path))
        if handler is None:
            raise ConnectionError(f"No stub registered: {target}{path}")
        return handler(payload)

class FakeEvents:
    """MQ-shaped local queue; delivery is explicit, including intentional redelivery."""
    def __init__(self):
        self.messages = []
    def publish(self, topic, payload):
        self.messages.append({"topic":topic,"payload":payload.copy()})
