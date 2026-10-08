"""Bound fin-edge deviations while preserving source stations and all slats."""
import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'blender'))
from arts_landmark import fin_stations,intervals,outline,roof_level,FIN_PITCH,FIN_WIDTH


class FinSamplingTests(unittest.TestCase):
    def test_all_existing_fin_edges_are_bounded(self):
        boundary=outline();saved=0;tested=0
        first=math.ceil(min(p[0] for p in boundary)/FIN_PITCH)
        last=math.floor(max(p[0] for p in boundary)/FIN_PITCH)
        for index in range(first,last+1):
            u=index*FIN_PITCH
            for start,end in intervals(boundary,u):
                n=max(2,math.ceil((end-start)/.030));original=fin_stations(u,start,end,n)
                selected=fin_stations(u,start,end,n,.005)
                self.assertEqual(original,[start+(end-start)*i/n for i in range(n+1)])
                self.assertEqual(selected[0],original[0]);self.assertEqual(selected[-1],original[-1])
                self.assertTrue(set(selected)<=set(original));saved+=len(original)-len(selected);tested+=1
                for a,b in zip(selected,selected[1:]):
                    for v in original:
                        if not a<=v<=b:continue
                        t=(v-a)/(b-a)
                        for side in [-1,1]:
                            x=u+side*FIN_WIDTH/2
                            error=abs(roof_level(x,v)-(roof_level(x,a)*(1-t)+roof_level(x,b)*t))*100
                            self.assertLessEqual(error,.005+1e-10)
        self.assertEqual(tested,62);self.assertGreater(saved,0)

    def test_invalid_tolerances_are_rejected(self):
        for value in [-1,0,float('nan'),float('inf')]:
            with self.assertRaises(ValueError):fin_stations(0,0,1,10,value)


if __name__=='__main__':unittest.main()
