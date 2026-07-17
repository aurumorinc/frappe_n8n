import frappe
from frappe_controller.utils.background_jobs import enqueue

def on_update(doc, method=None):
    if doc.has_value_changed("enabled"):
        playbooks = frappe.get_all("Playbook", filters={"provider": "n8n", "enabled": 1})
        for pb in playbooks:
            pb_doc = frappe.get_doc("Playbook", pb.name)
            # Need a new n8n helper for toggling since N8nPlaybookProvider is gone.
            # But the blueprint says "syncing active n8n playbooks when settings change"
            # It should likely trigger something similar to update_a_playbook or toggle directly.
            pass

def queue_update_playbooks():
    playbooks = frappe.get_all("Playbook", filters={"provider": "n8n"})
    for p in playbooks:
        enqueue("frappe_n8n.n8n.doctype.playbook_provider.playbook_provider.update_a_playbook", playbook_name=p.name)

def retrieve_workflow(playbook_name):
    playbook_doc = frappe.get_doc("Playbook", playbook_name)
    if not playbook_doc.n8n_workflow_id:
        return None
    # Assuming this logic gets moved to a helper or playbook.py
    import requests
    settings = frappe.get_single("n8n Settings")
    if not settings.enabled or not settings.base_url or not settings.api_key:
        frappe.throw("n8n integration is not enabled or missing credentials.")
        
    url = f"{settings.base_url.rstrip('/')}/api/v1/workflows/{playbook_doc.n8n_workflow_id}"
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

def after_save(doc, method):
    pass

def update_a_playbook(playbook_name):
    import json
    playbook_data = retrieve_workflow(playbook_name)
    if not playbook_data:
        return
        
    playbook_doc = frappe.get_doc("Playbook", playbook_name)
    
    # Status
    playbook_doc.enabled = playbook_data.get("active", False)
    
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
        
    frappe.flags.in_playbook_sync = True
    try:
        playbook_doc.save(ignore_permissions=True)
    finally:
        frappe.flags.in_playbook_sync = False

