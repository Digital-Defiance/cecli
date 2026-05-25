"""EventIO accepts cecli kwargs such as coder_uuid."""

import unittest

from bright_vision_core.event_io import EventIO


class TestEventIOKwargs(unittest.TestCase):
    def test_tool_warning_accepts_coder_uuid(self):
        io = EventIO(yes=True)
        io.tool_warning("test warning", coder_uuid="uuid-1")
        self.assertEqual(io.events[-1]["type"], "tool_warning")
        self.assertIn("test warning", io.events[-1]["text"])


if __name__ == "__main__":
    unittest.main()
