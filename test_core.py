import unittest

from app.core import make_greeting


class GreetingTests(unittest.TestCase):
    def test_empty_name(self):
        self.assertEqual(make_greeting("  "), "Bonjour !")

    def test_name_is_trimmed_and_spaces_are_normalized(self):
        self.assertEqual(make_greeting("  Ada   Lovelace "), "Bonjour, Ada Lovelace !")


if __name__ == "__main__":
    unittest.main()
