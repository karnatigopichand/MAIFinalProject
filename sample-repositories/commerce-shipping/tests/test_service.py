import unittest
from commerce_shipping import Service, Database
from fakes import FakeHTTP, FakeEvents

class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.s=Service(db=Database(),http=FakeHTTP(),events=FakeEvents())
    def tearDown(self):
        self.s.db.close()
    def test_carrier_mapping_and_redelivery(self):
        self.s.http.register("carrier-provider-api","/shipments",lambda p:{"tracking_number":"TRACK-a"})
        event={"event_id":"order:a","order_id":"a","delivery_address":"Main St"}
        self.s.consume("order.confirmed.v1",event); self.s.consume("order.confirmed.v1",event)
        self.assertEqual(len(self.s.http.calls),1)
        self.assertEqual(self.s.http.calls[0]["payload"]["address"],"Main St")
        self.assertEqual(len(self.s.events.messages),1)
    def test_wrong_topic(self):
        with self.assertRaises(ValueError): self.s.consume("unknown",{})

    def test_publication_failure_can_retry(self):
        calls=[]
        def fail_once(topic,payload):
            calls.append(topic)
            if len(calls)==1: raise TimeoutError('broker receipt timeout')
            self.s.events.messages.append({'topic':topic,'payload':payload})
        self.s.events.publish=fail_once
        self.s.http.register("carrier-provider-api","/shipments",lambda p:{"tracking_number":"TRACK-a"})
        event={"event_id":"order:a","order_id":"a","delivery_address":"Main St"}
        with self.assertRaises(TimeoutError): self.s.consume("order.confirmed.v1",event)
        self.s.consume("order.confirmed.v1",event)
        self.assertEqual(len(self.s.http.calls),1)
        self.assertEqual(len(self.s.events.messages),1)

if __name__ == "__main__": unittest.main()
