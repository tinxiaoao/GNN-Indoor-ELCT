import unittest

from experiments.evaluate_topology import typed_connectivity


class TopologyMatchingDefinitionTests(unittest.TestCase):
    def setUp(self):
        self.rooms = [{"RoomID": 1}, {"RoomID": 2}]
        self.edges = [{"RoomA": 1, "RoomB": 2, "ConnectionType": "door", "Count": 1, "segments": [(10, 2)]}]

    def test_count_and_dimensions_are_separate_from_typed_connectivity(self):
        candidate = [{"RoomA": 1, "RoomB": 2, "ConnectionType": "door", "Count": 2, "segments": [(6, 2), (5, 3)]}]
        self.assertTrue(all(typed_connectivity(self.rooms, self.rooms, self.edges, candidate).values()))

    def test_same_adjacency_with_different_interface_type_does_not_match(self):
        candidate = [dict(self.edges[0], ConnectionType="window")]
        self.assertFalse(typed_connectivity(self.rooms, self.rooms, self.edges, candidate)["typed_room_connectivity_equal"])

    def test_equal_room_count_with_an_unmatched_room_does_not_match(self):
        candidate_rooms = [{"RoomID": 1}, {"RoomID": "unmatched_candidate:3"}]
        result = typed_connectivity(self.rooms, candidate_rooms, self.edges, self.edges)
        self.assertTrue(result["room_count_equal"])
        self.assertFalse(result["spatially_matched_room_set_equal"])


if __name__ == "__main__":
    unittest.main()
