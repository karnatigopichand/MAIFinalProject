import unittest
from commerce_orders import Service, Database
from fakes import FakeHTTP, FakeEvents

class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.s=Service(db=Database(),http=FakeHTTP(),events=FakeEvents())
    def tearDown(self):
        self.s.db.close()
    def request(self):
        return {"order_id":"a","items":[{"sku":"book","quantity":1}],"total_cents":100,"currency":"USD","delivery_address":"Main St","payment_token":"ok"}
    def test_confirm_and_retry(self):
        self.s.http.register("commerce-inventory","/reservations",lambda p:{"status":"reserved"})
        self.s.http.register("commerce-payments","/authorizations",lambda p:{"status":"authorized"})
        self.s.create_order(self.request()); self.s.create_order(self.request())
        self.assertEqual(len(self.s.http.calls),2)
        self.assertEqual(self.s.events.messages[0]["topic"],"order.confirmed.v1")
        self.assertEqual(self.s.events.messages[0]["payload"]["delivery_address"],"Main St")
    def test_stock_rejection_stops_payment(self):
        def reject(p): raise ValueError("Insufficient stock")
        self.s.http.register("commerce-inventory","/reservations",reject)
        with self.assertRaises(ValueError): self.s.create_order(self.request())
        self.assertEqual(len(self.s.http.calls),1)
        self.assertEqual(self.s.events.messages,[])
    def test_payment_rejection_no_confirmation(self):
        self.s.http.register("commerce-inventory","/reservations",lambda p:{"status":"reserved"})
        def reject(p): raise ValueError("Payment declined")
        self.s.http.register("commerce-payments","/authorizations",reject)
        with self.assertRaises(ValueError): self.s.create_order(self.request())
        self.assertIsNone(self.s.db.get("orders","a"))
        self.assertEqual(self.s.events.messages,[])

    def test_publication_failure_can_retry(self):
        calls=[]
        def fail_once(topic,payload):
            calls.append(topic)
            if len(calls)==1: raise TimeoutError('broker receipt timeout')
            self.s.events.messages.append({'topic':topic,'payload':payload})
        self.s.events.publish=fail_once
        self.s.http.register("commerce-inventory","/reservations",lambda p:{"status":"reserved"})
        self.s.http.register("commerce-payments","/authorizations",lambda p:{"status":"authorized"})
        with self.assertRaises(TimeoutError): self.s.create_order(self.request())
        self.s.create_order(self.request())
        self.assertEqual(len(self.s.http.calls),2)
        self.assertEqual(len(self.s.events.messages),1)

if __name__ == "__main__": unittest.main()
