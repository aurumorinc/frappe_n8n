import frappe
from frappe.tests import IntegrationTestCase
from unittest.mock import patch, MagicMock
import requests

class TestN8NTestExecutionGracefulExit(IntegrationTestCase):
    def setUp(self):
        self.playbook = frappe.get_doc({
            "doctype": "Playbook",
            "playbook_name": "Test Playbook",
            "provider": "n8n",
            "document_type": "ToDo",
            "status": "Enabled",
            "nodes": [{"node_type": "n8n-nodes-base.webhook", "n8n_webhook_id": "test-webhook-id"}]
        }).insert()
        
    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.send_webhook")
    @patch("frappe.get_all")
    @patch("frappe.get_doc")
    def test_trigger_test_execution_graceful_failure(self, mock_get_doc, mock_get_all, mock_send_webhook):
        from frappe_n8n.n8n.doctype.playbook.playbook import trigger_test_execution
        
        # Mocking 404 response
        response = MagicMock()
        response.status_code = 404
        mock_send_webhook.side_effect = requests.exceptions.HTTPError(response=response)
        
        mock_get_all.return_value = [{"reference_doctype": "ToDo", "reference_name": "test-todo"}]
        mock_get_doc.return_value = self.playbook
        
        # Target doc
        target_doc = MagicMock()
        target_doc.doctype = "ToDo"
        target_doc.name = "test-todo"
        target_doc.as_dict.return_value = {}
        
        def custom_get_doc(doctype, name=None, *args, **kwargs):
            if doctype == "Playbook":
                return self.playbook
            if doctype == "ToDo" and name == "test-todo":
                return target_doc
            return frappe.get_doc(doctype, name, *args, **kwargs)
            
        mock_get_doc.side_effect = custom_get_doc
        
        result = trigger_test_execution(self.playbook.name)
        
        self.assertEqual(result.get("status"), "failed")
        self.assertEqual(result.get("title"), "Test Execution Failed")
        self.assertIn("404", result.get("message", ""))

    def test_whitelisting_playbook_overrides(self):
        from frappe_n8n.n8n.doctype.playbook.playbook import get_builder_url, trigger_test_execution
        
        # Check for whitelist attribute
        self.assertTrue(hasattr(get_builder_url, "whitelisted"))
        self.assertTrue(hasattr(trigger_test_execution, "whitelisted"))
