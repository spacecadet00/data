import unittest
from src.collector import normalize, parse_card_lines, parse_json_objects
from src.build_stats import pctile

class CollectorTests(unittest.TestCase):
    def test_known_gym(self):
        r = parse_card_lines("Sengkang ActiveSG Gym\n61% full", "gym")
        self.assertEqual(r["pct"], 61)
        self.assertEqual(r["type"], "gym")

    def test_pool_closed(self):
        r = parse_card_lines("Sengkang Swimming Complex\nClosed", "pool")
        self.assertIsNone(r["pct"])
        self.assertEqual(r["status"], "closed")

    def test_absent_reading(self):
        self.assertIsNone(parse_card_lines("ActiveSG Gym\n7am to 10pm", "gym"))

    def test_json(self):
        recs = parse_json_objects({"venues":[{"venue_name":"Fernvale Square ActiveSG Gym","occupancy_percentage":28,"status":"open"}]})
        self.assertEqual(recs[0]["pct"], 28)

    def test_percentile(self):
        self.assertEqual(pctile([10,20,30,40], .5), 25)

if __name__ == "__main__":
    unittest.main()
