import frappe
from frappe.tests import IntegrationTestCase
from unittest.mock import patch, MagicMock
from frappe_n8n.n8n.doctype.playbook_execution.playbook_execution import trigger_test_execution_sync
from requests.exceptions import RequestException
import uuid

class TestN8nTestExecutionUnit(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not frappe.db.exists("Custom Field", "Playbook Node-n8n_webhook_id"):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "Playbook Node",
                "fieldname": "n8n_webhook_id",
                "fieldtype": "Data",
                "label": "n8n Webhook ID",
                "insert_after": "on_error"
            }).insert()
        if not frappe.db.exists("Custom Field", "Playbook Node-n8n_node_id"):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "Playbook Node",
                "fieldname": "n8n_node_id",
                "fieldtype": "Data",
                "label": "n8n Node ID",
                "insert_after": "on_error"
            }).insert()

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()
        super().tearDownClass()

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
        self.assertEqual(kwargs["headers"]["Frappe-Playbook-Execution-Name"], "idemp-key")

    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.frappe")
    @patch("frappe_controller.utils.controller.wait_for_event")
    def test_n8n_test_execution_missing_webhook(self, mock_wait, mock_frappe):
        # Arrange
        mock_frappe.db.exists.return_value = False
        mock_frappe.flags.current_job_id = None
        
        playbook_doc = MagicMock()
        playbook_doc.get.return_value = [] # No webhook nodes
        
        def get_doc_side_effect(doctype, name=None):
            return playbook_doc
            
        mock_frappe.get_doc.side_effect = get_doc_side_effect
        
        # Act & Assert
        with self.assertRaisesRegex(ValueError, "No webhook node found"):
            trigger_test_execution_sync(
                "Test Playbook",
                "Test Doc",
                "TEST-001",
                {"data": "test"},
                "idemp-key"
            )

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

    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.requests.post")
    def test_synchronous_test_execution_lifecycle(self, mock_post):
        # 1. Sets up dummy n8n Settings with valid credentials.
        settings = frappe.get_single("n8n Settings")
        settings.db_set("enabled", 1)
        settings.db_set("base_url", "https://n8n.example.com")
        settings.db_set("webhook_security", "test_token")

        # 2. Creates a dummy Playbook (configured with provider="n8n" and a mocked webhook node).
        playbook_name = "Test Playbook n8n Lifecycle"
        if frappe.db.exists("Playbook", playbook_name):
            frappe.delete_doc("Playbook", playbook_name)

        playbook = frappe.get_doc({
            "doctype": "Playbook",
            "playbook_name": playbook_name,
            "provider": "n8n",
            "document_type": "ToDo",
            "status": "Enabled",
            "nodes": [
                {
                    "node_name": "Webhook",
                    "node_type": "n8n-nodes-base.webhook",
                    "n8n_webhook_id": "wh-lifecycle-test"
                }
            ]
        }).insert(ignore_permissions=True)

        # 3. Creates a target ToDo document.
        todo = frappe.get_doc({
            "doctype": "ToDo",
            "description": "Test Integration Todo Lifecycle"
        }).insert(ignore_permissions=True)

        # 5. Mocks requests.post to return a 200 OK
        mock_post.return_value.status_code = 200

        # Verify no execution docs exist with a test execution name
        initial_executions = frappe.db.count("Playbook Execution")

        # 4. Calls trigger_test_execution(playbook_name) natively from playbook.py
        from frappe_playbook.playbook.doctype.playbook.playbook import trigger_test_execution as trigger_test_execution_native
        result = trigger_test_execution_native(playbook.name)

        # 6. Asserts that the webhook was called successfully
        self.assertTrue(mock_post.called)
        
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://n8n.example.com/webhook-test/wh-lifecycle-test")

        # 7. Asserts that NO Playbook Execution document is created in the database.
        final_executions = frappe.db.count("Playbook Execution")
        self.assertEqual(initial_executions, final_executions)

        # 8. Asserts that the response message successfully acknowledges the synchronous execution.
        self.assertEqual(result.get("status"), "success")
        self.assertEqual(result.get("message"), "Test event sent.")
