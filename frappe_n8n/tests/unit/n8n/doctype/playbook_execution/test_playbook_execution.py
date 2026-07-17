import frappe
from frappe.tests import IntegrationTestCase
from unittest.mock import patch, MagicMock
import requests
from frappe_n8n.n8n.doctype.playbook_execution.playbook_execution import trigger_execution, resume_execution, trigger_test_execution_sync, trigger_test_execution_async

class TestN8nPlaybookExecution(IntegrationTestCase):
    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.requests.post")
    @patch("frappe_controller.utils.controller.wait_for_event")
    def test_trigger_execution_success(self, mock_wait, mock_post):
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {}
        
        settings = frappe.get_single("n8n Settings")
        settings.db_set("enabled", 1)
        settings.db_set("base_url", "https://n8n.example.com")
        settings.db_set("webhook_security", "test_token")
        
        todo = frappe.get_doc({"doctype": "ToDo", "description": "test"}).insert()
        
        playbook = frappe.get_doc({
            "doctype": "Playbook",
            "playbook_name": "Test Playbook Trigger",
            "provider": "n8n",
            "document_type": "ToDo", "status": "Enabled",
            "nodes": [
                {
                    "node_name": "Webhook",
                    "node_type": "n8n-nodes-base.webhook",
                    "n8n_webhook_id": "wh1"
                }
            ]
        }).insert()
        
        trigger_execution(playbook.name, "ToDo", todo.name, {"data": "test"}, "test-key")
        
        self.assertEqual(mock_post.call_count, 1)
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://n8n.example.com/webhook/wh1")
        self.assertEqual(kwargs["headers"]["Content-Type"], "application/json")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test_token")
        self.assertEqual(kwargs["headers"]["frappe-playbook-execution-name"], "test-key")
        self.assertEqual(kwargs["timeout"], 10)
        self.assertEqual(kwargs["json"], {"data": "test"})
        
        # Verify execution doc was created
        executions = frappe.get_all("Playbook Execution", filters={"name": "test-key"}, fields=["status", "name"])
        self.assertEqual(len(executions), 1)
        self.assertEqual(executions[0].status, "running")
        
    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.requests.post")
    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.frappe.log_error")
    @patch("frappe_controller.utils.controller.wait_for_event")
    def test_trigger_execution_failure(self, mock_wait, mock_log_error, mock_post):
        mock_post.side_effect = ValueError("Serialization error")
        mock_post.return_value.json.return_value = {}
        
        settings = frappe.get_single("n8n Settings")
        settings.db_set("enabled", 1)
        settings.db_set("base_url", "https://n8n.example.com")
        
        todo = frappe.get_doc({"doctype": "ToDo", "description": "test"}).insert()
        
        playbook = frappe.get_doc({
            "doctype": "Playbook",
            "playbook_name": "Test Playbook Trigger Fail",
            "provider": "n8n",
            "document_type": "ToDo", "status": "Enabled",
            "nodes": [
                {
                    "node_name": "Webhook",
                    "node_type": "n8n-nodes-base.webhook",
                    "n8n_webhook_id": "wh1"
                }
            ]
        }).insert()
        
        with self.assertRaises(ValueError):
            trigger_execution(playbook.name, "ToDo", todo.name, {"data": "test"}, "test-key")
            
        mock_log_error.assert_called_once()
        
        # Verify no execution doc was created
        executions = frappe.get_all("Playbook Execution", filters={"name": "test-key"})
        self.assertEqual(len(executions), 0)
        
    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.requests.post")
    def test_resume_execution_success(self, mock_post):
        mock_post.return_value.raise_for_status.return_value = None
        
        settings = frappe.get_single("n8n Settings")
        settings.webhook_security = "test_token"
        settings.save()
        
        resume_execution("http://example.com", {"status": "approved"})
        
        self.assertEqual(mock_post.call_count, 1)
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "http://example.com")
        self.assertEqual(kwargs["headers"]["Content-Type"], "application/json")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test_token")
        self.assertEqual(kwargs["timeout"], 10)
        self.assertEqual(kwargs["json"], {"status": "approved"})
        
    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.requests.post")
    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.frappe.log_error")
    def test_resume_execution_failure(self, mock_log_error, mock_post):
        mock_post.side_effect = ValueError("Serialization error")
        
        with self.assertRaises(ValueError):
            resume_execution("http://example.com", {"status": "approved"})
            
        mock_log_error.assert_called_once()
        
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
        node.get.side_effect = lambda k, d=None: "n8n-nodes-base.webhook" if k == "node_type" else "test-webhook-123" if k == "n8n_webhook_id" else d
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
        trigger_test_execution_sync(
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
        self.assertEqual(kwargs["headers"]["frappe-playbook-execution-name"], "idemp-key")

    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.frappe")
    def test_n8n_test_execution_missing_webhook_no_job_context(self, mock_frappe):
        # Arrange
        mock_frappe.db.exists.return_value = False
        mock_frappe.flags.current_job_id = None
        
        # Act & Assert
        with self.assertRaisesRegex(ValueError, "trigger_test_execution_async must be run in a background job context."):
            trigger_test_execution_async(
                "Test Playbook",
                "Test Doc",
                "TEST-001",
                {"data": "test"},
                "idemp-key"
            )

    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.requests.post")
    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.frappe")
    @patch("frappe_controller.utils.background_jobs.enqueue")
    def test_n8n_test_execution_async_flow(self, mock_enqueue, mock_frappe, mock_post):
        # Arrange
        mock_frappe.db.exists.return_value = False
        mock_frappe.generate_hash.return_value = "hash123"
        mock_frappe.flags.current_job_id = "mocked"
        
        settings = MagicMock()
        settings.enabled = 1
        settings.base_url = "https://n8n.example.com/"
        mock_frappe.get_single.return_value = settings
        
        playbook_doc = MagicMock()
        node = MagicMock()
        node.get.side_effect = lambda k, d=None: "n8n-nodes-base.webhook" if k == "node_type" else "test-webhook-123" if k == "n8n_webhook_id" else d
        playbook_doc.get.return_value = [node]
        
        def get_doc_side_effect(doctype, name=None):
            return playbook_doc
            
        mock_frappe.get_doc.side_effect = get_doc_side_effect
        
        mock_post.return_value.status_code = 200
        
        mock_job_promise = MagicMock()
        mock_enqueue.return_value = mock_job_promise

        # Act
        trigger_test_execution_async(
            "Test Playbook",
            "Test Doc",
            "TEST-001",
            {"data": "test"},
            "idemp-key"
        )
        
        # Assert
        mock_enqueue.assert_called_once_with("frappe_n8n.n8n.doctype.playbook_provider.playbook_provider.update_a_playbook", playbook_name="Test Playbook")
        mock_job_promise.result.assert_called_once()
        mock_post.assert_called_once()
        self.assertEqual(mock_post.call_args[0][0], "https://n8n.example.com/webhook-test/test-webhook-123")

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
        node.get.side_effect = lambda k, d=None: "n8n-nodes-base.webhook" if k == "node_type" else "test-webhook-123" if k == "n8n_webhook_id" else d
        playbook_doc.get.return_value = [node]
        def get_doc_side_effect(doctype, name=None):
            return playbook_doc
            
        mock_frappe.get_doc.side_effect = get_doc_side_effect
        
        from requests.exceptions import RequestException
        mock_post.side_effect = RequestException("Connection timeout")

        # Act & Assert
        with self.assertRaises(RequestException):
            trigger_test_execution_sync(
                "Test Playbook",
                "Test Doc",
                "TEST-001",
                {"data": "test"},
                "idemp-key"
            )
            
        mock_frappe.log_error.assert_called_once()
        self.assertIn("Failed to trigger n8n test execution", mock_frappe.log_error.call_args[0][0])
