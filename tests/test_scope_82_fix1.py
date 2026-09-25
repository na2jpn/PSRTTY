import unittest
import numpy as np
from psrtty.ui.cross_scope import ScopeAfterglow

class TwoTraceTests(unittest.TestCase):
    def test_two_per_axis_cap_dim_previous_and_no_duplicate(self):
        a=ScopeAfterglow();tones=(2125,2295,45.45)
        for stamp in (1.,1.1,1.2):
            a.accept(stamp,tones,[(0,np.full((5,2),stamp)),(1,np.full((5,2),-stamp))])
        shown=a.visible(1.2)
        self.assertEqual(len(shown),4)
        self.assertEqual([s for s,t in a.latest[0]],[1.1,1.2])
        self.assertAlmostEqual(shown[0][1],.45*(1-.1/.7))
        self.assertAlmostEqual(shown[1][1],1.)
        a.accept(1.2,tones,[(0,np.zeros((5,2)))])
        self.assertEqual(len(a.latest[0]),2)
        self.assertEqual(len(a.visible(1.81)),2)
        self.assertEqual(a.visible(1.901),[])
    def test_tuning_clear_and_axis_independence(self):
        a=ScopeAfterglow();t=(2125,2295,45.45);trace=np.ones((5,2))
        a.accept(1,t,[(0,trace)]);a.accept(1.1,t,[(1,trace)])
        a.accept(1.2,t,[(0,trace)]);self.assertEqual(len(a.visible(1.2)),3)
        a.accept(1.3,(1500,1670,45.45),[(1,trace)])
        self.assertEqual(len(a.visible(1.3)),1)
