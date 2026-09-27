import unittest
from types import SimpleNamespace
from psrtty.jarl_score import locate, calculate


def q(call, band='20M'):
    return (SimpleNamespace(call=call, band=band), {'xqso': False})


class ScoreTest(unittest.TestCase):
    def test_mainland_areas_and_uncertainty(self):
        self.assertEqual(locate('JA1RL/3')['multiplier'],'JA3')
        self.assertEqual(locate('8J20AAA')['multiplier'],'JA0')
        self.assertEqual(locate('K1AAA')['multiplier'],'W1')
        self.assertIsNone(locate('JD1ABC'))
        self.assertIsNone(locate('JA1AAA/JD1'))
        self.assertEqual(locate('JA1AAA/MM')['entity'],'MM')

    def test_score_duplicate_mult_and_mm(self):
        entries=[q('JA1AAA'),q('JA1AAA'),q('JA1BBB'),q('HL1AAA'),q('JA1CCC/MM')]
        result=calculate(entries,'AS')
        self.assertEqual(result['points'],8)
        self.assertEqual(result['multipliers'],2)
        self.assertEqual(result['total'],16)
        self.assertEqual(result['details'][1][2],0)

    def test_unknown_requires_manual_location(self):
        result=calculate([q('JD1AAA')],'AS')
        self.assertEqual(result['unknown'],['JD1AAA'])
        chosen={'JD1AAA':{'entity':'JD/o','continent':'AS','multiplier':'JD/o'}}
        # Manual entity IDs may contain a slash for Ogasawara/Minami Torishima.
        self.assertEqual(calculate([q('JD1AAA')],'AS',chosen)['total'],2)

    def test_manual_area_multiplier_is_distinct_from_entity(self):
        chosen={'VK/JA1YRL':{'entity':'VK','continent':'OC','multiplier':'VK0'}}
        result=calculate([q('VK/JA1YRL')],'AS',chosen)
        self.assertEqual(result['points'],3)
        self.assertEqual(result['details'][0][3],'VK0')
        with self.assertRaises(ValueError):
            calculate([q('JD1AAA')],'AS',{'JD1AAA':{'entity':'JD/o','continent':'AS','multiplier':''}})


if __name__=='__main__':unittest.main()
