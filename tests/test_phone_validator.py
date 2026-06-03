"""Pruebas de validación telefónica."""

import unittest

from app.utils.phone_validator import prefix_menu_options, split_e164


class PhoneValidatorTests(unittest.TestCase):
    def test_split_e164_colombia(self):
        prefix, local = split_e164("+573001112233")
        self.assertEqual(prefix, "+57")
        self.assertEqual(local, "3001112233")

    def test_split_e164_malta(self):
        prefix, local = split_e164("+35699155990")
        self.assertEqual(prefix, "+356")
        self.assertEqual(local, "99155990")

    def test_prefix_menu_includes_detected_prefix(self):
        labels, default = prefix_menu_options("+35699155990")
        self.assertTrue(default.startswith("+356"))
        self.assertIn(default, labels)


if __name__ == "__main__":
    unittest.main()
