# Copyright (c) 2026, Aquiveal and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import requests


class n8nSettings(Document):
	def validate(self):
		if not self.webhook_security and not self.get_password("webhook_security", raise_exception=False):
			self.webhook_security = frappe.generate_hash(length=32)

		if self.enabled:
			if not self.base_url or not self.api_key:
				self.enabled = 0
				frappe.msgprint("Base URL and API Key are required to enable n8n integration. Integration has been disabled.", indicator="orange", alert=True)
				return
			
			# Validate credentials by making a test API call
			try:
				url = f"{self.base_url.rstrip('/')}/api/v1/workflows"
				api_key = self.get_password("api_key", raise_exception=False) or self.api_key
				headers = {
					"X-N8N-API-KEY": api_key,
					"Accept": "application/json"
				}
				response = requests.get(url, headers=headers, timeout=10)
				response.raise_for_status()
			except requests.exceptions.RequestException as e:
				self.enabled = 0
				frappe.msgprint(f"Failed to connect to n8n. Integration has been disabled. Error: {str(e)}", indicator="orange", alert=True)

	def on_update(self):
		if frappe.db.exists("Playbook Provider", "n8n"):
			provider = frappe.get_doc("Playbook Provider", "n8n")
			provider.enabled = self.enabled
			provider.save(ignore_permissions=True)
		
		if self.enabled:
			from frappe_controller.utils.background_jobs import enqueue
			enqueue("frappe_n8n.n8n.doctype.n8n_settings.n8n_settings.update_webhook_credential")

def update_webhook_credential():
	from frappe_controller.utils.controller import emit_event
	settings = frappe.get_single("n8n Settings")
	if not settings.enabled or not settings.base_url or not settings.api_key:
		return

	webhook_security = settings.get_password("webhook_security", raise_exception=False)
	if not webhook_security:
		webhook_security = settings.webhook_security
	if not webhook_security:
		webhook_security = frappe.generate_hash(length=32)
		frappe.db.set_value("n8n Settings", "n8n Settings", "webhook_security", webhook_security)
		settings.webhook_security = webhook_security

	api_key = settings.get_password("api_key", raise_exception=False) or settings.api_key
	headers = {
		"X-N8N-API-KEY": api_key,
		"Accept": "application/json",
		"Content-Type": "application/json"
	}

	credential_exists = False
	if settings.webhook_credential_id:
		check_url = f"{settings.base_url.rstrip('/')}/api/v1/credentials/{settings.webhook_credential_id}"
		payload = {
			"data": {
				"name": "Authorization",
				"value": f"Bearer {webhook_security}"
			}
		}
		try:
			# Use PATCH to sync the token and check existence
			response = requests.patch(check_url, headers=headers, json=payload, timeout=10)
			if response.status_code == 200:
				credential_exists = True
			elif response.status_code == 404:
				settings.webhook_credential_id = None
		except Exception:
			pass

	# If not found by ID, try to find by name
	if not credential_exists:
		try:
			list_url = f"{settings.base_url.rstrip('/')}/api/v1/credentials"
			response = requests.get(list_url, headers=headers, timeout=10)
			if response.status_code == 200:
				credentials = response.json().get("data", [])
				for cred in credentials:
					if cred.get("name") == "crm_n8n_api_key":
						settings.webhook_credential_id = cred.get("id")
						# Now patch it to sync the token
						patch_url = f"{settings.base_url.rstrip('/')}/api/v1/credentials/{settings.webhook_credential_id}"
						payload = {
							"data": {
								"name": "Authorization",
								"value": f"Bearer {webhook_security}"
							}
						}
						patch_response = requests.patch(patch_url, headers=headers, json=payload, timeout=10)
						if patch_response.status_code == 200:
							credential_exists = True
							settings.db_set("webhook_credential_id", settings.webhook_credential_id)
						break
		except Exception:
			pass

	just_created = False
	if not credential_exists:
		url = f"{settings.base_url.rstrip('/')}/api/v1/credentials"
		payload = {
			"name": "crm_n8n_api_key",
			"type": "httpHeaderAuth",
			"data": {
				"name": "Authorization",
				"value": f"Bearer {webhook_security}"
			}
		}
		try:
			response = requests.post(url, headers=headers, json=payload, timeout=10)
			response.raise_for_status()
			data = response.json()
			settings.db_set("webhook_credential_id", data.get("id"))
			settings.db_set("webhook_secret_updated", frappe.utils.now_datetime())
			credential_exists = True
			just_created = True
		except requests.exceptions.RequestException as e:
			frappe.log_error(f"Failed to create n8n webhook credential: {str(e)}", "n8n Integration Error")
			raise

	if credential_exists:
		destination_project_id = settings.project_id
		if not destination_project_id:
			try:
				projects_url = f"{settings.base_url.rstrip('/')}/api/v1/projects"
				response = requests.get(projects_url, headers=headers, timeout=10)
				if response.status_code == 200:
					projects = response.json().get("data", [])
					for p in projects:
						if p.get("type") == "personal":
							destination_project_id = p.get("id")
							break
			except Exception:
				pass

		if destination_project_id:
			transfer_url = f"{settings.base_url.rstrip('/')}/api/v1/credentials/{settings.webhook_credential_id}/transfer"
			transfer_payload = {"destinationProjectId": destination_project_id}
			try:
				requests.put(transfer_url, headers=headers, json=transfer_payload, timeout=10)
			except Exception as e:
				frappe.log_error(f"Failed to transfer n8n webhook credential: {str(e)}", "n8n Integration Error")
				raise

	emit_event(key="n8n_credential_ready", argument={"status": "success"})

def rotate_credentials():
	from frappe_controller.utils.controller import emit_event
	settings = frappe.get_single("n8n Settings")
	if not settings.enabled or not settings.base_url or not settings.api_key or not settings.webhook_credential_id:
		return

	new_webhook_security = frappe.generate_hash(length=32)
	
	url = f"{settings.base_url.rstrip('/')}/api/v1/credentials/{settings.webhook_credential_id}"
	api_key = settings.get_password("api_key", raise_exception=False) or settings.api_key
	headers = {
		"X-N8N-API-KEY": api_key,
		"Accept": "application/json",
		"Content-Type": "application/json"
	}
	payload = {
		"data": {
			"name": "Authorization",
			"value": f"Bearer {new_webhook_security}"
		}
	}
	try:
		response = requests.patch(url, headers=headers, json=payload, timeout=10)
		response.raise_for_status()
		settings.db_set("webhook_security", new_webhook_security)
		settings.db_set("webhook_secret_updated", frappe.utils.now_datetime())
		emit_event(key="n8n_credential_ready", argument={"status": "success"})
	except requests.exceptions.RequestException as e:
		frappe.log_error(f"Failed to update n8n webhook credential: {str(e)}", "n8n Integration Error")
		raise

def enqueue_rotate_credentials():
	settings = frappe.get_single("n8n Settings")
	if settings.enabled:
		from frappe_controller.utils.background_jobs import enqueue
		enqueue("frappe_n8n.n8n.doctype.n8n_settings.n8n_settings.rotate_credentials")
