import unittest
import numpy as np
from psrtty.ui.cross_scope import scope_points,ScopeAfterglow

class Scope82Tests(unittest.TestCase):
    def test_thin_tuned_ellipse_and_detuned_widening(self):
        t=np.arange(4096)/48000
        for mark,space in [(2125,2295),(1585,1415)]:
            for tone in (mark,space):
                def ratio(freq):
                    xy=scope_points(.2*np.sin(2*np.pi*freq*t),48000,mark,space,45.45)
                    eigen=np.linalg.eigvalsh(np.cov(xy.T))
                    return np.sqrt(eigen[0]/eigen[1])
                tuned=ratio(tone)
                self.assertGreater(tuned,.01)
                self.assertLess(tuned,.07)
                self.assertGreater(ratio(tone+40),tuned*1.2)
    def test_afterglow_lasts_seven_tenths(self):
        a=ScopeAfterglow();a.accept(10.,(2125,2295,45.45),[(0,np.ones((5,2)))])
        self.assertEqual(len(a.visible(10.3)),1)
        self.assertAlmostEqual(a.visible(10.3)[0][1],1-.3/.7)
        self.assertEqual(len(a.visible(10.65)),1)
        self.assertEqual(a.visible(10.701),[])
