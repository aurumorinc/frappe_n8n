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
