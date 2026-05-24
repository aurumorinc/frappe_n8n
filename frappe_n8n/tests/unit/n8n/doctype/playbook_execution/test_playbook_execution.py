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
        
        mock_post.assert_called_once_with("http://example.com", json={"data": "test"}, timeout=10)
        
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
        
        mock_post.assert_called_once_with("http://example.com", json='{"status": "approved"}', timeout=10)
        
    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.requests.post")
    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.frappe.log_error")
    def test_resume_execution_failure(self, mock_log_error, mock_post):
        mock_post.side_effect = requests.exceptions.RequestException("Connection error")
        
        with self.assertRaises(requests.exceptions.RequestException):
            resume_execution("http://example.com", '{"status": "approved"}')
            
        mock_log_error.assert_called_once()
