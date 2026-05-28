# Copyright (c) 2026, Aquiveal and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from unittest.mock import patch

class IntegrationTestn8nSettings(IntegrationTestCase):
    """
    Integration tests for n8nSettings.
    """

    @patch("frappe_n8n.n8n.doctype.n8n_settings.n8n_settings.requests.get")
    @patch("frappe_controller.utils.background_jobs.enqueue")
    def setUp(self, mock_enqueue, mock_get):
        super().setUp()
        

        if not frappe.db.exists("Playbook Provider", "n8n"):
            provider = frappe.get_doc({
                "doctype": "Playbook Provider",
                "provider_name": "n8n",
                "enabled": 0
            })
            provider.insert(ignore_permissions=True)
            
        mock_get.return_value.status_code = 200
        self.settings = frappe.get_single("n8n Settings")
        self.settings.enabled = 1
        self.settings.base_url = "https://n8n.example.com"
        self.settings.api_key = "test_api_key"
        self.settings.webhook_security = "test_webhook_token"
        self.settings.save()

    def test_n8n_settings_save_and_retrieve(self):
        settings = frappe.get_single("n8n Settings")
        self.assertEqual(settings.enabled, 1)
        self.assertEqual(settings.base_url, "https://n8n.example.com")
        self.assertEqual(settings.get_password("api_key"), "test_api_key")
        self.assertEqual(settings.get_password("webhook_security"), "test_webhook_token")

    def test_n8n_settings_registers_provider(self):
        self.assertTrue(frappe.db.exists("Playbook Provider", "n8n"))
        provider = frappe.get_doc("Playbook Provider", "n8n")
        self.assertEqual(provider.enabled, 1)
        
        # Disable settings
        self.settings.enabled = 0
        self.settings.save()
        
        provider.reload()
        self.assertEqual(provider.enabled, 0)

    @patch("frappe_n8n.n8n.doctype.n8n_settings.n8n_settings.requests.get")
    @patch("frappe_controller.utils.background_jobs.enqueue")
    def test_n8n_settings_validation_failure(self, mock_enqueue, mock_get):
        import requests
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection failed")
        
        settings = frappe.get_single("n8n Settings")
        settings.enabled = 1
        settings.base_url = "https://invalid.example.com"
        settings.api_key = "invalid_key"
        settings.save()
        
        self.assertEqual(settings.enabled, 0)

    @patch("frappe_controller.utils.controller.emit_event")
    @patch("frappe_n8n.n8n.doctype.n8n_settings.n8n_settings.requests.get")
    @patch("frappe_n8n.n8n.doctype.n8n_settings.n8n_settings.requests.post")
    @patch("frappe_n8n.n8n.doctype.n8n_settings.n8n_settings.requests.put")
    def test_update_webhook_credential(self, mock_put, mock_post, mock_get, mock_emit):
        mock_get.return_value.status_code = 200
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"id": "test_cred_id"}
        mock_put.return_value.status_code = 200
        
        settings = frappe.get_single("n8n Settings")
        settings.db_set("enabled", 1)
        settings.db_set("base_url", "https://n8n.example.com")
        settings.db_set("api_key", "test_api_key")
        settings.db_set("webhook_security", "")
        settings.db_set("webhook_credential_id", "")
        
        from frappe_n8n.n8n.doctype.n8n_settings.n8n_settings import update_webhook_credential
        update_webhook_credential()
        
        settings.reload()
        self.assertEqual(settings.webhook_credential_id, "test_cred_id")
        mock_post.assert_called_once()
        mock_emit.assert_any_call(key="n8n_credential_ready", argument={"status": "success"})

    @patch("frappe_controller.utils.controller.emit_event")
    @patch("frappe_n8n.n8n.doctype.n8n_settings.n8n_settings.requests.patch")
    @patch("frappe_n8n.n8n.doctype.n8n_settings.n8n_settings.requests.put")
    def test_update_webhook_credential_transfers_project(self, mock_put, mock_patch, mock_emit):
        mock_patch.return_value.status_code = 200
        mock_put.return_value.status_code = 200
        
        settings = frappe.get_single("n8n Settings")
        settings.db_set("enabled", 1)
        settings.db_set("base_url", "https://n8n.example.com")
        settings.db_set("api_key", "test_api_key")
        settings.db_set("webhook_credential_id", "test_cred_id")
        settings.db_set("project_id", "new_project_id")
        
        from frappe_n8n.n8n.doctype.n8n_settings.n8n_settings import update_webhook_credential
        update_webhook_credential()
        
        mock_put.assert_called_once()
        args, kwargs = mock_put.call_args
        self.assertIn("new_project_id", kwargs["json"]["destinationProjectId"])
        mock_emit.assert_any_call(key="n8n_credential_ready", argument={"status": "success"})

    @patch("frappe_controller.utils.controller.emit_event")
    @patch("frappe_n8n.n8n.doctype.n8n_settings.n8n_settings.requests.patch")
    @patch("frappe_n8n.n8n.doctype.n8n_settings.n8n_settings.requests.post")
    @patch("frappe_n8n.n8n.doctype.n8n_settings.n8n_settings.requests.put")
    @patch("frappe_n8n.n8n.doctype.n8n_settings.n8n_settings.requests.get")
    def test_update_webhook_credential_recreates_if_deleted(self, mock_get, mock_put, mock_post, mock_patch, mock_emit):
        mock_patch.return_value.status_code = 404
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"id": "new_cred_id"}
        mock_put.return_value.status_code = 200
        mock_get.return_value.status_code = 200
        
        settings = frappe.get_single("n8n Settings")
        settings.db_set("enabled", 1)
        settings.db_set("base_url", "https://n8n.example.com")
        settings.db_set("api_key", "test_api_key")
        settings.db_set("webhook_credential_id", "old_cred_id")
        
        from frappe_n8n.n8n.doctype.n8n_settings.n8n_settings import update_webhook_credential
        update_webhook_credential()
        
        settings.reload()
        self.assertEqual(settings.webhook_credential_id, "new_cred_id")
        mock_post.assert_called_once()
        mock_emit.assert_any_call(key="n8n_credential_ready", argument={"status": "success"})

    @patch("frappe_controller.utils.controller.emit_event")
    @patch("frappe_n8n.n8n.doctype.n8n_settings.n8n_settings.requests.get")
    @patch("frappe_n8n.n8n.doctype.n8n_settings.n8n_settings.requests.patch")
    @patch("frappe_n8n.n8n.doctype.n8n_settings.n8n_settings.requests.put")
    def test_update_webhook_credential_transfers_to_personal(self, mock_put, mock_patch, mock_get, mock_emit):
        mock_patch.return_value.status_code = 200
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"data": [{"id": "personal_id", "type": "personal"}]}
        mock_put.return_value.status_code = 200
        
        settings = frappe.get_single("n8n Settings")
        settings.db_set("enabled", 1)
        settings.db_set("base_url", "https://n8n.example.com")
        settings.db_set("api_key", "test_api_key")
        settings.db_set("webhook_credential_id", "test_cred_id")
        settings.db_set("project_id", "")
        
        from frappe_n8n.n8n.doctype.n8n_settings.n8n_settings import update_webhook_credential
        update_webhook_credential()
        
        mock_put.assert_called_once()
        args, kwargs = mock_put.call_args
        self.assertEqual(kwargs["json"]["destinationProjectId"], "personal_id")
        mock_emit.assert_any_call(key="n8n_credential_ready", argument={"status": "success"})

    @patch("frappe_controller.utils.controller.emit_event")
    @patch("frappe_n8n.n8n.doctype.n8n_settings.n8n_settings.requests.get")
    @patch("frappe_n8n.n8n.doctype.n8n_settings.n8n_settings.requests.patch")
    @patch("frappe_n8n.n8n.doctype.n8n_settings.n8n_settings.requests.put")
    def test_update_webhook_credential_finds_by_name(self, mock_put, mock_patch, mock_get, mock_emit):
        mock_patch.return_value.status_code = 200
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"data": [{"id": "found_cred_id", "name": "crm_n8n_api_key"}]}
        mock_put.return_value.status_code = 200
        
        settings = frappe.get_single("n8n Settings")
        settings.db_set("enabled", 1)
        settings.db_set("base_url", "https://n8n.example.com")
        settings.db_set("api_key", "test_api_key")
        settings.db_set("webhook_credential_id", "")
        
        from frappe_n8n.n8n.doctype.n8n_settings.n8n_settings import update_webhook_credential
        update_webhook_credential()
        
        settings.reload()
        self.assertEqual(settings.webhook_credential_id, "found_cred_id")
        mock_patch.assert_called_once()
        mock_emit.assert_any_call(key="n8n_credential_ready", argument={"status": "success"})
        
    @patch("frappe_controller.utils.controller.emit_event")
    @patch("frappe_n8n.n8n.doctype.n8n_settings.n8n_settings.requests.get")
    @patch("frappe_n8n.n8n.doctype.n8n_settings.n8n_settings.requests.patch")
    @patch("frappe_controller.utils.background_jobs.enqueue")
    def test_queue_rotate_credentials(self, mock_enqueue, mock_patch, mock_get, mock_emit):
        mock_get.return_value.status_code = 200
        mock_patch.return_value.status_code = 200
        
        settings = frappe.get_single("n8n Settings")
        settings.enabled = 1
        settings.base_url = "https://n8n.example.com"
        settings.api_key = "test_api_key"
        settings.webhook_credential_id = "test_cred_id"
        settings.webhook_security = "test_webhook_token"
        settings.save()
        
        from frappe_n8n.n8n.doctype.n8n_settings.n8n_settings import queue_rotate_credentials
        queue_rotate_credentials()
        
        mock_patch.assert_called_once()
        mock_emit.assert_any_call(key="n8n_credential_ready", argument={"status": "success"})
