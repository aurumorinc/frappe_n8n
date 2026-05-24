import requests
import frappe
import uuid
from cloudevents.http import CloudEvent, to_structured

def trigger_execution(url, payload):
    try:
        attributes = {
            "type": "playbook.execution.triggered",
            "source": "frappe",
            "id": str(uuid.uuid4())
        }
        event = CloudEvent(attributes, payload)
        headers, data = to_structured(event)
        
        settings = frappe.get_single("n8n Settings")
        webhook_security = settings.get_password("webhook_security", raise_exception=False) or settings.webhook_security
        if webhook_security:
            headers["Authorization"] = f"Bearer {webhook_security}"
        
        response = requests.post(url, headers=headers, data=data, timeout=10)
        response.raise_for_status()
    except Exception as e:
        frappe.log_error(f"Failed to trigger n8n execution: {e}", "n8n Execution Error")
        if "execution_id" in payload:
            frappe.db.set_value("Playbook Execution", payload["execution_id"], "status", "error")
        raise

def resume_execution(url, payload, execution_id=None):
    try:
        attributes = {
            "type": "playbook.execution.resumed",
            "source": "frappe",
            "id": str(uuid.uuid4())
        }
        event = CloudEvent(attributes, payload)
        headers, data = to_structured(event)
        
        settings = frappe.get_single("n8n Settings")
        webhook_security = settings.get_password("webhook_security", raise_exception=False) or settings.webhook_security
        if webhook_security:
            headers["Authorization"] = f"Bearer {webhook_security}"
        
        response = requests.post(url, headers=headers, data=data, timeout=10)
        response.raise_for_status()
    except Exception as e:
        frappe.log_error(f"Failed to resume n8n execution: {e}", "n8n Execution Error")
        if execution_id:
            frappe.db.set_value("Playbook Execution", execution_id, "status", "error")
        elif "execution_id" in payload:
            frappe.db.set_value("Playbook Execution", payload["execution_id"], "status", "error")
        raise
