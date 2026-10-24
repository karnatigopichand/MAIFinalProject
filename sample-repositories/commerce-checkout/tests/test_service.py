import unittest
from commerce_checkout import Service, Database
from fakes import FakeHTTP, FakeEvents

class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.s=Service(db=Database(),http=FakeHTTP(),events=FakeEvents())
    def tearDown(self):
        self.s.db.close()
    def test_mapping_and_idempotency(self):
        self.s.http.register("commerce-orders","/orders",lambda p: {"order_id":p["order_id"],"status":"confirmed"})
        request={"checkout_id":"a","cart":{"items":[{"sku":"book","quantity":1}]},"total_cents":100,"delivery":{"address":"Main St"},"payment_token":"ok"}
        self.assertEqual(self.s.checkout(request)["status"],"confirmed")
        self.s.checkout(request)
        self.assertEqual(len(self.s.http.calls),1)
        self.assertEqual(self.s.http.calls[0]["payload"]["delivery_address"],"Main St")
    def test_empty_cart(self):
        with self.assertRaises(ValueError): self.s.checkout({"checkout_id":"a","cart":{"items":[]}})

if __name__ == "__main__": unittest.main()
