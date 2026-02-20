import unittest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app
from app.api.deps import get_current_user
from app.models.user import User

class TestReviewEndpoint(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.user_id = uuid4()
        self.mock_user = MagicMock(spec=User)
        self.mock_user.id = self.user_id
        
        # Override get_current_user dependency
        app.dependency_overrides[get_current_user] = lambda: self.mock_user

    def tearDown(self):
        app.dependency_overrides = {}

    @patch("app.api.v1.endpoints.review.Review")  # Patch the class itself
    @patch("app.api.v1.endpoints.review.Conversation.get", new_callable=AsyncMock)
    def test_create_review_success(self, mock_get_conversation, mock_review_cls):
        conversation_id = uuid4()
        
        # Mock Conversation
        mock_conversation = MagicMock()
        mock_conversation.user_id = str(self.user_id)
        mock_conversation.transcript = [{"role": "user", "content": "Hello"}]
        mock_get_conversation.return_value = mock_conversation
        
        # Mock Review.find_one (static method on class)
        # Review.find_one returns a FindOne object which is awaited.
        # So Review.find_one(...) should return an awaitable that resolves to None.
        mock_find_one_future = asyncio.Future()
        mock_find_one_future.set_result(None)
        mock_review_cls.find_one.return_value = mock_find_one_future

        # Mock Review instance and insert method
        mock_review_instance = MagicMock()
        mock_review_instance.id = uuid4()
        mock_review_instance.conversation_id = conversation_id
        mock_review_instance.user_id = str(self.user_id)
        mock_review_instance.overall_rating = 5
        mock_review_instance.ai_quality_rating = 4
        mock_review_instance.difficulty_rating = 3
        mock_review_instance.feedback_text = "Great interview!"
        
        from datetime import datetime
        mock_review_instance.created_at = datetime.utcnow()

        mock_insert_future = asyncio.Future()
        mock_insert_future.set_result(None)
        mock_review_instance.insert.return_value = mock_insert_future
        
        # Make the class constructor return the mock instance
        mock_review_cls.return_value = mock_review_instance

        # Payload
        payload = {
            "overall_rating": 5,
            "ai_quality_rating": 4,
            "difficulty_rating": 3,
            "feedback_text": "Great interview!",
            "would_recommend": True
        }

        response = self.client.post(f"/api/v1/review/{conversation_id}", json=payload)
        
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["overall_rating"], 5)
        self.assertEqual(data["conversation_id"], str(conversation_id))

    @patch("app.api.v1.endpoints.review.Review")
    @patch("app.api.v1.endpoints.review.Conversation.get", new_callable=AsyncMock)
    def test_create_review_no_transcript(self, mock_get_conversation, mock_review_cls):
        conversation_id = uuid4()
        
        # Mock Conversation with empty transcript
        mock_conversation = MagicMock()
        mock_conversation.user_id = str(self.user_id)
        mock_conversation.transcript = [] # Empty transcript
        mock_get_conversation.return_value = mock_conversation

        payload = {
            "overall_rating": 5
        }

        response = self.client.post(f"/api/v1/review/{conversation_id}", json=payload)
        
        self.assertEqual(response.status_code, 400)
        self.assertIn("transcript", response.json()["detail"])

    @patch("app.api.v1.endpoints.review.Review")
    @patch("app.api.v1.endpoints.review.Conversation.get", new_callable=AsyncMock)
    def test_create_review_already_exists(self, mock_get_conversation, mock_review_cls):
        conversation_id = uuid4()
        
        # Mock Conversation
        mock_conversation = MagicMock()
        mock_conversation.user_id = str(self.user_id)
        mock_conversation.transcript = [{"role": "user", "content": "Hello"}]
        mock_get_conversation.return_value = mock_conversation

        # Mock Review.find_one to return an existing review
        mock_existing_review = MagicMock()
        mock_find_one_future = asyncio.Future()
        mock_find_one_future.set_result(mock_existing_review)
        mock_review_cls.find_one.return_value = mock_find_one_future

        payload = {
            "overall_rating": 5
        }

        response = self.client.post(f"/api/v1/review/{conversation_id}", json=payload)
        
        self.assertEqual(response.status_code, 409)
        self.assertIn("already exists", response.json()["detail"])

    @patch("app.api.v1.endpoints.review.Review")
    def test_get_review_success(self, mock_review_cls):
        conversation_id = uuid4()
        
        # Mock Review
        mock_review = MagicMock()
        mock_review.id = uuid4()
        mock_review.conversation_id = conversation_id
        mock_review.user_id = str(self.user_id)
        mock_review.overall_rating = 5
        mock_review.ai_quality_rating = 4
        mock_review.difficulty_rating = 3
        mock_review.feedback_text = "Great!"
        from datetime import datetime
        mock_review.created_at = datetime.utcnow()

        # Mock find_one to return the review
        mock_find_one_future = asyncio.Future()
        mock_find_one_future.set_result(mock_review)
        mock_review_cls.find_one.return_value = mock_find_one_future

        response = self.client.get(f"/api/v1/review/{conversation_id}")
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["overall_rating"], 5)
        self.assertEqual(data["conversation_id"], str(conversation_id))

    @patch("app.api.v1.endpoints.review.Review")
    def test_get_review_not_found(self, mock_review_cls):
        conversation_id = uuid4()
        
        # Mock find_one to return None
        mock_find_one_future = asyncio.Future()
        mock_find_one_future.set_result(None)
        mock_review_cls.find_one.return_value = mock_find_one_future

        response = self.client.get(f"/api/v1/review/{conversation_id}")
        
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["detail"].lower())

    @patch("app.api.v1.endpoints.review.Review")
    def test_get_review_forbidden(self, mock_review_cls):
        conversation_id = uuid4()
        
        # Mock Review belonging to another user
        mock_review = MagicMock()
        mock_review.user_id = "other-user-id"
        
        # Mock find_one to return the review
        mock_find_one_future = asyncio.Future()
        mock_find_one_future.set_result(mock_review)
        mock_review_cls.find_one.return_value = mock_find_one_future

        response = self.client.get(f"/api/v1/review/{conversation_id}")
        
        self.assertEqual(response.status_code, 403)
        self.assertIn("permission", response.json()["detail"].lower())

if __name__ == "__main__":
    unittest.main()
