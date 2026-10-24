import unittest
from commerce_inventory import Service, Database
from fakes import FakeHTTP, FakeEvents

class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.s=Service(db=Database(),http=FakeHTTP(),events=FakeEvents())
    def tearDown(self):
        self.s.db.close()
    def test_duplicate_lines_and_retry(self):
        self.s.seed_stock("book",5)
        request={"order_id":"a","items":[{"sku":"book","quantity":1},{"sku":"book","quantity":2}]}
        self.s.reserve(request); self.s.reserve(request)
        self.assertEqual(self.s.db.get("stock","book")["quantity"],2)
    def test_rejection_changes_nothing(self):
        self.s.seed_stock("book",5)
        with self.assertRaises(ValueError): self.s.reserve({"order_id":"a","items":[{"sku":"book","quantity":1},{"sku":"missing","quantity":1}]})
        self.assertEqual(self.s.db.get("stock","book")["quantity"],5)
    def test_invalid_quantity(self):
        with self.assertRaises(ValueError): self.s.reserve({"order_id":"a","items":[{"sku":"book","quantity":0}]})

if __name__ == "__main__": unittest.main()
