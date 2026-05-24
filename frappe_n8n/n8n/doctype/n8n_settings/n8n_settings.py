# Copyright (c) 2026, Aquiveal and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import requests


class n8nSettings(Document):
	def validate(self):
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

	def before_save(self):
		self.ensure_webhook_credential()

	def ensure_webhook_credential(self):
		if not self.enabled or not self.base_url or not self.api_key:
			return

		webhook_security = self.get_password("webhook_security", raise_exception=False)
		if not webhook_security:
			webhook_security = self.webhook_security
		if not webhook_security:
			self.webhook_security = frappe.generate_hash(length=32)
			webhook_security = self.webhook_security

		api_key = self.get_password("api_key", raise_exception=False) or self.api_key
		headers = {
			"X-N8N-API-KEY": api_key,
			"Accept": "application/json",
			"Content-Type": "application/json"
		}

		credential_exists = False
		if self.webhook_credential_id:
			check_url = f"{self.base_url.rstrip('/')}/api/v1/credentials/{self.webhook_credential_id}"
			try:
				# Use PATCH with empty payload to check existence since GET /credentials/{id} returns 405
				response = requests.patch(check_url, headers=headers, json={}, timeout=10)
				if response.status_code == 200:
					credential_exists = True
				elif response.status_code == 404:
					self.webhook_credential_id = None
			except Exception:
				pass

		just_created = False
		if not self.webhook_credential_id:
			url = f"{self.base_url.rstrip('/')}/api/v1/credentials"
			payload = {
				"name": f"crm_n8n_api_key_{frappe.utils.today()}",
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
				self.webhook_credential_id = data.get("id")
				self.webhook_secret_updated = frappe.utils.now_datetime()
				credential_exists = True
				just_created = True
			except requests.exceptions.RequestException as e:
				frappe.log_error(f"Failed to create n8n webhook credential: {str(e)}", "n8n Integration Error")
				frappe.throw(f"Failed to create webhook credential in n8n. Error: {str(e)}")

		if credential_exists:
			destination_project_id = self.project_id
			if not destination_project_id:
				try:
					projects_url = f"{self.base_url.rstrip('/')}/api/v1/projects"
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
				transfer_url = f"{self.base_url.rstrip('/')}/api/v1/credentials/{self.webhook_credential_id}/transfer"
				transfer_payload = {"destinationProjectId": destination_project_id}
				try:
					requests.put(transfer_url, headers=headers, json=transfer_payload, timeout=10)
				except Exception as e:
					frappe.log_error(f"Failed to transfer n8n webhook credential: {str(e)}", "n8n Integration Error")

	def update_credentials(self):
		if not self.enabled or not self.base_url or not self.api_key or not self.webhook_credential_id:
			return

		new_webhook_security = frappe.generate_hash(length=32)
		
		url = f"{self.base_url.rstrip('/')}/api/v1/credentials/{self.webhook_credential_id}"
		api_key = self.get_password("api_key", raise_exception=False) or self.api_key
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
			self.webhook_security = new_webhook_security
			self.webhook_secret_updated = frappe.utils.now_datetime()
			self.save(ignore_permissions=True)
		except requests.exceptions.RequestException as e:
			frappe.log_error(f"Failed to update n8n webhook credential: {str(e)}", "n8n Integration Error")
			frappe.throw(f"Failed to update webhook credential in n8n. Error: {str(e)}")

def rotate_credentials():
	settings = frappe.get_single("n8n Settings")
	if settings.enabled:
		settings.update_credentials()
