import frappe
from frappe.tests import IntegrationTestCase
from unittest.mock import patch
import requests
from frappe_n8n.n8n.doctype.playbook_execution.playbook_execution import trigger_execution, resume_execution

class TestN8nPlaybookExecution(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        frappe.db.delete("Playbook", {"playbook_name": ["like", "Test Playbook%"]})
        frappe.db.delete("Playbook Execution", {"playbook": ["like", "Test Playbook%"]})

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
        self.assertEqual(kwargs["timeout"], 10)
        self.assertIn(b'"data": {"data": "test"}', kwargs["data"])
        self.assertIn(b'"type": "playbook.execution.triggered"', kwargs["data"])
        self.assertIn(b'"name":', kwargs["data"]) # Verify provisional name was sent
        
        # Verify execution doc was created
        executions = frappe.get_all("Playbook Execution", filters={"idempotency_key": "test-key"}, fields=["status", "name"])
        self.assertEqual(len(executions), 1)
        self.assertEqual(executions[0].status, "running")
        
        frappe.db.delete("Playbook Execution", {"idempotency_key": "test-key"})
        playbook.delete()
        todo.delete()
        
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
        executions = frappe.get_all("Playbook Execution", filters={"idempotency_key": "test-key"})
        self.assertEqual(len(executions), 0)
        
        playbook.delete()
        todo.delete()
        
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

    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.requests.get")
    def test_retrieve_executions(self, mock_get):
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.json.return_value = {
            "data": [
                {
                    "id": "123",
                    "status": "success",
                    "mode": "webhook",
                    "data": {
                        "resultData": {
                            "runData": {
                                "Webhook": [
                                    {
                                        "data": {
                                            "main": [
                                                [
                                                    {
                                                        "json": {
                                                            "name": "test_exec_1"
                                                        }
                                                    }
                                                ]
                                            ]
                                        }
                                    }
                                ]
                            }
                        }
                    }
                }
            ]
        }
        
        settings = frappe.get_single("n8n Settings")
        settings.db_set("enabled", 1)
        settings.db_set("base_url", "https://n8n.example.com")
        
        playbook_name = "Test Playbook Retrieve"
        if frappe.db.exists("Playbook", playbook_name):
            frappe.delete_doc("Playbook", playbook_name)

        playbook = frappe.get_doc({
            "doctype": "Playbook",
            "playbook_name": playbook_name,
            "provider": "n8n",
            "document_type": "ToDo", "status": "Enabled",
            "n8n_workflow_id": "wf1"
        }).insert()
        
        execution = frappe.get_doc({
            "doctype": "Playbook Execution",
            "playbook": playbook.name,
            "status": "running"
        }).insert(ignore_permissions=True)
        
        mock_get.return_value.json.return_value["data"][0]["data"]["resultData"]["runData"]["Webhook"][0]["data"]["main"][0][0]["json"]["name"] = execution.name
        
        from frappe_n8n.n8n.doctype.playbook_execution.playbook_execution import retrieve_executions
        retrieve_executions(playbook.name)
        
        execution.reload()
        self.assertEqual(execution.n8n_execution_id, "123")
        self.assertEqual(execution.status, "success")
        
        frappe.delete_doc("Playbook Execution", execution.name)
        playbook.delete()

    @patch("frappe_n8n.n8n.doctype.playbook_provider.playbook_provider.N8nPlaybookProvider.get_execution_status")
    def test_poll_executions(self, mock_get_status):
        mock_get_status.return_value = {"status": "success"}
        
        settings = frappe.get_single("n8n Settings")
        settings.db_set("enabled", 1)
        settings.db_set("base_url", "https://n8n.example.com")
        
        playbook = frappe.get_doc({
            "doctype": "Playbook",
            "playbook_name": "Test Playbook Poll",
            "provider": "n8n",
            "document_type": "ToDo", "status": "Enabled"
        }).insert()
        
        execution = frappe.get_doc({
            "doctype": "Playbook Execution",
            "playbook": playbook.name,
            "status": "running",
            "n8n_execution_id": "456"
        }).insert(ignore_permissions=True)
        
        from frappe_n8n.n8n.doctype.playbook_execution.playbook_execution import poll_executions
        poll_executions()
        
        execution.reload()
        self.assertEqual(execution.status, "success")
        
        frappe.delete_doc("Playbook Execution", execution.name)
        playbook.delete()
