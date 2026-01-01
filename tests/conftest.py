import pytest
from unittest.mock import MagicMock

from aider.models import Model


# Model Fixtures
@pytest.fixture
def gpt35_model():
    """Common GPT-3.5-turbo model fixture used across test files."""
    return Model("gpt-3.5-turbo")


@pytest.fixture
def gpt4_model():
    """Common GPT-4 model fixture for tests requiring GPT-4."""
    return Model("gpt-4")


# Mock Streaming Fixtures
@pytest.fixture
def mock_delta_class():
    """
    Factory fixture for MockDelta class.

    Returns a class that can be instantiated to create mock delta objects
    for streaming responses. Used extensively in test_reasoning.py and other
    streaming-related tests.

    Example:
        def test_something(mock_delta_class):
            MockDelta = mock_delta_class
            delta = MockDelta(content="test content")
    """
    class MockDelta:
        def __init__(self, content=None, reasoning_content=None, reasoning=None):
            if content is not None:
                self.content = content
            if reasoning_content is not None:
                self.reasoning_content = reasoning_content
            if reasoning is not None:
                self.reasoning = reasoning

    return MockDelta


@pytest.fixture
def mock_streaming_chunk_class(mock_delta_class):
    """
    Factory fixture for MockStreamingChunk class.

    Returns a class that can be instantiated to create mock streaming chunk objects.
    Depends on mock_delta_class fixture.

    Example:
        def test_something(mock_streaming_chunk_class):
            MockStreamingChunk = mock_streaming_chunk_class
            chunk = MockStreamingChunk(content="test", finish_reason="stop")
    """
    class MockStreamingChunk:
        def __init__(self, content=None, reasoning_content=None, reasoning=None, finish_reason=None):
            self.choices = [MagicMock()]
            self.choices[0].delta = mock_delta_class(content, reasoning_content, reasoning)
            self.choices[0].finish_reason = finish_reason
            self._hidden_params = {}

    return MockStreamingChunk
