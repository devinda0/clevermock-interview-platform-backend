import unittest
import asyncio
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app

class TestReviewStatsEndpoint(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch("app.api.v1.endpoints.review.Review")
    def test_get_review_stats_success(self, mock_review_cls):
        # Mock aggregation results
        mock_results = [
            {
                "overview": [
                    {
                        "average_rating": 4.5,
                        "total_reviews": 10
                    }
                ],
                "distribution": [
                    {"_id": 5, "count": 6},
                    {"_id": 4, "count": 3},
                    {"_id": 3, "count": 1}
                ]
            }
        ]
        
        # Setup mock cursor
        mock_cursor = MagicMock()
        mock_to_list_future = asyncio.Future()
        mock_to_list_future.set_result(mock_results)
        mock_cursor.to_list.return_value = mock_to_list_future
        
        mock_review_cls.aggregate.return_value = mock_cursor

        response = self.client.get("/api/v1/review/stats")
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["average_rating"], 4.5)
        self.assertEqual(data["total_reviews"], 10)
        self.assertEqual(data["rating_distribution"]["5"], 6)
        self.assertEqual(data["rating_distribution"]["4"], 3)
        self.assertEqual(data["rating_distribution"]["3"], 1)
        self.assertEqual(data["rating_distribution"]["1"], 0)

    @patch("app.api.v1.endpoints.review.Review")
    def test_get_review_stats_empty(self, mock_review_cls):
        # Mock empty aggregation results
        mock_results = [
            {
                "overview": [],
                "distribution": []
            }
        ]
        
        mock_cursor = MagicMock()
        mock_to_list_future = asyncio.Future()
        mock_to_list_future.set_result(mock_results)
        mock_cursor.to_list.return_value = mock_to_list_future
        
        mock_review_cls.aggregate.return_value = mock_cursor

        response = self.client.get("/api/v1/review/stats")
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["average_rating"], 0.0)
        self.assertEqual(data["total_reviews"], 0)
        self.assertEqual(data["rating_distribution"]["5"], 0)

if __name__ == "__main__":
    unittest.main()
