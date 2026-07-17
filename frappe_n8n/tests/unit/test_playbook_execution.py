import frappe
from frappe.tests import IntegrationTestCase
import json

class TestCallbackEndpoint(IntegrationTestCase):
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
