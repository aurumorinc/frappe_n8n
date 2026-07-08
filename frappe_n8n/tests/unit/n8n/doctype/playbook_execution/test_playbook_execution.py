import frappe
from frappe.tests import IntegrationTestCase
from unittest.mock import patch
import requests
from frappe_n8n.n8n.doctype.playbook_execution.playbook_execution import trigger_execution, resume_execution

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
        self.assertEqual(kwargs["headers"]["Frappe-Playbook-Execution-Name"], "test-key")
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
        
    def test_callback_success(self):
        import json
        todo = frappe.get_doc({"doctype": "ToDo", "description": "test"}).insert()
        playbook = frappe.get_doc({
            "doctype": "Playbook",
            "playbook_name": "Test Callback Playbook",
            "provider": "n8n",
            "document_type": "ToDo", "status": "Enabled",
        }).insert()
        
        execution = frappe.get_doc({
            "doctype": "Playbook Execution",
            "name": "test-callback-exec",
            "playbook": playbook.name,
            "reference_doctype": "ToDo",
            "reference_name": todo.name,
            "status": "running"
        }).insert(ignore_permissions=True, ignore_links=True)
        
        from frappe_n8n.playbook_execution import callback
        
        payload = {
            "status": "success",
            "execution": {"id": "n8n-12345"},
            "execution_data": {"test_key": "test_value"},
            "playbook": "Should Not Update",
            "unknown_field": "Should be ignored"
        }
        
        result = callback(execution_name=execution.name, **payload)
        
        execution.reload()
        self.assertEqual(execution.status, "success")
        self.assertEqual(execution.n8n_execution_id, "n8n-12345")
        
        # Verify execution_data was serialized to string
        self.assertEqual(execution.execution_data, json.dumps({"test_key": "test_value"}))
        
        # Verify disallowed fields were not updated
        self.assertEqual(execution.playbook, playbook.name)
        
        # Verify returned result is the updated document dict
        self.assertEqual(result.get("status"), "success")
        self.assertEqual(result.get("name"), "test-callback-exec")
        
    def test_callback_not_found_but_create(self):
        from frappe_n8n.playbook_execution import callback
        import json

        todo = frappe.get_doc({"doctype": "ToDo", "description": "test"}).insert()
        playbook = frappe.get_doc({
            "doctype": "Playbook",
            "playbook_name": "Test Callback Playbook Create",
            "provider": "n8n",
            "document_type": "ToDo", "status": "Enabled",
        }).insert()
        
        payload = {
            "status": "success",
            "playbook": playbook.name,
            "reference_doctype": "ToDo",
            "reference_name": todo.name,
            "execution": {"id": "n8n-create-123"},
            "execution_data": {"created": True}
        }
        
        result = callback(execution_name="new-exec-123", **payload)
        
        self.assertEqual(result.get("status"), "success")
        self.assertEqual(result.get("name"), "new-exec-123")
        self.assertEqual(result.get("playbook"), playbook.name)
        
        # Verify it was inserted in db
        execution = frappe.get_doc("Playbook Execution", "new-exec-123")
        self.assertEqual(execution.status, "success")
        self.assertEqual(execution.n8n_execution_id, "n8n-create-123")
        self.assertEqual(execution.execution_data, json.dumps({"created": True}))

    def test_callback_create_no_name(self):
        from frappe_n8n.playbook_execution import callback
        
        playbook = frappe.get_doc({
            "doctype": "Playbook",
            "playbook_name": "Test Callback Playbook No Name",
            "provider": "n8n",
            "document_type": "ToDo", "status": "Enabled",
        }).insert()
        
        payload = {
            "status": "success",
            "playbook": playbook.name
        }
        
        result = callback(**payload)
        
        self.assertEqual(result.get("status"), "success")
        self.assertIsNotNone(result.get("name"))
        self.assertEqual(len(result.get("name")), 10)
        
    def test_callback_create_missing_playbook(self):
        from frappe_n8n.playbook_execution import callback
        
        payload = {
            "status": "success"
        }
        
        with self.assertRaises(frappe.exceptions.ValidationError):
            callback(execution_name="non-existent-exec", **payload)
