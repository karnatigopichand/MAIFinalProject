import unittest
from commerce_payments import Service, Database
from fakes import FakeHTTP, FakeEvents

class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.s=Service(db=Database(),http=FakeHTTP(),events=FakeEvents())
    def tearDown(self):
        self.s.db.close()
    def test_mapping_and_retry(self):
        self.s.http.register("payment-provider-api","/charges",lambda p:{"status":"authorized","authorization_id":"auth"})
        request={"order_id":"a","amount_cents":100,"currency":"USD","payment_token":"ok"}
        self.s.authorize(request); self.s.authorize(request)
        self.assertEqual(len(self.s.http.calls),1)
        self.assertEqual(self.s.http.calls[0]["payload"]["amount"],100)
        self.assertNotIn("payment_token",self.s.db.get("authorizations","a"))
    def test_decline(self):
        self.s.http.register("payment-provider-api","/charges",lambda p:{"status":"declined"})
        with self.assertRaises(ValueError): self.s.authorize({"order_id":"a","amount_cents":100,"currency":"USD","payment_token":"decline"})
        self.assertIsNone(self.s.db.get("authorizations","a"))
    def test_invalid_amount(self):
        with self.assertRaises(ValueError): self.s.authorize({"order_id":"a","amount_cents":-1})

if __name__ == "__main__": unittest.main()
