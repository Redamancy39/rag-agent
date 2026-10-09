import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.chat import router
from app.api.auth import get_current_user


class QueryPreviewApiTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(router)
        self.client = TestClient(self.app)

    def test_both_routes_require_authentication(self):
        self.assertEqual(self.client.get('/chat/hotwords').status_code, 401)
        self.assertEqual(self.client.post('/chat/query-preview', json={'question': '菌落总树'}).status_code, 401)

    def test_reader_can_preview_without_model_jobs_or_database_access(self):
        self.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=2, is_admin=False)
        with patch('app.api.chat.RagService', side_effect=AssertionError('No retrieval')), patch('app.api.chat.chat_job_service.create_chat_job', side_effect=AssertionError('No jobs')):
            response = self.client.post('/chat/query-preview', json={'question': '菌落总树和大肠杆群'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['corrected_question'], '菌落总数和大肠杆群')
            self.assertTrue(response.json()['suggestions'])
            self.assertEqual(len(self.client.get('/chat/hotwords').json()['entries']), 48)
            self.assertEqual(self.client.post('/chat/query-preview', json={'question': '中'*4001}).status_code, 422)


if __name__ == '__main__': unittest.main()
