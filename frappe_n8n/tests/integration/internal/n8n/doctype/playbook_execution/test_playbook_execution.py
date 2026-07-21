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

    def setUp(self):
        super().setUp()
        settings = frappe.get_single("n8n Settings")
        settings.enabled = 1
        settings.base_url = "https://n8n.example.com/"
        settings.webhook_security = "test_token"
        settings.api_key = "test_key"
        settings.save(ignore_permissions=True)

    def tearDown(self):
        frappe.db.rollback()
        super().tearDown()

    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.requests.post")
    def test_n8n_test_execution_webhook_url(self, mock_post):
        # Arrange
        original_exists = frappe.db.exists
        original_hash = frappe.generate_hash
        frappe.db.exists = MagicMock(return_value=False)
        frappe.generate_hash = MagicMock(return_value="hash123")
        
        settings = frappe.get_doc("n8n Settings")
        settings.enabled = 1
        settings.base_url = "https://n8n.example.com/"
        
        playbook_doc = MagicMock()
        node = MagicMock()
        node.get.side_effect = lambda k, d=None: "n8n-nodes-base.webhook" if k == "node_type" else "test-webhook-123" if k == "n8n_webhook_id" else d
        playbook_doc.get.return_value = [node]
        
        original_get_doc = frappe.get_doc
        original_get_single = frappe.get_single
        def custom_get_doc(doctype, *args, **kwargs):
            if isinstance(doctype, dict) and doctype.get("doctype") == "Playbook Execution":
                mock_exec = MagicMock()
                mock_exec.insert.return_value = None
                return mock_exec
            if doctype == "Playbook" and args and args[0] == "Test Playbook":
                return playbook_doc
            return original_get_doc(doctype, *args, **kwargs)
            
        def custom_get_single(doctype):
            if doctype == "n8n Settings":
                return settings
            return original_get_single(doctype)
            
        frappe.get_doc = MagicMock(side_effect=custom_get_doc)
        frappe.get_single = MagicMock(side_effect=custom_get_single)
        
        mock_post.return_value.status_code = 200

        # Act
        try:
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
        finally:
            frappe.get_doc = original_get_doc
            frappe.get_single = original_get_single
            frappe.db.exists = original_exists
            frappe.generate_hash = original_hash

    @patch("frappe_controller.utils.controller.wait_for_event")
    def test_n8n_test_execution_missing_webhook(self, mock_wait):
        # Arrange
        original_exists = frappe.db.exists
        frappe.db.exists = MagicMock(return_value=False)
        frappe.flags.current_job_id = None
        
        playbook_doc = MagicMock()
        playbook_doc.get.return_value = [] # No webhook nodes
        
        original_get_doc = frappe.get_doc
        def custom_get_doc(doctype, name=None):
            if doctype == "Playbook":
                return playbook_doc
            return original_get_doc(doctype, name)
            
        frappe.get_doc = MagicMock(side_effect=custom_get_doc)
        
        # Act & Assert
        try:
            with self.assertRaisesRegex(ValueError, "No webhook node found"):
                trigger_test_execution_sync(
                    "Test Playbook",
                    "Test Doc",
                    "TEST-001",
                    {"data": "test"},
                    "idemp-key"
                )
        finally:
            frappe.get_doc = original_get_doc
            frappe.db.exists = original_exists

    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.requests.post")
    def test_n8n_test_execution_api_failure(self, mock_post):
        # Arrange
        original_exists = frappe.db.exists
        original_hash = frappe.generate_hash
        frappe.db.exists = MagicMock(return_value=False)
        frappe.generate_hash = MagicMock(return_value="hash123")
        
        settings = frappe.get_single("n8n Settings")
        settings.enabled = 1
        settings.base_url = "https://n8n.example.com"
        
        playbook_doc = MagicMock()
        node = MagicMock()
        node.get.side_effect = lambda k, d=None: "n8n-nodes-base.webhook" if k == "node_type" else "test-webhook-123" if k == "n8n_webhook_id" else d
        playbook_doc.get.return_value = [node]
        
        def get_doc_side_effect(doctype, name=None):
            return playbook_doc
            
        # We need to preserve the real get_doc for some calls if needed, or mock carefully
        original_get_doc = frappe.get_doc
        original_get_single = frappe.get_single
        def custom_get_doc(doctype, name=None, *args, **kwargs):
            if doctype == "Playbook" and name == "Test Playbook":
                return playbook_doc
            if doctype == "n8n Settings":
                return settings
            return original_get_doc(doctype, name, *args, **kwargs)
            
        def custom_get_single(doctype):
            if doctype == "n8n Settings":
                return settings
            return original_get_single(doctype)
            
        frappe.get_doc = MagicMock(side_effect=custom_get_doc)
        frappe.get_single = MagicMock(side_effect=custom_get_single)
        frappe.log_error = MagicMock()
        
        mock_post.side_effect = RequestException("Connection timeout")

        # Act & Assert
        try:
            with self.assertRaises(RequestException):
                trigger_test_execution_sync(
                    "Test Playbook",
                    "Test Doc",
                    "TEST-001",
                    {"data": "test"},
                    "idemp-key"
                )
        finally:
            frappe.get_doc = original_get_doc
            frappe.get_single = original_get_single
            frappe.db.exists = original_exists
            frappe.generate_hash = original_hash
            # Restore other mocks if needed but unittest handles it somewhat


    @patch("frappe_n8n.n8n.doctype.playbook.playbook.create_workflow", return_value="wf-mock-123")
    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.requests.post")
    def test_synchronous_test_execution_lifecycle(self, mock_exec_post, mock_create_workflow):
        # 1. Sets up dummy n8n Settings with valid credentials.
        settings = frappe.get_doc("n8n Settings")
        settings.db_set("enabled", 1)
        settings.db_set("base_url", "https://n8n.example.com/")
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

        # Verify no execution docs exist with a test execution name
        initial_executions = frappe.db.count("Playbook Execution")

        # 4. Calls trigger_test_execution(playbook_name)
        from frappe_n8n.n8n.doctype.playbook.playbook import trigger_test_execution
        
        mock_exec_post.return_value.status_code = 200
        result = trigger_test_execution(playbook.name)
        
        # 6. Asserts that the webhook was called successfully
        self.assertTrue(mock_exec_post.called)
        
        args, kwargs = mock_exec_post.call_args
        self.assertEqual(args[0], "https://n8n.example.com/webhook-test/wh-lifecycle-test")

        # 7. Asserts that NO Playbook Execution document is created in the database.
        final_executions = frappe.db.count("Playbook Execution")
        self.assertEqual(initial_executions, final_executions)

        # 8. Asserts that the response message successfully acknowledges the synchronous execution.
        self.assertEqual(result.get("status"), "success")
        self.assertEqual(result.get("message"), "Test event sent.")

    @patch("frappe_n8n.n8n.doctype.playbook.playbook.create_workflow", return_value="wf-mock-123")
    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.requests.post")
    @patch("frappe.enqueue")
    def test_after_insert_hook_triggers_webhook(self, mock_enqueue, mock_post, mock_create_workflow):
        mock_post.return_value.status_code = 200

        settings = frappe.get_doc("n8n Settings")
        settings.db_set("enabled", 1)
        settings.db_set("base_url", "https://n8n.example.com/")

        playbook = frappe.get_doc({
            "doctype": "Playbook",
            "playbook_name": "Test Webhook Insert",
            "provider": "n8n",
            "document_type": "ToDo",
            "status": "Enabled",
            "nodes": [
                {
                    "node_name": "Webhook",
                    "node_type": "n8n-nodes-base.webhook",
                    "n8n_webhook_id": "wh-insert-123"
                }
            ]
        }).insert(ignore_permissions=True)

        todo = frappe.get_doc({"doctype": "ToDo", "description": "test"}).insert()

        execution = frappe.get_doc({
            "doctype": "Playbook Execution",
            "name": f"test-{frappe.generate_hash(length=8)}",
            "playbook": playbook.name,
            "reference_doctype": "ToDo",
            "reference_name": todo.name,
            "status": "queued",
            "execution_data": '{"test": "data"}'
        }).insert(ignore_permissions=True, ignore_links=True)

        # Assert that trigger_execution was enqueued
        mock_enqueue.assert_any_call(
            "frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.trigger_execution",
            execution_name=execution.name,
            queue="high"
        )

        # Simulate executing the background trigger
        from frappe_n8n.n8n.doctype.playbook_execution.playbook_execution import trigger_execution
        trigger_execution(execution.name)

        execution.reload()
        self.assertEqual(execution.status, "running")
        mock_post.assert_called_once()
        self.assertEqual(mock_post.call_args[0][0], "https://n8n.example.com/webhook/wh-insert-123")
        
        # Test error handling
        mock_post.side_effect = RequestException("Connection timeout")
        execution2 = frappe.get_doc({
            "doctype": "Playbook Execution",
            "name": f"test-{frappe.generate_hash(length=8)}",
            "playbook": playbook.name,
            "reference_doctype": "ToDo",
            "reference_name": todo.name,
            "status": "queued",
            "execution_data": '{"test": "data"}'
        }).insert(ignore_permissions=True, ignore_links=True)
        
        # Simulate executing the background trigger with error
        with self.assertRaises(RequestException):
            trigger_execution(execution2.name)

        execution2.reload()
        self.assertEqual(execution2.status, "error")

    @patch("frappe_n8n.n8n.doctype.playbook.playbook.create_workflow", return_value="wf-mock-123")
    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.requests.post")
    @patch("frappe.enqueue")
    def test_on_update_hook_stops_execution(self, mock_enqueue, mock_post, mock_create_workflow):
        mock_post.return_value.status_code = 200

        settings = frappe.get_doc("n8n Settings")
        settings.db_set("enabled", 1)
        settings.db_set("base_url", "https://n8n.example.com/")

        playbook = frappe.get_doc({
            "doctype": "Playbook",
            "playbook_name": "Test Webhook Update",
            "provider": "n8n",
            "document_type": "ToDo",
            "status": "Enabled"
        }).insert(ignore_permissions=True)

        todo = frappe.get_doc({"doctype": "ToDo", "description": "test"}).insert()

        execution = frappe.get_doc({
            "doctype": "Playbook Execution",
            "name": f"test-{frappe.generate_hash(length=8)}",
            "playbook": playbook.name,
            "reference_doctype": "ToDo",
            "reference_name": todo.name,
            "status": "waiting"
        })
        execution.db_set("n8n_execution_id", "exec-123")
        execution.insert(ignore_permissions=True, ignore_links=True)

        execution.status = "canceled"
        execution.save(ignore_permissions=True)

        # Assert stop_execution was enqueued
        mock_enqueue.assert_any_call(
            "frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.stop_execution",
            n8n_execution_id="exec-123",
            queue="high"
        )

        # Simulate executing background stop
        from frappe_n8n.n8n.doctype.playbook_execution.playbook_execution import stop_execution
        stop_execution("exec-123")

        mock_post.assert_called_once()
        self.assertEqual(mock_post.call_args[0][0], "https://n8n.example.com/api/v1/executions/exec-123/stop")
import json

from unittest.mock import patch

class TestCallbackEndpoint(IntegrationTestCase):
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

    def tearDown(self):
        self.patcher.stop()
        self.patcher2.stop()
        self.patcher3.stop()
        frappe.db.rollback()
        super().tearDown()

    def test_callback_success(self):
        todo = frappe.get_doc({"doctype": "ToDo", "description": "test"}).insert()
        playbook = frappe.get_doc({
            "doctype": "Playbook",
            "playbook_name": "Test Callback Playbook",
            "provider": "n8n",
            "document_type": "ToDo", "status": "Enabled",
        }).insert()
        
        execution = frappe.get_doc({
            "doctype": "Playbook Execution",
            "name": "live-callback-exec",
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
        self.assertEqual(result.get("name"), "live-callback-exec")
        
    def test_callback_not_found_but_create(self):
        from frappe_n8n.playbook_execution import callback

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

    def test_callback_test_execution_no_db_save(self):
        from frappe_n8n.playbook_execution import callback
        
        playbook = frappe.get_doc({
            "doctype": "Playbook",
            "playbook_name": "Test Transient Callback",
            "provider": "n8n",
            "document_type": "ToDo", "status": "Enabled",
        }).insert()

        payload = {
            "name": "test-playbookname-12345",
            "playbook": playbook.name,
            "status": "success",
            "execution_data": {"result": "ok"}
        }

        result = callback(**payload)

        # Assert returned result is formatted correctly
        self.assertEqual(result.get("status"), "success")
        self.assertEqual(result.get("execution_data"), json.dumps({"result": "ok"}))
        self.assertEqual(result.get("name"), "test-playbookname-12345")

        # Assert not in DB
        self.assertFalse(frappe.db.exists("Playbook Execution", "test-playbookname-12345"))

    def test_callback_test_execution_validation_failure(self):
        from frappe_n8n.playbook_execution import callback
        
        # Missing mandatory playbook field
        payload = {
            "name": "test-playbookname-invalid",
            "status": "success",
            "execution_data": {"result": "ok"}
        }

        # Assert validations are correctly invoked even for transient docs
        with self.assertRaises(frappe.exceptions.MandatoryError):
            callback(**payload)
            
        # Assert not in DB
        self.assertFalse(frappe.db.exists("Playbook Execution", "test-playbookname-invalid"))

    def test_callback_error_status(self):
        from frappe_n8n.playbook_execution import callback

        todo = frappe.get_doc({"doctype": "ToDo", "description": "test"}).insert()
        playbook = frappe.get_doc({
            "doctype": "Playbook",
            "playbook_name": "Test Callback Playbook Error",
            "provider": "n8n",
            "document_type": "ToDo", "status": "Enabled",
        }).insert()
        
        payload = {
            "status": "error",
            "playbook": playbook.name,
            "reference_doctype": "ToDo",
            "reference_name": todo.name,
            "execution_data": {"error": "Something went wrong"}
        }
        
        result = callback(execution_name="error-exec-123", **payload)
        
        self.assertEqual(result.get("status"), "error")
        self.assertEqual(result.get("execution_data"), json.dumps({"error": "Something went wrong"}))
        
        execution = frappe.get_doc("Playbook Execution", "error-exec-123")
        self.assertEqual(execution.status, "error")
        self.assertEqual(execution.execution_data, json.dumps({"error": "Something went wrong"}))
from unittest.mock import patch

class TestN8nPlaybookTestLifecycle(IntegrationTestCase):
    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()
        super().tearDownClass()

    def setUp(self):
        super().setUp()

    def tearDown(self):
        frappe.db.rollback()
        super().tearDown()

    @patch("frappe_n8n.n8n.doctype.playbook.playbook.create_workflow", return_value="wf-mock-123")
    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.requests.post")
    def test_sync_lifecycle(self, mock_exec_post, mock_create_workflow):
        mock_exec_post.return_value.status_code = 200
        
        settings = frappe.get_doc("n8n Settings")
        settings.db_set("enabled", 1)
        settings.db_set("base_url", "https://n8n.example.com")
        settings.db_set("webhook_security", "test_token")
        
        todo = frappe.get_doc({"doctype": "ToDo", "description": "test"}).insert()
        
        playbook = frappe.get_doc({
            "doctype": "Playbook",
            "playbook_name": "Test Sync Lifecycle",
            "provider": "n8n",
            "document_type": "ToDo", 
            "status": "Enabled",
            "nodes": [
                {
                    "node_name": "Webhook",
                    "node_type": "n8n-nodes-base.webhook",
                    "n8n_webhook_id": "wh-sync-123"
                }
            ]
        }).insert()
        
        from frappe_n8n.n8n.doctype.playbook.playbook import trigger_test_execution
        
        result = trigger_test_execution(playbook.name)
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["message"], "Test event sent.")
        
        self.assertEqual(mock_exec_post.call_count, 1)
        self.assertEqual(mock_exec_post.call_args[0][0], "https://n8n.example.com/webhook-test/wh-sync-123")
        self.assertEqual(mock_exec_post.call_args[1]["json"]["name"], todo.name)

    @patch("frappe_n8n.n8n.doctype.playbook.playbook.create_workflow", return_value="wf-mock-123")
    @patch("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.requests.post")
    @patch("frappe_controller.utils.background_jobs.enqueue")
    def test_async_lifecycle(self, mock_enqueue, mock_post, mock_create_workflow):
        mock_post.return_value.status_code = 200
        
        settings = frappe.get_doc("n8n Settings")
        settings.db_set("enabled", 1)
        settings.db_set("base_url", "https://n8n.example.com/")
        settings.db_set("webhook_security", "test_token")
        
        todo = frappe.get_doc({"doctype": "ToDo", "description": "test"}).insert()
        
        playbook = frappe.get_doc({
            "doctype": "Playbook",
            "playbook_name": "Test Async Lifecycle",
            "provider": "n8n",
            "document_type": "ToDo", 
            "status": "Enabled",
            "nodes": [
                {
                    "node_name": "Manual",
                    "node_type": "n8n-nodes-base.manualTrigger"
                }
            ]
        }).insert()
        
        from frappe_n8n.n8n.doctype.playbook.playbook import trigger_test_execution
        
        # Act 1: Initial trigger (will route to async)
        with patch("frappe_controller.utils.background_jobs.enqueue") as mock_provider_enqueue:
            result = trigger_test_execution(playbook.name)
            
            self.assertEqual(result["status"], "success")
            self.assertEqual(result["message"], "Test event queued.")
            self.assertEqual(mock_provider_enqueue.call_count, 1)
            
            # Get the exact payload that was enqueued
            enqueue_kwargs = mock_provider_enqueue.call_args[1]
            playbook_name = enqueue_kwargs["playbook_name"]
            reference_doctype = enqueue_kwargs["reference_doctype"]
            reference_name = enqueue_kwargs["reference_name"]
            payload = enqueue_kwargs["payload"]
            execution_name = enqueue_kwargs["execution_name"]

        # Act 2: Simulate the background job being processed
        # Before we run the async function, we simulate that the update job "succeeded"
        # by updating the playbook to have a webhook ID, which is what would happen in reality.
        def mock_enqueue_side_effect(*args, **kwargs):
            class MockJobPromise:
                def result(self):
                    pb = frappe.get_doc("Playbook", playbook_name)
                    pb.set("nodes", [
                        {
                            "node_name": "Webhook",
                            "node_type": "n8n-nodes-base.webhook",
                            "n8n_webhook_id": "wh-async-123"
                        }
                    ])
                    pb.save()
            return MockJobPromise()
            
        mock_enqueue.side_effect = mock_enqueue_side_effect
        
        from frappe_n8n.n8n.doctype.playbook_execution.playbook_execution import trigger_test_execution_async
        
        # Simulate being in a background job
        frappe.flags.current_job_id = "test-job-id"
        try:
            trigger_test_execution_async(
                playbook_name=playbook_name,
                reference_doctype=reference_doctype,
                reference_name=reference_name,
                payload=payload,
                execution_name=execution_name
            )
        finally:
            frappe.flags.current_job_id = None
            
        # Assertions for the async part
        mock_enqueue.assert_any_call("frappe_n8n.n8n.doctype.playbook_provider.playbook_provider.update_a_playbook", playbook_name=playbook.name)
        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(mock_post.call_args[0][0], "https://n8n.example.com/webhook-test/wh-async-123")
        self.assertEqual(mock_post.call_args[1]["json"]["name"], todo.name)
