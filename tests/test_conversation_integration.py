"""
Integration tests for conversation system with coder.
"""

import unittest

from cecli.helpers.conversation import ConversationManager, MessageTag


class TestConversationIntegration(unittest.TestCase):
    """Test conversation system integration with coder."""

    def setUp(self):
        """Set up test environment."""
        # Reset conversation manager
        ConversationManager.reset()

    def test_conversation_manager_methods(self):
        """Test that conversation manager methods work correctly."""
        # Test adding a message
        message_dict = {"role": "user", "content": "Hello"}
        message = ConversationManager.add_message(
            message_dict=message_dict,
            tag=MessageTag.CUR,
        )

        self.assertIsNotNone(message)
        self.assertEqual(len(ConversationManager.get_messages()), 1)

        # Test getting messages as dict
        messages_dict = ConversationManager.get_messages_dict()
        self.assertEqual(len(messages_dict), 1)
        self.assertEqual(messages_dict[0]["role"], "user")
        self.assertEqual(messages_dict[0]["content"], "Hello")

        # Test clearing tag
        ConversationManager.clear_tag(MessageTag.CUR)
        self.assertEqual(len(ConversationManager.get_messages()), 0)

    def test_message_ordering_with_tags(self):
        """Test message ordering with different tags."""
        # Add messages with different tags (different default priorities)
        ConversationManager.add_message(
            message_dict={"role": "system", "content": "System"},
            tag=MessageTag.SYSTEM,  # Priority 0
        )
        ConversationManager.add_message(
            message_dict={"role": "user", "content": "User"},
            tag=MessageTag.CUR,  # Priority 200
        )
        ConversationManager.add_message(
            message_dict={"role": "assistant", "content": "Assistant"},
            tag=MessageTag.EXAMPLES,  # Priority 75
        )

        messages = ConversationManager.get_messages()

        # Check ordering: SYSTEM (0), EXAMPLES (75), CUR (200)
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0].message_dict["content"], "System")
        self.assertEqual(messages[1].message_dict["content"], "Assistant")
        self.assertEqual(messages[2].message_dict["content"], "User")

    def test_mark_for_delete_lifecycle(self):
        """Test mark_for_delete lifecycle."""
        # Add message with mark_for_delete
        ConversationManager.add_message(
            message_dict={"role": "user", "content": "Temp"},
            tag=MessageTag.CUR,
            mark_for_delete=2,  # Will expire after 2 decrements
        )

        self.assertEqual(len(ConversationManager.get_messages()), 1)

        # First decrement: mark_for_delete = 1 (not expired)
        ConversationManager.decrement_mark_for_delete()
        self.assertEqual(len(ConversationManager.get_messages()), 1)

        # Second decrement: mark_for_delete = 0 (not expired)
        ConversationManager.decrement_mark_for_delete()
        self.assertEqual(len(ConversationManager.get_messages()), 1)

        # Third decrement: mark_for_delete = -1 (expired, should be removed)
        ConversationManager.decrement_mark_for_delete()
        self.assertEqual(len(ConversationManager.get_messages()), 0)


if __name__ == "__main__":
    unittest.main()
