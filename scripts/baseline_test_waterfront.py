"""Compare the waterfront source arrays with preserved P1 inputs."""
import unittest
from test_waterfront import ROOT
from baseline_inputs import baseline_input

class WaterfrontTests(unittest.TestCase):
    def test_sources_unchanged(self):
        baseline=baseline_input('urban-structure/baseline-p1')
        for filename in ['geography.json','terrain.json']:
            self.assertEqual((ROOT/'public/data'/filename).read_bytes(),(baseline/'public/data'/filename).read_bytes())
