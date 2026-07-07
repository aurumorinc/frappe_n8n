import unittest
from unittest.mock import patch, MagicMock
from frappe_n8n.n8n.doctype.playbook_provider.playbook_provider import N8nPlaybookProvider

class TestN8nProviderTestExecutionUnit(unittest.TestCase):
    @patch("frappe_n8n.n8n.doctype.playbook_provider.playbook_provider.enqueue")
    def test_n8n_provider_queuing(self, mock_enqueue):
        provider = N8nPlaybookProvider()
        
        playbook_doc = MagicMock()
        playbook_doc.name = "Test Playbook"
        
        provider.queue_test_execution(
            playbook_doc,
            "Test Doc",
            "TEST-001",
            {"doc": {"name": "TEST-001"}},
            "test-key",
            as_child=False
        )
        
        mock_enqueue.assert_called_once_with(
            "frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.trigger_test_execution",
            playbook_name="Test Playbook",
            reference_doctype="Test Doc",
            reference_name="TEST-001",
            payload={"doc": {"name": "TEST-001"}},
            idempotency_key="test-key",
            as_child=False
        )
