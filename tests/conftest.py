"""Shared pytest fixtures and configuration."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_json_data():
    """Sample JSON data for testing."""
    return {
        "user_id": "test-user-123",
        "timestamp": "2025-07-25 10:00:00.000000+00:00",
        "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
        "user_question": "How do I test this?",
        "llm_response": "You can use pytest for testing.",
        "sentiment": 1,
        "user_feedback": "helpful",
    }


@pytest.fixture
def mock_auth_provider():
    """Mock authentication provider for testing."""
    provider = Mock()
    provider.get_auth_token.return_value = "test-auth-token"
    provider.get_identity_id.return_value = "test-cluster-id"
    provider.get_credentials.return_value = ("test-auth-token", "test-cluster-id")
    return provider


@pytest.fixture
def sample_data_structure(temp_dir, sample_json_data):
    """Create a sample data directory structure for testing."""
    # Create feedback directory with sample files
    feedback_dir = temp_dir / "feedback"
    feedback_dir.mkdir()

    feedback_file1 = feedback_dir / "feedback1.json"
    feedback_file1.write_text('{"feedback": "test1"}')

    feedback_file2 = feedback_dir / "feedback2.json"
    feedback_file2.write_text('{"feedback": "test2"}')

    # Create transcripts directory with sample files
    transcripts_dir = temp_dir / "transcripts"
    transcripts_dir.mkdir()

    transcript_file = transcripts_dir / "conversation1.json"
    transcript_file.write_text('{"conversation": "test"}')

    # Create an invalid directory that should be ignored
    invalid_dir = temp_dir / "logs"
    invalid_dir.mkdir()

    invalid_file = invalid_dir / "invalid.json"
    invalid_file.write_text('{"invalid": "data"}')

    return {
        "data_dir": temp_dir,
        "feedback_files": [feedback_file1, feedback_file2],
        "transcript_files": [transcript_file],
        "invalid_files": [invalid_file],
    }
