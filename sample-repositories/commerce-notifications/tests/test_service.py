import unittest
from commerce_notifications import Service, Database
from fakes import FakeHTTP, FakeEvents

class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.s=Service(db=Database(),http=FakeHTTP(),events=FakeEvents())
    def tearDown(self):
        self.s.db.close()
    def test_templates_and_deduplication(self):
        order={"event_id":"order:a","order_id":"a"}
        self.s.consume("order.confirmed.v1",order); self.s.consume("order.confirmed.v1",order)
        result=self.s.consume("shipment.created.v1",{"event_id":"shipment:a","order_id":"a","tracking_number":"TRACK-a"})
        self.assertIn("TRACK-a",result["body"])
        count=self.s.db.connection.execute("SELECT COUNT(*) FROM records WHERE kind='outbox'").fetchone()[0]
        self.assertEqual(count,2)
    def test_wrong_topic(self):
        with self.assertRaises(ValueError): self.s.consume("unknown",{})

if __name__ == "__main__": unittest.main()
