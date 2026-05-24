import frappe
from frappe.tests import IntegrationTestCase
from unittest.mock import patch
from frappe_n8n.n8n.doctype.playbook_provider.playbook_provider import N8nPlaybookProvider

class TestN8nPlaybookProvider(IntegrationTestCase):
    @patch("frappe_n8n.n8n.doctype.playbook_provider.playbook_provider.enqueue")
    def test_queue_trigger_execution(self, mock_enqueue):
        provider = N8nPlaybookProvider()
        playbook_doc = frappe._dict({"n8n_webhook_url": "http://n8n.example.com/webhook"})
        execution_doc = frappe._dict({"name": "EXEC-001"})
        payload = {"data": "test"}

        provider.queue_trigger_execution(playbook_doc, execution_doc, payload)

        mock_enqueue.assert_called_once_with(
            "frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.trigger_execution",
            url="http://n8n.example.com/webhook",
            payload=payload
        )

    @patch("frappe_n8n.n8n.doctype.n8n_settings.n8n_settings.requests.get")
    @patch("frappe_n8n.n8n.doctype.playbook_provider.playbook_provider.requests.post")
    def test_stop_execution(self, mock_post, mock_get):
        mock_get.return_value.status_code = 200
        settings = frappe.get_single("n8n Settings")
        settings.enabled = 1
        settings.base_url = "https://n8n.example.com"
        settings.api_key = "test_api_key"
        settings.save()
        
        mock_post.reset_mock()

        provider = N8nPlaybookProvider()
        execution_doc = frappe._dict({"n8n_execution_id": "12345"})

        provider.stop_execution(execution_doc)

        mock_post.assert_called_once_with(
            "https://n8n.example.com/api/v1/executions/12345/stop",
            headers={
                "X-N8N-API-KEY": "test_api_key",
                "Accept": "application/json"
            },
            timeout=10
        )

    @patch("frappe_n8n.n8n.doctype.playbook_provider.playbook_provider.enqueue")
    @patch("frappe_n8n.n8n.doctype.playbook_provider.playbook_provider.frappe.log_error")
    def test_queue_trigger_execution_missing_url(self, mock_log_error, mock_enqueue):
        provider = N8nPlaybookProvider()
        playbook_doc = frappe._dict({"n8n_webhook_url": None, "name": "Test Playbook"})
        execution_doc = frappe._dict({"name": "EXEC-001"})
        payload = {"data": "test"}

        provider.queue_trigger_execution(playbook_doc, execution_doc, payload)

        mock_enqueue.assert_not_called()
        mock_log_error.assert_called_once()
        
    @patch("frappe_n8n.n8n.doctype.playbook_provider.playbook_provider.enqueue")
    def test_queue_resume_execution(self, mock_enqueue):
        provider = N8nPlaybookProvider()
        execution_doc = frappe._dict({"name": "EXEC-001"})
        response_body = '{"status": "approved"}'
        callback_url = "http://n8n.example.com/resume"
        
        provider.queue_resume_execution(execution_doc, response_body, callback_url)
        
        mock_enqueue.assert_called_once_with(
            "frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.resume_execution",
            url=callback_url,
            payload=response_body
        )
