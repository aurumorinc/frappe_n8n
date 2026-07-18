import frappe

@frappe.whitelist()
def get_builder_url(playbook_name):
    playbook_doc = frappe.get_doc("Playbook", playbook_name)
    settings = frappe.get_single("n8n Settings")
    return f"{settings.base_url.rstrip('/')}/workflow/{playbook_doc.n8n_workflow_id}"

@frappe.whitelist()
def trigger_test_execution(playbook_name):
    playbook_doc = frappe.get_doc("Playbook", playbook_name)
    
    # We need the payload, get it from waiting execution or latest valid doc
    waiting_exec = frappe.get_all(
        "Playbook Execution",
        filters={"playbook": playbook_name, "status": "waiting"},
        fields=["reference_doctype", "reference_name"],
        order_by="creation desc",
        limit=1
    )
    
    target_doc = None
    if waiting_exec:
        target_doc = frappe.get_doc(waiting_exec[0].reference_doctype, waiting_exec[0].reference_name)
    else:
        recent_docs = frappe.get_all(
            playbook_doc.document_type,
            order_by="creation desc",
            limit=50
        )
        for d in recent_docs:
            doc_instance = frappe.get_doc(playbook_doc.document_type, d.name)
            if playbook_doc.meets_condition(doc_instance):
                target_doc = doc_instance
                break
                
    if not target_doc:
        return {"status": "failed", "title": "No Document Found", "message": "No matching document found."}
        
    payload = target_doc.as_dict(convert_dates_to_str=True)
    execution_name = f"test-{playbook_doc.name}-{frappe.generate_hash(length=10)}"
    
    for node in playbook_doc.get("nodes", []):
        if node.get("node_type") == "n8n-nodes-base.webhook" and node.get("n8n_webhook_id"):
            from frappe_n8n.n8n.doctype.playbook_execution.playbook_execution import trigger_test_execution_sync
            import requests
            try:
                trigger_test_execution_sync(
                    playbook_name=playbook_doc.name,
                    reference_doctype=target_doc.doctype,
                    reference_name=target_doc.name,
                    payload=payload,
                    execution_name=execution_name
                )
                return {"status": "success", "title": "Test Execution Sent", "message": "Test event sent."}
            except requests.exceptions.RequestException as e:
                msg = "Failed to send test event to n8n. Please ensure 'Listen for test events' is active in n8n."
                if e.response is not None:
                    msg += f" (HTTP {e.response.status_code})"
                frappe.log_error(f"Failed to trigger n8n test execution: {e}", "n8n Execution Error")
                return {"status": "failed", "title": "Test Execution Failed", "message": msg}
            except Exception as e:
                frappe.log_error(f"Failed to trigger n8n test execution: {e}", "n8n Execution Error")
                return {"status": "failed", "title": "Error", "message": f"Failed to trigger n8n test execution: {str(e)}"}
    
    from frappe_controller.utils.background_jobs import enqueue
    enqueue(
        "frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.trigger_test_execution_async",
        queue="high",
        playbook_name=playbook_doc.name,
        reference_doctype=target_doc.doctype,
        reference_name=target_doc.name,
        payload=payload,
        execution_name=execution_name
    )
    return {"status": "success", "title": "Test Execution Queued", "message": "Test event queued."}


def create_workflow(playbook_doc):
    import requests
    import json
    from frappe_controller.utils.controller import emit_event
    
    settings = frappe.get_single("n8n Settings")
    if not settings.enabled or not settings.base_url or not settings.api_key:
        frappe.throw("n8n integration is not enabled or missing credentials.")
        
    url = f"{settings.base_url.rstrip('/')}/api/v1/workflows"
    api_key = settings.get_password("api_key") or settings.api_key
    headers = {
        "X-N8N-API-KEY": api_key,
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    payload = {
        "name": playbook_doc.playbook_name,
        "nodes": [],
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
        playbook_doc.db_set('playbook_data', json.dumps(vue_flow_data))
        
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
            
        # Instead of generic save that might trigger recursive updates, update the DB directly
        for child in playbook_doc.get("nodes"):
            child.db_insert()
        
        emit_event(key="n8n_workflow_created", argument={"playbook_name": playbook_doc.name})
            
        return workflow_id
    except requests.exceptions.RequestException as e:
        error_details = str(e)
        if hasattr(e, 'response') and e.response is not None:
            error_details += f" - Details: {e.response.text}"
        frappe.log_error(f"Failed to create n8n workflow: {error_details}", "n8n Integration Error")
        frappe.throw(f"Failed to create workflow in n8n. Error: {error_details}")

def toggle_workflow_status(playbook_doc, is_active: bool):
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

def on_update(doc, method=None):
    if doc.provider != "n8n":
        return
    if not doc.n8n_workflow_id:
        workflow_id = create_workflow(doc)
        if workflow_id:
            doc.db_set("n8n_workflow_id", workflow_id)
    
    if doc.has_value_changed("enabled"):
        toggle_workflow_status(doc, bool(doc.enabled))

def on_trash(doc, method=None):
    if doc.provider != "n8n" or not doc.n8n_workflow_id:
        return
    import requests
    settings = frappe.get_single("n8n Settings")
    if not settings.enabled or not settings.base_url or not settings.api_key:
        return

    url = f"{settings.base_url.rstrip('/')}/api/v1/workflows/{doc.n8n_workflow_id}"
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