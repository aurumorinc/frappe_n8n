import unittest
from unittest.mock import patch, MagicMock
from frappe_n8n.n8n.doctype.playbook_execution.playbook_execution import trigger_test_execution
from requests.exceptions import RequestException
import uuid

class TestN8nTestExecutionUnit(unittest.TestCase):
    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.requests.post")
    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.frappe")
    def test_n8n_test_execution_webhook_url(self, mock_frappe, mock_post):
        # Arrange
        mock_frappe.db.exists.return_value = False
        mock_frappe.generate_hash.return_value = "hash123"
        
        settings = MagicMock()
        settings.enabled = 1
        settings.base_url = "https://n8n.example.com/"
        mock_frappe.get_single.return_value = settings
        
        playbook_doc = MagicMock()
        node = MagicMock()
        node.node_type = "n8n-nodes-base.webhook"
        node.n8n_webhook_id = "test-webhook-123"
        playbook_doc.get.return_value = [node]
        
        def get_doc_side_effect(doctype, *args, **kwargs):
            if isinstance(doctype, dict) and doctype.get("doctype") == "Playbook Execution":
                mock_exec = MagicMock()
                mock_exec.insert.return_value = None
                return mock_exec
            return playbook_doc
            
        mock_frappe.get_doc.side_effect = get_doc_side_effect
        
        mock_post.return_value.status_code = 200

        # Act
        trigger_test_execution(
            "Test Playbook", 
            "Test Doc", 
            "TEST-001", 
            {"data": "test"}, 
            "idemp-key"
        )
        
        # Assert
        mock_post.assert_called_once()
        url = mock_post.call_args[0][0]
        kwargs = mock_post.call_args[1]
        self.assertEqual(url, "https://n8n.example.com/webhook-test/test-webhook-123")
        self.assertEqual(kwargs["json"], {"data": "test"})
        self.assertEqual(kwargs["headers"]["Frappe-Playbook-Execution-Name"], "idemp-key")

    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.frappe")
    @patch("frappe_controller.utils.controller.wait_for_event")
    def test_n8n_test_execution_missing_webhook(self, mock_wait, mock_frappe):
        # Arrange
        mock_frappe.db.exists.return_value = False
        
        playbook_doc = MagicMock()
        playbook_doc.get.return_value = [] # No webhook nodes
        mock_frappe.get_doc.return_value = playbook_doc
        
        # Act & Assert
        with self.assertRaisesRegex(ValueError, "No webhook node found"):
            trigger_test_execution(
                "Test Playbook", 
                "Test Doc", 
                "TEST-001", 
                {"data": "test"}, 
                "idemp-key"
            )

    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.requests.post")
    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.frappe")
    def test_n8n_test_execution_api_failure(self, mock_frappe, mock_post):
        # Arrange
        mock_frappe.db.exists.return_value = False
        mock_frappe.generate_hash.return_value = "hash123"
        
        settings = MagicMock()
        settings.enabled = 1
        settings.base_url = "https://n8n.example.com"
        mock_frappe.get_single.return_value = settings
        
        playbook_doc = MagicMock()
        node = MagicMock()
        node.node_type = "n8n-nodes-base.webhook"
        node.n8n_webhook_id = "test-webhook-123"
        playbook_doc.get.return_value = [node]
        mock_frappe.get_doc.return_value = playbook_doc
        
        mock_post.side_effect = RequestException("Connection timeout")

        # Act & Assert
        with self.assertRaises(RequestException):
            trigger_test_execution(
                "Test Playbook", 
                "Test Doc", 
                "TEST-001", 
                {"data": "test"}, 
                "idemp-key"
            )
            
        mock_frappe.log_error.assert_called_once()
        self.assertIn("Failed to trigger n8n test execution", mock_frappe.log_error.call_args[0][0])
