import unittest

from text_stats import average_word_length


class AverageWordLengthTest(unittest.TestCase):
    def test_calculates_average_for_two_words(self):
        self.assertEqual(average_word_length("hi world"), 3.5)

    def test_ignores_extra_whitespace(self):
        self.assertAlmostEqual(average_word_length("  a   bee  ccc "), 7 / 3)

    def test_empty_text_returns_zero(self):
        self.assertEqual(average_word_length("   "), 0.0)


if __name__ == "__main__":
    unittest.main()
