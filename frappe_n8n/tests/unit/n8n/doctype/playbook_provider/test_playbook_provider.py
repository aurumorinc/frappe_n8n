from frappe.tests import UnitTestCase
from unittest.mock import patch, MagicMock
from frappe_n8n.n8n.doctype.playbook_provider.playbook_provider import N8nPlaybookProvider

class TestN8nProviderTestExecutionUnit(UnitTestCase):
    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.trigger_test_execution_sync")
    def test_n8n_provider_triggering_synchronously(self, mock_trigger_sync):
        provider = N8nPlaybookProvider()
        
        playbook_doc = MagicMock()
        playbook_doc.name = "Test Playbook"
        playbook_doc.get.return_value = [
            {"node_type": "n8n-nodes-base.webhook", "n8n_webhook_id": "wh1"}
        ]
        
        result = provider.trigger_test_execution(
            playbook_doc,
            "Test Doc",
            "TEST-001",
            {"name": "TEST-001"},
            "test-key"
        )
        
        mock_trigger_sync.assert_called_once_with(
            playbook_name="Test Playbook",
            reference_doctype="Test Doc",
            reference_name="TEST-001",
            payload={"name": "TEST-001"},
            execution_name="test-key"
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["message"], "Test event sent.")

    @patch("frappe_n8n.n8n.doctype.playbook_provider.playbook_provider.enqueue")
    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.trigger_test_execution_sync")
    def test_n8n_provider_triggering_asynchronously(self, mock_trigger_sync, mock_enqueue):
        provider = N8nPlaybookProvider()
        
        playbook_doc = MagicMock()
        playbook_doc.name = "Test Playbook"
        playbook_doc.get.return_value = [
            {"node_type": "n8n-nodes-base.manualTrigger"}
        ]
        
        result = provider.trigger_test_execution(
            playbook_doc,
            "Test Doc",
            "TEST-001",
            {"name": "TEST-001"},
            "test-key"
        )
        
        mock_trigger_sync.assert_not_called()
        mock_enqueue.assert_called_once_with(
            "frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.trigger_test_execution_async",
            queue="high",
            playbook_name="Test Playbook",
            reference_doctype="Test Doc",
            reference_name="TEST-001",
            payload={"name": "TEST-001"},
            execution_name="test-key"
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["message"], "Test event queued.")

