import frappe
from frappe.tests import IntegrationTestCase
from unittest.mock import patch
import json

class TestN8nPlaybook(IntegrationTestCase):
    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()
        super().tearDownClass()

    def setUp(self):
        super().setUp()

    def tearDown(self):
        frappe.db.rollback()
        super().tearDown()

    @patch("requests.put")
    @patch("requests.post")
    def test_on_playbook_after_insert_creates_workflow(self, mock_post, mock_put):
        mock_post.return_value.status_code = 200
        mock_put.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "id": "wf-12345",
            "nodes": [
                {"name": "Webhook", "type": "n8n-nodes-base.webhook", "id": "node-1", "webhookId": "wh-1"}
            ],
            "connections": {}
        }
        
        settings = frappe.get_doc("n8n Settings")
        settings.db_set("enabled", 1)
        settings.db_set("base_url", "https://n8n.example.com")
        settings.db_set("api_key", "test_key")
        
        playbook = frappe.get_doc({
            "doctype": "Playbook",
            "playbook_name": "Test N8n Playbook Hook",
            "provider": "n8n",
            "document_type": "ToDo", 
            "status": "Enabled"
        }).insert()
        
        self.assertTrue(mock_post.called)
        self.assertEqual(mock_post.call_args[0][0], "https://n8n.example.com/api/v1/workflows")
        
        playbook.reload()
        self.assertEqual(playbook.n8n_workflow_id, "wf-12345")
        self.assertEqual(len(playbook.nodes), 1)
        self.assertEqual(playbook.nodes[0].node_name, "Webhook")
        self.assertEqual(playbook.nodes[0].n8n_webhook_id, "wh-1")
from unittest.mock import patch, MagicMock
import requests

class TestN8NTestExecutionGracefulExit(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        self.patcher = patch("frappe_n8n.n8n.doctype.playbook.playbook.create_workflow", return_value="wf-mock-123")
        self.mock_create_workflow = self.patcher.start()
        
        self.patcher2 = patch("frappe_n8n.n8n.doctype.playbook.playbook.toggle_workflow_status")
        self.mock_toggle = self.patcher2.start()

        self.patcher3 = patch("frappe_n8n.n8n.doctype.playbook.playbook.on_trash")
        self.mock_trash = self.patcher3.start()

        if not frappe.db.exists("Playbook Provider", "n8n"):
            frappe.get_doc({
                "doctype": "Playbook Provider",
                "provider_name": "n8n",
                "enabled": 1
            }).insert(ignore_permissions=True)

        self.playbook = frappe.get_doc({
            "doctype": "Playbook",
            "playbook_name": "Test Playbook",
            "provider": "n8n",
            "document_type": "ToDo",
            "status": "Enabled",
            "nodes": [{"node_type": "n8n-nodes-base.webhook", "n8n_webhook_id": "test-webhook-id"}]
        }).insert()

    def tearDown(self):
        self.patcher.stop()
        self.patcher2.stop()
        self.patcher3.stop()
        frappe.db.rollback()
        super().tearDown()
        
    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.send_webhook")
    def test_trigger_test_execution_graceful_failure(self, mock_send_webhook):
        from frappe_n8n.n8n.doctype.playbook.playbook import trigger_test_execution
        
        # Mocking 404 response
        response = MagicMock()
        response.status_code = 404
        mock_send_webhook.side_effect = requests.exceptions.HTTPError(response=response)
        
        original_get_all = frappe.get_all
        def custom_get_all(doctype, *args, **kwargs):
            if doctype == "Playbook Execution":
                return [frappe._dict({"reference_doctype": "ToDo", "reference_name": "test-todo"})]
            return original_get_all(doctype, *args, **kwargs)
        frappe.get_all = MagicMock(side_effect=custom_get_all)
        
        # Target doc
        target_doc = MagicMock()
        target_doc.doctype = "ToDo"
        target_doc.name = "test-todo"
        target_doc.as_dict.return_value = {}
        
        from frappe.model.document import get_doc as real_get_doc
        def custom_get_doc(*args, **kwargs):
            if args:
                doctype = args[0]
                if isinstance(doctype, str):
                    if doctype == "Playbook":
                        return self.playbook
                    if doctype == "ToDo" and len(args) > 1 and args[1] == "test-todo":
                        return target_doc
            return real_get_doc(*args, **kwargs)
            
        original_get_doc = frappe.get_doc
        frappe.get_doc = MagicMock(side_effect=custom_get_doc)
        
        try:
            result = trigger_test_execution(self.playbook.name)
            
            self.assertEqual(result.get("status"), "failed")
            self.assertEqual(result.get("title"), "Test Execution Failed")
            self.assertIn("404", result.get("message", ""))
        finally:
            frappe.get_doc = original_get_doc
            frappe.get_all = original_get_all

    def test_whitelisting_playbook_overrides(self):
        from frappe_n8n.n8n.doctype.playbook.playbook import get_builder_url, trigger_test_execution
        
        get_builder_url_func = get_builder_url
        get_builder_url_whitelisted = False
        while get_builder_url_func:
            if getattr(get_builder_url_func, "whitelisted", False) or hasattr(get_builder_url_func, "whitelisted"):
                get_builder_url_whitelisted = True
                break
            get_builder_url_func = getattr(get_builder_url_func, "__wrapped__", None)
            
        trigger_test_execution_func = trigger_test_execution
        trigger_test_execution_whitelisted = False
        while trigger_test_execution_func:
            if getattr(trigger_test_execution_func, "whitelisted", False) or hasattr(trigger_test_execution_func, "whitelisted"):
                trigger_test_execution_whitelisted = True
                break
            trigger_test_execution_func = getattr(trigger_test_execution_func, "__wrapped__", None)
            
        if not get_builder_url_whitelisted:
            from frappe_n8n import hooks
            self.assertIn("frappe_playbook.playbook.doctype.playbook.playbook.get_builder_url", hooks.override_whitelisted_methods)
            self.assertIn("frappe_playbook.playbook.doctype.playbook.playbook.trigger_test_execution", hooks.override_whitelisted_methods)
        else:
            self.assertTrue(get_builder_url_whitelisted)
            self.assertTrue(trigger_test_execution_whitelisted)
