import frappe
from frappe.tests import IntegrationTestCase
from frappe_n8n.n8n.doctype.playbook_provider.playbook_provider import N8nPlaybookProvider
from unittest.mock import patch

class TestN8nPlaybookProvider(IntegrationTestCase):
    @patch("frappe_n8n.n8n.doctype.n8n_settings.n8n_settings.requests.get")
    def setUp(self, mock_get):
        super().setUp()
        

        mock_get.return_value.status_code = 200
        self.settings = frappe.get_single("n8n Settings")
        self.settings.enabled = 1
        self.settings.base_url = "https://n8n.example.com"
        self.settings.api_key = "test_api_key"
        self.settings.save()

    @patch("frappe_controller.utils.controller.emit_event")
    @patch("frappe_n8n.n8n.doctype.playbook_provider.playbook_provider.requests.post")
    def test_create_workflow(self, mock_post, mock_emit):
        import json
        provider = N8nPlaybookProvider()
        
        playbook_doc = frappe.get_doc({
            "doctype": "Playbook",
            "playbook_name": "Test Playbook Create",
            "provider": "n8n",
            "document_type": "ToDo", "status": "Enabled"
        }).insert()
        
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "id": "new_workflow_id",
            "nodes": [],
            "connections": {}
        }
        
        with patch("frappe_n8n.n8n.doctype.playbook_provider.playbook_provider.frappe.get_single") as mock_get_single:
            class MockSettings:
                def __init__(self):
                    self.enabled = 1
                    self.base_url = "https://n8n.example.com"
                    self.api_key = "test_api_key"
                    self.webhook_credential_id = "test_cred_id"
                    self.project_id = None
                def get_password(self, key):
                    return getattr(self, key)
            
            settings = MockSettings()
            mock_get_single.return_value = settings
            
            workflow_id = provider.create_workflow(playbook_doc)
            
            mock_emit.assert_any_call(key="n8n_workflow_created", argument={"playbook_name": playbook_doc.name})
            self.assertEqual(workflow_id, "new_workflow_id")
            
            # Verify payload
            call_args = mock_post.call_args
            self.assertEqual(call_args[0][0], "https://n8n.example.com/api/v1/workflows")
            payload = call_args[1]["json"]
            self.assertEqual(payload["name"], "Test Playbook Create")
            self.assertEqual(len(payload["nodes"]), 0)
            
            # Verify nodes are empty
            playbook_doc.reload()
            self.assertEqual(len(playbook_doc.nodes), 0)
            
            playbook_data = json.loads(playbook_doc.playbook_data)
            self.assertEqual(len(playbook_data["nodes"]), 0)

    @patch("frappe_n8n.n8n.doctype.playbook_provider.playbook_provider.enqueue")
    def test_after_save(self, mock_enqueue):
        from frappe_n8n.n8n.doctype.playbook_provider.playbook_provider import after_save
        
        # Test 1: Should enqueue when conditions are met
        playbook_doc = frappe.get_doc({
            "doctype": "Playbook",
            "playbook_name": "Test Playbook After Save",
            "provider": "n8n",
            "document_type": "ToDo", "status": "Enabled"
        })
        playbook_doc.name = "Test Playbook After Save"
        frappe.flags.in_playbook_sync = False
        after_save(playbook_doc, "after_save")
        mock_enqueue.assert_called_once_with(
            "frappe_n8n.n8n.doctype.playbook_provider.playbook_provider.update_a_playbook",
            playbook_name=playbook_doc.name
        )
        
        # Test 2: Should skip if in sync
        mock_enqueue.reset_mock()
        frappe.flags.in_playbook_sync = True
        after_save(playbook_doc, "after_save")
        mock_enqueue.assert_not_called()
        frappe.flags.in_playbook_sync = False
        
        # Test 3: Should skip if wrong provider
        playbook_doc.provider = "other"
        after_save(playbook_doc, "after_save")
        mock_enqueue.assert_not_called()

    @patch("frappe_n8n.n8n.doctype.playbook_provider.playbook_provider.requests.delete")
    def test_delete_workflow(self, mock_delete):
        provider = N8nPlaybookProvider()

        class MockPlaybookDoc:
            n8n_workflow_id = "12345"

        playbook_doc = MockPlaybookDoc()

        provider.delete_workflow(playbook_doc)

        mock_delete.assert_called_once_with(
            "https://n8n.example.com/api/v1/workflows/12345",
            headers={
                "X-N8N-API-KEY": "test_api_key",
                "Accept": "application/json"
            },
            timeout=10
        )

    def test_get_builder_url(self):
        provider = N8nPlaybookProvider()
        
        # Mock a playbook doc
        class MockPlaybookDoc:
            n8n_workflow_id = "12345"
            
        playbook_doc = MockPlaybookDoc()
        
        url = provider.get_builder_url(playbook_doc)
        self.assertEqual(url, "https://n8n.example.com/workflow/12345")

    @patch("frappe_n8n.n8n.doctype.playbook_provider.playbook_provider.requests.get")
    def test_retrieve_workflow(self, mock_get):
        provider = N8nPlaybookProvider()
        mock_get.return_value.json.return_value = {"id": "12345", "name": "Test Workflow"}
        
        result = provider.retrieve_workflow("12345")
        
        mock_get.assert_called_once_with(
            "https://n8n.example.com/api/v1/workflows/12345",
            headers={
                "X-N8N-API-KEY": "test_api_key",
                "Accept": "application/json"
            },
            timeout=10
        )
        self.assertEqual(result, {"id": "12345", "name": "Test Workflow"})

    @patch("frappe_n8n.n8n.doctype.playbook_provider.playbook_provider.enqueue")
    def test_queue_update_playbooks(self, mock_enqueue):
        from frappe_n8n.n8n.doctype.playbook_provider.playbook_provider import queue_update_playbooks
        
        # Create a test playbook
        playbook = frappe.get_doc({
            "doctype": "Playbook",
            "playbook_name": "Test Playbook Queue",
            "provider": "n8n",
            "document_type": "ToDo", "status": "Enabled"
        }).insert()
        
        queue_update_playbooks()
        
        mock_enqueue.assert_any_call(
            "frappe_n8n.n8n.doctype.playbook_provider.playbook_provider.update_a_playbook",
            playbook_name=playbook.name
        )

    @patch("frappe_n8n.n8n.doctype.playbook_provider.playbook_provider.enqueue")
    def test_update_a_playbook(self, mock_enqueue):
        from frappe_n8n.n8n.doctype.playbook_provider.playbook_provider import update_a_playbook
        import json
        
        # Create a test playbook
        playbook = frappe.get_doc({
            "doctype": "Playbook",
            "playbook_name": "Test Playbook Update",
            "provider": "n8n",
            "document_type": "ToDo", "status": "Enabled"
        }).insert()
        
        # Mock the result of retrieve_workflow
        mock_result = mock_enqueue.return_value
        mock_result.result.return_value = {
            "active": True,
            "nodes": [
                {
                    "id": "node1",
                    "name": "Webhook",
                    "type": "n8n-nodes-base.webhook",
                    "disabled": False,
                    "retryOnFail": True,
                    "onError": "continue",
                    "webhookId": "wh1"
                }
            ],
            "connections": {
                "Webhook": {
                    "main": [
                        [
                            {
                                "node": "Next Node",
                                "type": "main",
                                "index": 0
                            }
                        ]
                    ]
                }
            }
        }
        
        update_a_playbook(playbook.name)
        
        # Reload playbook
        playbook.reload()
        
        self.assertTrue(playbook.is_active)
        self.assertEqual(len(playbook.nodes), 1)
        self.assertEqual(playbook.nodes[0].node_name, "Webhook")
        self.assertEqual(playbook.nodes[0].node_type, "n8n-nodes-base.webhook")
        self.assertEqual(playbook.nodes[0].disabled, 0)
        self.assertEqual(playbook.nodes[0].retry_on_fail, 1)
        self.assertEqual(playbook.nodes[0].on_error, "continue")
        self.assertEqual(playbook.nodes[0].n8n_node_id, "node1")
        self.assertEqual(playbook.nodes[0].n8n_webhook_id, "wh1")
        
        playbook_data = json.loads(playbook.playbook_data)
        self.assertEqual(len(playbook_data["nodes"]), 1)
        self.assertIn("Webhook", playbook_data["connections"])

    @patch("frappe_n8n.n8n.doctype.playbook_provider.playbook_provider.enqueue")
    def test_update_a_playbook_no_data(self, mock_enqueue):
        from frappe_n8n.n8n.doctype.playbook_provider.playbook_provider import update_a_playbook
        
        playbook = frappe.get_doc({
            "doctype": "Playbook",
            "playbook_name": "Test Playbook No Data",
            "provider": "n8n",
            "document_type": "ToDo", "status": "Enabled"
        }).insert()
        
        mock_result = mock_enqueue.return_value
        mock_result.result.return_value = None
        
        update_a_playbook(playbook.name)
        
        playbook.reload()
        self.assertEqual(len(playbook.nodes), 0)

    @patch("frappe_n8n.n8n.doctype.playbook_provider.playbook_provider.requests.get")
    def test_retrieve_workflow_api_error(self, mock_get):
        import requests
        provider = N8nPlaybookProvider()
        
        # Mock a 404 error
        mock_response = mock_get.return_value
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Client Error")
        
        with self.assertRaises(frappe.exceptions.ValidationError):
            provider.retrieve_workflow("invalid_id")

    def test_retrieve_workflow_missing_credentials(self):
        provider = N8nPlaybookProvider()
        
        # Disable settings
        self.settings.enabled = 0
        self.settings.save()
        
        with self.assertRaises(frappe.exceptions.ValidationError):
            provider.retrieve_workflow("12345")
            
        # Re-enable for other tests
        self.settings.enabled = 1
        self.settings.save()

    @patch("frappe_n8n.n8n.doctype.playbook_provider.playbook_provider.enqueue")
    def test_update_a_playbook_existing_nodes(self, mock_enqueue):
        from frappe_n8n.n8n.doctype.playbook_provider.playbook_provider import update_a_playbook
        
        playbook = frappe.get_doc({
            "doctype": "Playbook",
            "playbook_name": "Test Playbook Existing Nodes",
            "provider": "n8n",
            "document_type": "ToDo", "status": "Enabled",
            "nodes": [
                {
                    "node_name": "Old Node",
                    "node_type": "n8n-nodes-base.old",
                    "n8n_node_id": "old1"
                }
            ]
        }).insert()
        
        mock_result = mock_enqueue.return_value
        mock_result.result.return_value = {
            "active": True,
            "nodes": [
                {
                    "id": "new1",
                    "name": "New Node",
                    "type": "n8n-nodes-base.new"
                }
            ]
        }
        
        update_a_playbook(playbook.name)
        
        playbook.reload()
        self.assertEqual(len(playbook.nodes), 1)
        self.assertEqual(playbook.nodes[0].node_name, "New Node")
        self.assertEqual(playbook.nodes[0].n8n_node_id, "new1")

    @patch("frappe_n8n.n8n.doctype.playbook_provider.playbook_provider.enqueue")
    def test_queue_trigger_execution(self, mock_enqueue):
        provider = N8nPlaybookProvider()
        
        class MockDoc:
            name = "test_name"
            doctype = "ToDo"
            def get(self, key, default=None):
                return []
                
        playbook_doc = MockDoc()
        execution_doc = MockDoc()
        
        provider.queue_trigger_execution(playbook_doc, "ToDo", "TASK-001", {"data": "test"}, "test-key")
        
        mock_enqueue.assert_called_once_with(
            "frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.trigger_execution",
            playbook_name="test_name",
            reference_doctype="ToDo",
            reference_name="TASK-001",
            payload={"data": "test"},
            execution_name="test-key",
            as_child=True
        )
