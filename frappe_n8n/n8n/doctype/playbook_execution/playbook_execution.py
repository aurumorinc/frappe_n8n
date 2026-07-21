import requests
import frappe

def send_webhook(playbook_name, payload, execution_name, is_test=False, webhook_id=None):
    if not webhook_id:
        playbook_doc = frappe.get_doc("Playbook", playbook_name)
        for node in playbook_doc.get("nodes", []):
            if node.get("node_type") == "n8n-nodes-base.webhook" and node.get("n8n_webhook_id"):
                webhook_id = node.get("n8n_webhook_id")
                break
                
    if not webhook_id:
        frappe.log_error(f"Cannot trigger execution for Playbook {playbook_name}: No webhook node found.", "n8n Integration Error")
        raise ValueError(f"No webhook node found for Playbook {playbook_name}")
        
    settings = frappe.get_single("n8n Settings")
    if not settings.enabled or not settings.base_url:
        frappe.log_error(f"Cannot trigger execution for Playbook {playbook_name}: n8n is not enabled or base_url is missing.", "n8n Integration Error")
        raise ValueError(f"n8n is not enabled or base_url is missing")
        
    endpoint = "webhook-test" if is_test else "webhook"
    url = f"{settings.base_url.rstrip('/')}/{endpoint}/{webhook_id}"
    
    headers = {
        "Content-Type": "application/json",
        "frappe-playbook-execution-name": execution_name
    }
    
    webhook_security = settings.get_password("webhook_security", raise_exception=False) or settings.webhook_security
    if webhook_security:
        headers["Authorization"] = f"Bearer {webhook_security}"
    
    response = requests.post(url, headers=headers, json=payload, timeout=10)
    response.raise_for_status()

def after_insert(doc, method=None):
    if doc.status == "queued":
        playbook = frappe.db.get_value("Playbook", doc.playbook, "provider")
        if playbook == "n8n":
            frappe.enqueue(
                "frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.trigger_execution",
                execution_name=doc.name,
                queue="high"
            )

def trigger_execution(execution_name):
    doc = frappe.get_doc("Playbook Execution", execution_name)
    if doc.status != "queued":
        return

    import json
    payload = json.loads(doc.execution_data) if doc.execution_data else {}
    try:
        send_webhook(doc.playbook, payload, doc.name, is_test=False)
        doc.status = "running"
        doc.save(ignore_permissions=True)
    except Exception as e:
        frappe.log_error(f"Failed to trigger n8n execution: {e}", "n8n Execution Error")
        # Ensure valid status transition paths (queued -> running -> error)
        doc.status = "running"
        doc.save(ignore_permissions=True)
        doc.status = "error"
        doc.save(ignore_permissions=True)
        raise

def on_update(doc, method=None):
    if doc.has_value_changed("status") and doc.status == "canceled":
        playbook = frappe.db.get_value("Playbook", doc.playbook, "provider")
        if playbook == "n8n" and doc.n8n_execution_id:
            frappe.enqueue(
                "frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.stop_execution",
                n8n_execution_id=doc.n8n_execution_id,
                queue="high"
            )

def stop_execution(n8n_execution_id):
    settings = frappe.get_single("n8n Settings")
    if not settings.enabled or not settings.base_url or not settings.api_key:
        return

    url = f"{settings.base_url.rstrip('/')}/api/v1/executions/{n8n_execution_id}/stop"
    api_key = settings.get_password("api_key") or settings.api_key
    headers = {
        "X-N8N-API-KEY": api_key,
        "Accept": "application/json"
    }

    try:
        response = requests.post(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            frappe.log_error("Execution already stopped or not found in n8n (404).", "n8n Integration Error")
            return
        frappe.log_error(f"Failed to stop n8n execution: {str(e)}", "n8n Integration Error")
        raise
    except requests.exceptions.RequestException as e:
        frappe.log_error(f"Failed to stop n8n execution: {str(e)}", "n8n Integration Error")
        raise

def get_debug_url(execution_name):
    doc = frappe.get_doc("Playbook Execution", execution_name)
    if not doc.get("n8n_execution_id"):
        return None
        
    playbook = frappe.get_doc("Playbook", doc.playbook)
    settings = frappe.get_single("n8n Settings")
    
    if not settings.base_url or not playbook.n8n_workflow_id:
        return None
        
    return f"{settings.base_url.rstrip('/')}/workflow/{playbook.n8n_workflow_id}/debug/{doc.n8n_execution_id}"

def replay(execution_name):
    from frappe_controller.utils.background_jobs import enqueue
    doc = frappe.get_doc("Playbook Execution", execution_name)
    import json
    payload = json.loads(doc.execution_data) if doc.execution_data else {}
    enqueue(
        "frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.send_webhook",
        playbook_name=doc.playbook,
        payload=payload,
        execution_name=doc.name
    )

def trigger_test_execution_sync(playbook_name, reference_doctype, reference_name, payload, execution_name):
    send_webhook(playbook_name, payload, execution_name, is_test=True)
    return True

def trigger_test_execution_async(playbook_name, reference_doctype, reference_name, payload, execution_name):
    import requests
    if not getattr(frappe.flags, "current_job_id", None):
        raise ValueError("trigger_test_execution_async must be run in a background job context.")
        
    try:
        from frappe_controller.utils.background_jobs import enqueue
        update_job = enqueue("frappe_n8n.n8n.doctype.playbook_provider.playbook_provider.update_a_playbook", playbook_name=playbook_name)
        update_job.result()
        
        playbook_doc = frappe.get_doc("Playbook", playbook_name)
        webhook_id = None
        for node in playbook_doc.get("nodes", []):
            if node.get("node_type") == "n8n-nodes-base.webhook" and node.get("n8n_webhook_id"):
                webhook_id = node.get("n8n_webhook_id")
                break
                
        if not webhook_id:
            frappe.log_error(f"No webhook node found for Playbook {playbook_name} even after update.", "n8n Execution Error")
            return
            
        send_webhook(playbook_name, payload, execution_name, is_test=True, webhook_id=webhook_id)
    except requests.exceptions.RequestException as e:
        frappe.log_error(f"Failed to trigger async n8n test execution (User may not have 'Listen for test events' active): {e}", "n8n Execution Error")
    except Exception as e:
        frappe.log_error(f"Failed to trigger async n8n test execution: {e}", "n8n Execution Error")

def resume_execution(url, payload, execution_id=None):
    try:
        headers = {"Content-Type": "application/json"}
        
        settings = frappe.get_single("n8n Settings")
        webhook_security = settings.get_password("webhook_security", raise_exception=False) or settings.webhook_security
        if webhook_security:
            headers["Authorization"] = f"Bearer {webhook_security}"
        
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
    except Exception as e:
        frappe.log_error(f"Failed to resume n8n execution: {e}", "n8n Execution Error")
        error_execution_id = execution_id or payload.get("execution_id")
        if error_execution_id and frappe.db.exists("Playbook Execution", error_execution_id):
            doc = frappe.get_doc("Playbook Execution", error_execution_id)
            doc.status = "error"
            doc.save(ignore_permissions=True)
            if not frappe.flags.in_test:
                frappe.db.commit()
        raise

