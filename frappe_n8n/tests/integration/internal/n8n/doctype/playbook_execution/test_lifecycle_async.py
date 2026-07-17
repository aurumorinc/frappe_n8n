import frappe
from frappe.tests import IntegrationTestCase
from unittest.mock import patch

class TestN8nPlaybookTestLifecycle(IntegrationTestCase):
    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()
        super().tearDownClass()

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
        
        try:
            result = trigger_test_execution(playbook.name)
            
            self.assertEqual(result["status"], "success")
            self.assertEqual(result["message"], "Test event sent.")
            
            self.assertEqual(mock_exec_post.call_count, 1)
            self.assertEqual(mock_exec_post.call_args[0][0], "https://n8n.example.com/webhook-test/wh-sync-123")
            self.assertEqual(mock_exec_post.call_args[1]["json"]["name"], todo.name)
        finally:
            frappe.delete_doc("Playbook", playbook.name, force=1)
            frappe.delete_doc("ToDo", todo.name, force=1)

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
        
        try:
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
            mock_enqueue.assert_called_once_with("frappe_n8n.n8n.doctype.playbook_provider.playbook_provider.update_a_playbook", playbook_name=playbook.name)
            self.assertEqual(mock_post.call_count, 1)
            self.assertEqual(mock_post.call_args[0][0], "https://n8n.example.com/webhook-test/wh-async-123")
            self.assertEqual(mock_post.call_args[1]["json"]["name"], todo.name)
        finally:
            frappe.delete_doc("Playbook", playbook.name, force=1)
            frappe.delete_doc("ToDo", todo.name, force=1)
