import frappe
from frappe.tests import IntegrationTestCase
from unittest.mock import patch
import requests
from frappe_n8n.n8n.doctype.playbook_execution.playbook_execution import trigger_execution, resume_execution

class TestN8nPlaybookExecution(IntegrationTestCase):
    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.requests.post")
    def test_trigger_execution_success(self, mock_post):
        mock_post.return_value.raise_for_status.return_value = None
        
        trigger_execution("http://example.com", {"data": "test"})
        
        self.assertEqual(mock_post.call_count, 1)
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "http://example.com")
        self.assertEqual(kwargs["headers"]["content-type"], "application/cloudevents+json")
        self.assertEqual(kwargs["timeout"], 10)
        self.assertIn(b'"data": {"data": "test"}', kwargs["data"])
        self.assertIn(b'"type": "playbook.execution.triggered"', kwargs["data"])
        
    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.requests.post")
    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.frappe.log_error")
    def test_trigger_execution_failure(self, mock_log_error, mock_post):
        mock_post.side_effect = requests.exceptions.RequestException("Connection error")
        
        with self.assertRaises(requests.exceptions.RequestException):
            trigger_execution("http://example.com", {"data": "test"})
            
        mock_log_error.assert_called_once()
        
    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.requests.post")
    def test_resume_execution_success(self, mock_post):
        mock_post.return_value.raise_for_status.return_value = None
        
        resume_execution("http://example.com", '{"status": "approved"}')
        
        self.assertEqual(mock_post.call_count, 1)
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "http://example.com")
        self.assertEqual(kwargs["headers"]["content-type"], "application/cloudevents+json")
        self.assertEqual(kwargs["timeout"], 10)
        self.assertIn(b'"data": "{\\\"status\\\": \\\"approved\\\"}"', kwargs["data"])
        self.assertIn(b'"type": "playbook.execution.resumed"', kwargs["data"])
        
    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.requests.post")
    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.frappe.log_error")
    def test_resume_execution_failure(self, mock_log_error, mock_post):
        mock_post.side_effect = requests.exceptions.RequestException("Connection error")
        
        with self.assertRaises(requests.exceptions.RequestException):
            resume_execution("http://example.com", '{"status": "approved"}')
            
        mock_log_error.assert_called_once()
