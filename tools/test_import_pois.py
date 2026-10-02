import unittest

from import_pois import LABELS, code, coordinates, key, make_resolver, unit_aliases


class MappingTests(unittest.TestCase):
    def test_user_labels(self):
        self.assertEqual(len(set(LABELS)), 24)
        self.assertEqual([LABELS[i] for i in (13,20,21)], ['quận 2','quận 9','thủ đức'])

    def test_unicode_and_raw_short_aliases(self):
        self.assertEqual(key('TP Thủ Đức'), 'tp thủ đức')
        self.assertIn('6', unit_aliases('Quận 6','district'))
        self.assertNotIn('thủ đức', unit_aliases('Quận 9','district'))

    def test_parent_scoped_and_ambiguous_matches(self):
        units = {('legacy_2025','ward','1'): {'id':1,'name':'Phường 1','parent':10},
                 ('legacy_2025','ward','2'): {'id':2,'name':'Phường 1','parent':20},
                 ('from_2025','ward','1'): {'id':3,'name':'Phường 1','parent':30}}
        resolve = make_resolver(units)
        self.assertEqual(resolve('legacy_2025','ward',10,'1'), (1,'matched'))
        self.assertEqual(resolve('legacy_2025','ward',None,'1'), (None,'parent_unresolved'))
        self.assertEqual(resolve('from_2025','ward',10,'1'), (None,'unmatched'))
        units[('legacy_2025','ward','3')] = {'id':4,'name':'Phường 1','parent':10}
        self.assertEqual(make_resolver(units)('legacy_2025','ward',10,'1'), (None,'ambiguous'))

    def test_coordinates(self):
        for lat,lon in [('NaN','106'), ('10','inf'), ('91','106'), ('10','181'), ('','106')]:
            with self.assertRaises(ValueError):
                coordinates(dict(poi_id='test',latitude=lat,longitude=lon))
        self.assertEqual(coordinates(dict(latitude='',longitude='')), (None,None))
        self.assertEqual(coordinates(dict(latitude='10.5',longitude='106.7')), (10.5,106.7))

    def test_codes(self):
        self.assertEqual(code('001.0'), '1')
        self.assertIsNone(code(''))
        with self.assertRaises(ValueError):
            code('1.5')


if __name__ == '__main__':
    unittest.main()
