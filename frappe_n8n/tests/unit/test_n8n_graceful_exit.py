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
    def test_trigger_test_execution_sync_handles_404(self, mock_send_webhook):
        from frappe_n8n.n8n.doctype.playbook_execution.playbook_execution import trigger_test_execution_sync
        
        # Mocking 404 response
        response = MagicMock()
        response.status_code = 404
        mock_send_webhook.side_effect = requests.exceptions.HTTPError(response=response)
        
        # We need to wrap it because send_webhook might raise inside trigger_test_execution_sync
        # But wait, trigger_test_execution_sync already handles HTTPError if we raise it
        # Actually in playbook_execution.py send_webhook calls requests.post(..).raise_for_status()
        
        # Let's mock send_webhook to raise directly
        mock_send_webhook.side_effect = requests.exceptions.HTTPError(response=response)
        
        with patch("frappe.msgprint") as mock_msgprint:
            result = trigger_test_execution_sync(
                playbook_name=self.playbook.name,
                reference_doctype="ToDo",
                reference_name="test-todo",
                payload={},
                execution_name="test-exec"
            )
            
            self.assertFalse(result)
            mock_msgprint.assert_called_once()
            self.assertIn("orange", mock_msgprint.call_args[1].get("indicator", ""))

    def test_whitelisting_playbook_overrides(self):
        from frappe_n8n.n8n.doctype.playbook.playbook import get_builder_url, trigger_test_execution
        
        # Check for whitelist attribute
        self.assertTrue(hasattr(get_builder_url, "whitelisted"))
        self.assertTrue(hasattr(trigger_test_execution, "whitelisted"))
