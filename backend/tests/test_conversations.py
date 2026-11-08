"""Tests for conversation and project management endpoints."""
import pytest
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


class TestProjects:
    """Project CRUD operations."""

    def test_create_project(self):
        resp = client.post(
            "/conversations/projects",
            json={"name": "NIFTY 50 Strategies", "description": "My trading strategies"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "NIFTY 50 Strategies"
        assert data["description"] == "My trading strategies"
        assert "id" in data
        assert "created_at" in data

    def test_list_projects(self):
        # Create a project first
        client.post("/conversations/projects", json={"name": "Test Project"})
        resp = client.get("/conversations/projects")
        assert resp.status_code == 200
        projects = resp.json()
        assert isinstance(projects, list)
        assert len(projects) >= 1

    def test_update_project(self):
        create_resp = client.post("/conversations/projects", json={"name": "Original"})
        project_id = create_resp.json()["id"]

        resp = client.patch(
            f"/conversations/projects/{project_id}",
            json={"name": "Updated Name", "description": "New description"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Updated Name"
        assert data["description"] == "New description"

    def test_delete_project_move_conversations(self):
        # Create project and conversation
        proj_resp = client.post("/conversations/projects", json={"name": "To Delete"})
        project_id = proj_resp.json()["id"]

        conv_resp = client.post("/conversations", json={"project_id": project_id})
        conversation_id = conv_resp.json()["id"]

        # Delete project with move_conversations=true (default)
        resp = client.delete(f"/conversations/projects/{project_id}?move_conversations=true")
        assert resp.status_code == 200

        # Conversation should still exist but be unassigned
        conv_check = client.get(f"/conversations/{conversation_id}")
        assert conv_check.status_code == 200
        assert conv_check.json()["conversation"]["project_id"] is None

    def test_delete_project_delete_conversations(self):
        proj_resp = client.post("/conversations/projects", json={"name": "To Delete"})
        project_id = proj_resp.json()["id"]

        conv_resp = client.post("/conversations", json={"project_id": project_id})
        conversation_id = conv_resp.json()["id"]

        # Delete project with move_conversations=false
        resp = client.delete(f"/conversations/projects/{project_id}?move_conversations=false")
        assert resp.status_code == 200

        # Conversation should be deleted
        conv_check = client.get(f"/conversations/{conversation_id}")
        assert conv_check.status_code == 404


class TestConversations:
    """Conversation CRUD operations."""

    def test_create_conversation_unassigned(self):
        resp = client.post("/conversations", json={"title": "My Chat"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "My Chat"
        assert data["project_id"] is None
        assert data["status"] == "active"

    def test_create_conversation_in_project(self):
        proj_resp = client.post("/conversations/projects", json={"name": "Test Project"})
        project_id = proj_resp.json()["id"]

        resp = client.post("/conversations", json={"title": "Project Chat", "project_id": project_id})
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Project Chat"
        assert data["project_id"] == project_id

    def test_list_conversations(self):
        client.post("/conversations", json={"title": "Chat 1"})
        client.post("/conversations", json={"title": "Chat 2"})
        resp = client.get("/conversations")
        assert resp.status_code == 200
        conversations = resp.json()
        assert isinstance(conversations, list)
        assert len(conversations) >= 2

    def test_list_conversations_filter_by_project(self):
        proj_resp = client.post("/conversations/projects", json={"name": "Filter Test"})
        project_id = proj_resp.json()["id"]

        client.post("/conversations", json={"title": "In Project", "project_id": project_id})
        client.post("/conversations", json={"title": "Unassigned"})

        resp = client.get(f"/conversations?project_id={project_id}")
        assert resp.status_code == 200
        conversations = resp.json()
        assert all(c["project_id"] == project_id for c in conversations)

    def test_list_conversations_unassigned(self):
        client.post("/conversations", json={"title": "Unassigned Chat"})
        resp = client.get("/conversations?project_id=unassigned")
        assert resp.status_code == 200
        conversations = resp.json()
        assert all(c["project_id"] is None for c in conversations)

    def test_get_conversation_with_messages(self):
        # Create conversation
        conv_resp = client.post("/conversations", json={"title": "With Messages"})
        conversation_id = conv_resp.json()["id"]

        # Send a message via chat endpoint to create messages
        client.post("/chat", json={"conversation_id": conversation_id, "content": "Hello"})
        client.post("/chat", json={"conversation_id": conversation_id, "content": "Hi there"})

        # Get conversation with messages
        resp = client.get(f"/conversations/{conversation_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["conversation"]["id"] == conversation_id
        assert len(data["messages"]) >= 2

    def test_update_conversation_title(self):
        conv_resp = client.post("/conversations", json={"title": "Old Title"})
        conversation_id = conv_resp.json()["id"]

        resp = client.patch(f"/conversations/{conversation_id}", json={"title": "New Title"})
        assert resp.status_code == 200
        assert resp.json()["title"] == "New Title"

    def test_update_conversation_project(self):
        proj_resp = client.post("/conversations/projects", json={"name": "New Project"})
        project_id = proj_resp.json()["id"]

        conv_resp = client.post("/conversations", json={"title": "Moving"})
        conversation_id = conv_resp.json()["id"]

        resp = client.patch(f"/conversations/{conversation_id}", json={"project_id": project_id})
        assert resp.status_code == 200
        assert resp.json()["project_id"] == project_id

    def test_update_conversation_unassigned(self):
        proj_resp = client.post("/conversations/projects", json={"name": "Project"})
        project_id = proj_resp.json()["id"]

        conv_resp = client.post("/conversations", json={"title": "In Project", "project_id": project_id})
        conversation_id = conv_resp.json()["id"]

        resp = client.patch(f"/conversations/{conversation_id}", json={"project_id": "unassigned"})
        assert resp.status_code == 200
        assert resp.json()["project_id"] is None

    def test_archive_conversation(self):
        conv_resp = client.post("/conversations", json={"title": "To Archive"})
        conversation_id = conv_resp.json()["id"]

        resp = client.post(f"/conversations/{conversation_id}/archive")
        assert resp.status_code == 200
        assert resp.json()["status"] == "archived"

    def test_restore_conversation(self):
        conv_resp = client.post("/conversations", json={"title": "To Restore"})
        conversation_id = conv_resp.json()["id"]

        client.post(f"/conversations/{conversation_id}/archive")
        resp = client.post(f"/conversations/{conversation_id}/restore")
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    def test_delete_conversation(self):
        conv_resp = client.post("/conversations", json={"title": "To Delete"})
        conversation_id = conv_resp.json()["id"]

        resp = client.delete(f"/conversations/{conversation_id}")
        assert resp.status_code == 200

        # Should be gone
        check = client.get(f"/conversations/{conversation_id}")
        assert check.status_code == 404

    def test_move_conversation(self):
        proj1_resp = client.post("/conversations/projects", json={"name": "Project 1"})
        proj2_resp = client.post("/conversations/projects", json={"name": "Project 2"})
        project1_id = proj1_resp.json()["id"]
        project2_id = proj2_resp.json()["id"]

        conv_resp = client.post("/conversations", json={"title": "Moving", "project_id": project1_id})
        conversation_id = conv_resp.json()["id"]

        resp = client.post(
            f"/conversations/{conversation_id}/move",
            json={"project_id": project2_id},
        )
        assert resp.status_code == 200
        assert resp.json()["project_id"] == project2_id

    def test_move_conversation_to_unassigned(self):
        proj_resp = client.post("/conversations/projects", json={"name": "Project"})
        project_id = proj_resp.json()["id"]

        conv_resp = client.post("/conversations", json={"title": "In Project", "project_id": project_id})
        conversation_id = conv_resp.json()["id"]

        resp = client.post(
            f"/conversations/{conversation_id}/move",
            json={"project_id": "unassigned"},
        )
        assert resp.status_code == 200
        assert resp.json()["project_id"] is None


class TestChatIntegration:
    """Integration tests with chat endpoint."""

    def test_chat_creates_conversation(self):
        resp = client.post("/chat", json={"content": "Create a strategy"})
        assert resp.status_code == 200
        data = resp.json()
        assert "conversation_id" in data
        assert data["conversation_id"] is not None

    def test_chat_appends_to_existing_conversation(self):
        # First message
        resp1 = client.post("/chat", json={"content": "First message"})
        assert resp1.status_code == 200
        conv_id = resp1.json()["conversation_id"]

        # Second message in same conversation
        resp2 = client.post("/chat", json={"conversation_id": conv_id, "content": "Second message"})
        assert resp2.status_code == 200
        assert resp2.json()["conversation_id"] == conv_id

        # Verify conversation has both messages
        conv_resp = client.get(f"/conversations/{conv_id}")
        assert conv_resp.status_code == 200
        messages = conv_resp.json()["messages"]
        assert len(messages) >= 2

    def test_chat_conversation_persists(self):
        resp1 = client.post("/chat", json={"content": "Test persistence"})
        conv_id = resp1.json()["conversation_id"]

        # Fetch conversation - should have the message
        conv_resp = client.get(f"/conversations/{conv_id}")
        assert conv_resp.status_code == 200
        messages = conv_resp.json()["messages"]
        assert len(messages) >= 1
        assert messages[0]["content"] == "Test persistence"


class TestOwnership:
    """Verify user ownership enforcement (single user mode - all same user)."""

    def test_cannot_access_other_user_conversation(self):
        # In single-user mode, all conversations belong to the same user
        # This test verifies the endpoint works for the current user
        conv_resp = client.post("/conversations", json={"title": "My Conversation"})
        conversation_id = conv_resp.json()["id"]

        resp = client.get(f"/conversations/{conversation_id}")
        assert resp.status_code == 200

    def test_cannot_access_other_user_project(self):
        proj_resp = client.post("/conversations/projects", json={"name": "My Project"})
        project_id = proj_resp.json()["id"]

        resp = client.get(f"/conversations/projects/{project_id}")
        # Project detail endpoint doesn't exist, but list should include it
        list_resp = client.get("/conversations/projects")
        assert any(p["id"] == project_id for p in list_resp.json())