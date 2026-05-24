import frappe
import requests
from frappe_playbook.playbook.doctype.playbook_provider.playbook_provider import PlaybookProviderBase
from frappe_controller.utils.background_jobs import enqueue

class N8nPlaybookProvider(PlaybookProviderBase):
    def create_workflow(self, playbook_doc):
        import requests
        import uuid
        import json
        settings = frappe.get_single("n8n Settings")
        if not settings.enabled or not settings.base_url or not settings.api_key:
            frappe.throw("n8n integration is not enabled or missing credentials.")
            
        settings.ensure_webhook_credential()
            
        url = f"{settings.base_url.rstrip('/')}/api/v1/workflows"
        api_key = settings.get_password("api_key") or settings.api_key
        headers = {
            "X-N8N-API-KEY": api_key,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        webhook_id = str(uuid.uuid4())
        
        payload = {
            "name": playbook_doc.playbook_name,
            "nodes": [
                {
                    "parameters": {
                        "httpMethod": "POST",
                        "path": webhook_id,
                        "authentication": "headerAuth",
                        "options": {}
                    },
                    "type": "n8n-nodes-base.webhook",
                    "typeVersion": 1,
                    "position": [0, 0],
                    "id": str(uuid.uuid4()),
                    "name": "Webhook",
                    "webhookId": webhook_id,
                    "credentials": {
                        "httpHeaderAuth": {
                            "id": settings.webhook_credential_id,
                            "name": "crm_n8n_api_key"
                        }
                    }
                }
            ],
            "connections": {},
            "settings": {}
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()
            workflow_id = data.get("id")
            
            # Transfer to project if specified
            if settings.project_id:
                transfer_url = f"{url}/{workflow_id}/transfer"
                transfer_payload = {"destinationProjectId": settings.project_id}
                requests.put(transfer_url, headers=headers, json=transfer_payload, timeout=10)
                
            # Populate nodes immediately
            vue_flow_data = {
                "nodes": data.get("nodes", []),
                "connections": data.get("connections", {})
            }
            playbook_doc.playbook_data = json.dumps(vue_flow_data)
            
            playbook_doc.set("nodes", [])
            for node in data.get("nodes", []):
                playbook_doc.append("nodes", {
                    "node_name": node.get("name"),
                    "node_type": node.get("type"),
                    "disabled": node.get("disabled", False),
                    "retry_on_fail": node.get("retryOnFail", False),
                    "on_error": node.get("onError", ""),
                    "n8n_node_id": node.get("id"),
                    "n8n_webhook_id": node.get("webhookId", "")
                })
                
            playbook_doc.save(ignore_permissions=True)
                
            return workflow_id
        except requests.exceptions.RequestException as e:
            error_details = str(e)
            if hasattr(e, 'response') and e.response is not None:
                error_details += f" - Details: {e.response.text}"
            frappe.log_error(f"Failed to create n8n workflow: {error_details}", "n8n Integration Error")
            frappe.throw(f"Failed to create workflow in n8n. Error: {error_details}")
            
    def delete_workflow(self, playbook_doc):
        import requests
        settings = frappe.get_single("n8n Settings")
        if not settings.enabled or not settings.base_url or not settings.api_key:
            return

        if not playbook_doc.n8n_workflow_id:
            return

        url = f"{settings.base_url.rstrip('/')}/api/v1/workflows/{playbook_doc.n8n_workflow_id}"
        api_key = settings.get_password("api_key") or settings.api_key
        headers = {
            "X-N8N-API-KEY": api_key,
            "Accept": "application/json"
        }

        try:
            response = requests.delete(url, headers=headers, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            frappe.log_error(f"Failed to delete n8n workflow: {str(e)}", "n8n Integration Error")
            frappe.throw(f"Failed to delete workflow in n8n. Error: {str(e)}")

    def get_builder_url(self, playbook_doc):
        settings = frappe.get_single("n8n Settings")
        return f"{settings.base_url.rstrip('/')}/workflow/{playbook_doc.n8n_workflow_id}"
        
    def toggle_workflow_status(self, playbook_doc, is_active: bool):
        import requests
        settings = frappe.get_single("n8n Settings")
        if not settings.enabled or not settings.base_url or not settings.api_key:
            return
            
        if not playbook_doc.n8n_workflow_id:
            return
            
        action = "activate" if is_active else "deactivate"
        url = f"{settings.base_url.rstrip('/')}/api/v1/workflows/{playbook_doc.n8n_workflow_id}/{action}"
        api_key = settings.get_password("api_key") or settings.api_key
        headers = {
            "X-N8N-API-KEY": api_key,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(url, headers=headers, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            frappe.log_error(f"Failed to {action} n8n workflow: {str(e)}", "n8n Integration Error")
            frappe.throw(f"Failed to {action} workflow in n8n. Error: {str(e)}")
            
    def queue_trigger_execution(self, playbook_doc, execution_doc, payload):
        if not playbook_doc.n8n_webhook_url:
            frappe.log_error(f"Cannot trigger execution for Playbook {playbook_doc.name}: n8n_webhook_url is missing.", "n8n Integration Error")
            return
        enqueue("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.trigger_execution", url=playbook_doc.n8n_webhook_url, payload=payload)
        
    def queue_resume_execution(self, execution_doc, response_body, callback_url, idempotency_key=None):
        payload = response_body or {}
        if isinstance(payload, str):
            try:
                import json
                payload = json.loads(payload)
            except Exception:
                payload = {"data": payload}
        if idempotency_key:
            payload["idempotency_key"] = idempotency_key
        enqueue("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.resume_execution", url=callback_url, payload=payload)
        
    def get_execution_status(self, execution_id):
        import requests
        settings = frappe.get_single("n8n Settings")
        if not settings.enabled or not settings.base_url or not settings.api_key:
            return None
            
        url = f"{settings.base_url.rstrip('/')}/api/v1/executions/{execution_id}"
        api_key = settings.get_password("api_key") or settings.api_key
        headers = {
            "X-N8N-API-KEY": api_key,
            "Accept": "application/json"
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            frappe.log_error(f"Failed to get n8n execution status: {str(e)}", "n8n Integration Error")
            return None
            
    def retry_execution(self, execution_id):
        import requests
        settings = frappe.get_single("n8n Settings")
        if not settings.enabled or not settings.base_url or not settings.api_key:
            frappe.throw("n8n integration is not enabled or missing credentials.")
            
        url = f"{settings.base_url.rstrip('/')}/api/v1/executions/{execution_id}/retry"
        api_key = settings.get_password("api_key") or settings.api_key
        headers = {
            "X-N8N-API-KEY": api_key,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(url, headers=headers, json={"loadWorkflow": True}, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            frappe.log_error(f"Failed to retry n8n execution: {str(e)}", "n8n Integration Error")
            frappe.throw(f"Failed to retry execution in n8n. Error: {str(e)}")
            
    def stop_execution(self, execution_doc):
        import requests
        settings = frappe.get_single("n8n Settings")
        if not settings.enabled or not settings.base_url or not settings.api_key:
            frappe.throw("n8n integration is not enabled or missing credentials.")
            
        if not execution_doc.n8n_execution_id:
            return

        url = f"{settings.base_url.rstrip('/')}/api/v1/executions/{execution_doc.n8n_execution_id}/stop"
        api_key = settings.get_password("api_key") or settings.api_key
        headers = {
            "X-N8N-API-KEY": api_key,
            "Accept": "application/json"
        }
        
        try:
            response = requests.post(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            frappe.log_error(f"Failed to stop n8n execution: {str(e)}", "n8n Integration Error")
            frappe.throw(f"Failed to stop execution in n8n. Error: {str(e)}")

    def retrieve_workflow(self, workflow_id: str):
        import requests
        settings = frappe.get_single("n8n Settings")
        if not settings.enabled or not settings.base_url or not settings.api_key:
            frappe.throw("n8n integration is not enabled or missing credentials.")
            
        url = f"{settings.base_url.rstrip('/')}/api/v1/workflows/{workflow_id}"
        api_key = settings.get_password("api_key") or settings.api_key
        headers = {
            "X-N8N-API-KEY": api_key,
            "Accept": "application/json"
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            frappe.log_error(f"Failed to retrieve n8n workflow: {str(e)}", "n8n Integration Error")
            frappe.throw(f"Failed to retrieve workflow in n8n. Error: {str(e)}")

def queue_update_playbooks():
    playbooks = frappe.get_all("Playbook", filters={"provider": "n8n"})
    for p in playbooks:
        enqueue("frappe_n8n.n8n.doctype.playbook_provider.playbook_provider.update_a_playbook", playbook_name=p.name)

def retrieve_workflow(playbook_name):
    playbook_doc = frappe.get_doc("Playbook", playbook_name)
    if not playbook_doc.n8n_workflow_id:
        return None
    from frappe_playbook.playbook.doctype.playbook_provider.playbook_provider import get_provider_instance
    provider = get_provider_instance(playbook_doc.provider)
    return provider.retrieve_workflow(playbook_doc.n8n_workflow_id)

def update_a_playbook(playbook_name):
    import json
    playbook_data = enqueue("frappe_n8n.n8n.doctype.playbook_provider.playbook_provider.retrieve_workflow", playbook_name=playbook_name).result()
    if not playbook_data:
        return
        
    playbook_doc = frappe.get_doc("Playbook", playbook_name)
    
    # Status
    playbook_doc.is_active = playbook_data.get("active", False)
    
    # Vue-Flow Elements (playbook_data)
    # Translate n8n nodes and connections into vue-flow nodes and edges
    vue_flow_data = {
        "nodes": playbook_data.get("nodes", []),
        "connections": playbook_data.get("connections", {})
    }
    playbook_doc.playbook_data = json.dumps(vue_flow_data)
    
    # Child Table Nodes
    playbook_doc.set("nodes", [])
    for node in playbook_data.get("nodes", []):
        playbook_doc.append("nodes", {
            "node_name": node.get("name"),
            "node_type": node.get("type"),
            "disabled": node.get("disabled", False),
            "retry_on_fail": node.get("retryOnFail", False),
            "on_error": node.get("onError", ""),
            "n8n_node_id": node.get("id"),
            "n8n_webhook_id": node.get("webhookId", "")
        })
        
    playbook_doc.save()
