import unittest

from matching import match, normalize

NAMES = ["Study", "Living Room", "Living Room Amp+Kitchen", "Game Room (4)", "Garage"]


class NormalizeTest(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize("Game Room (4)"), "gameroom4")
        self.assertEqual(normalize("  GARAGE "), "garage")
        self.assertEqual(normalize("Büro"), "büro")


class MatchTest(unittest.TestCase):
    def test_case_does_not_matter(self):
        for query in ["garage", "GARAGE", "Garage"]:
            with self.subTest(query=query):
                self.assertEqual(match(query, NAMES).matches, ["Garage"])

    def test_spaces_and_punctuation_do_not_matter(self):
        self.assertEqual(match("gameroom 4", NAMES).matches, ["Game Room (4)"])

    def test_exact_match_wins_over_longer_names(self):
        result = match("living room", NAMES)
        self.assertEqual(result.matches, ["Living Room"])
        self.assertEqual(result.suggestions, [])

    def test_several_matches(self):
        result = match("game room", ["Gameroom", "Game Room", "Study"])
        self.assertEqual(result.matches, ["Game Room", "Gameroom"])

    def test_duplicates_are_listed_once(self):
        self.assertEqual(match("study", ["Study", "Study"]).matches, ["Study"])

    def test_typo_gives_suggestion(self):
        result = match("Garge", NAMES)
        self.assertEqual(result.matches, [])
        self.assertEqual(result.suggestions, ["Garage"])

    def test_part_of_a_name_gives_suggestion(self):
        self.assertEqual(match("kitchen", NAMES).suggestions, ["Living Room Amp+Kitchen"])

    def test_substring_suggestions_come_first_and_are_limited(self):
        names = ["Room 4", "Room 2", "Rom", "Room 3", "Room 1"]
        self.assertEqual(match("room", names).suggestions, ["Room 1", "Room 2", "Room 3"])

    def test_nothing_found(self):
        result = match("xyz", NAMES)
        self.assertEqual((result.matches, result.suggestions), ([], []))

    def test_empty_query(self):
        result = match("  ()  ", NAMES)
        self.assertEqual((result.matches, result.suggestions), ([], []))


if __name__ == "__main__":
    unittest.main()
