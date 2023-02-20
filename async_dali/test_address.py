import unittest

from async_dali import DaliGearAddress, DaliGearGroupAddress, DaliGear, DaliGearGroup


class TestAddress(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.test_gear = DaliGear(None, DaliGearAddress(1))
        self.test_gear.groups = 1 << 1
        self.test_group = DaliGearGroup(None, DaliGearGroupAddress(1), self.test_gear)

    def test_gear_match(self):

        self.assertTrue(DaliGearAddress(1).matches_gear(self.test_gear)) 
        self.assertFalse(DaliGearAddress(2).matches_gear(self.test_gear)) 

    def test_gear_group_match(self):
        self.assertTrue(DaliGearGroupAddress(1).matches_gear(self.test_group)) 
        self.assertFalse(DaliGearGroupAddress(2).matches_gear(self.test_group)) 

    def test_group_also_matches_device(self):
        self.assertTrue(DaliGearGroupAddress(1).matches_gear(self.test_gear)) 
