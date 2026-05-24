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
        
        response = requests.post(url, headers=headers, data=data, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        frappe.log_error(f"Failed to trigger n8n execution: {e}", "n8n Execution Error")
        raise

def resume_execution(url, payload):
    try:
        attributes = {
            "type": "playbook.execution.resumed",
            "source": "frappe",
            "id": str(uuid.uuid4())
        }
        event = CloudEvent(attributes, payload)
        headers, data = to_structured(event)
        
        response = requests.post(url, headers=headers, data=data, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        frappe.log_error(f"Failed to resume n8n execution: {e}", "n8n Execution Error")
        raise
