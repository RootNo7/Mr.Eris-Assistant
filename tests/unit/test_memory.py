import os
import json
import pytest
from backend.ai.memory.buffer import ConversationBuffer

@pytest.fixture
def temp_storage(tmp_path):
    # Pytest provides a temporary directory path for safe file testing
    return str(tmp_path / "test_session.json")

def test_conversation_buffer_initialization():
    buffer = ConversationBuffer(max_history=5)
    assert len(buffer.get_history()) == 0
    assert buffer.max_history == 5

def test_conversation_buffer_appends_and_trims_messages():
    buffer = ConversationBuffer(max_history=2)
    buffer.add_user_message("Message 1")
    buffer.add_assistant_message("Message 2")
    buffer.add_user_message("Message 3") 

    history = buffer.get_history()
    assert len(history) == 2
    assert history[0]["text"] == "Message 2"
    assert history[1]["text"] == "Message 3"

def test_conversation_buffer_saves_and_loads(temp_storage):
    # 1. Create a buffer with persist_across_sessions=True, add a message, and save it
    buffer1 = ConversationBuffer(storage_path=temp_storage, persist_across_sessions=True)
    buffer1.add_user_message("Remember this secret password: 1234")
    
    assert os.path.exists(temp_storage)

    # 2. Initialize a BRAND NEW buffer pointing to the same file (with persistence enabled)
    buffer2 = ConversationBuffer(storage_path=temp_storage, persist_across_sessions=True)
    
    # 3. Verify the second buffer automatically loaded the history
    loaded_history = buffer2.get_history()
    assert len(loaded_history) == 1
    assert loaded_history[0]["role"] == "user"
    assert loaded_history[0]["text"] == "Remember this secret password: 1234"

def test_conversation_buffer_no_stale_history_on_new_session(temp_storage):
    """Default (persist_across_sessions=False) must start empty even if session.json exists."""
    # 1. Simulate a previous session that wrote to disk
    buffer_old = ConversationBuffer(storage_path=temp_storage, persist_across_sessions=True)
    buffer_old.add_user_message("Old session message")
    assert os.path.exists(temp_storage)

    # 2. New session — default persist_across_sessions=False — must NOT load old history
    buffer_new = ConversationBuffer(storage_path=temp_storage)
    assert len(buffer_new.get_history()) == 0, (
        "ConversationBuffer must start empty on a new session (persist_across_sessions=False)."
    )

def test_conversation_buffer_clear(temp_storage):
    buffer = ConversationBuffer(storage_path=temp_storage)
    buffer.add_user_message("Hello")
    buffer.clear()
    
    assert len(buffer.get_history()) == 0
    
    # Verify the file on disk was also cleared
    with open(temp_storage, 'r') as f:
        data = json.load(f)
        assert len(data) == 0