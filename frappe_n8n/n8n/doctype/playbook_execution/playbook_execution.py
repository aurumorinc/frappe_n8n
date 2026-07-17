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

def trigger_execution(playbook_name, reference_doctype, reference_name, payload, execution_name):
    # Idempotency check
    if frappe.db.exists("Playbook Execution", execution_name):
        return

    try:
        send_webhook(playbook_name, payload, execution_name, is_test=False)
        
        # Create Playbook Execution only after successful webhook call
        execution_doc = frappe.get_doc({
            "doctype": "Playbook Execution",
            "name": execution_name,
            "playbook": playbook_name,
            "reference_doctype": reference_doctype,
            "reference_name": reference_name,
            "status": "running",
            "execution_data": frappe.as_json(payload)
        })
        execution_doc.insert(ignore_permissions=True)
        if not frappe.flags.in_test:
            frappe.db.commit()
    except Exception as e:
        frappe.log_error(f"Failed to trigger n8n execution: {e}", "n8n Execution Error")
        raise

def trigger_test_execution_sync(playbook_name, reference_doctype, reference_name, payload, execution_name):
    try:
        send_webhook(playbook_name, payload, execution_name, is_test=True)
    except Exception as e:
        frappe.log_error(f"Failed to trigger n8n test execution: {e}", "n8n Execution Error")
        raise

def trigger_test_execution_async(playbook_name, reference_doctype, reference_name, payload, execution_name):
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
            raise ValueError(f"No webhook node found for Playbook {playbook_name} even after update.")
            
        send_webhook(playbook_name, payload, execution_name, is_test=True, webhook_id=webhook_id)
    except Exception as e:
        frappe.log_error(f"Failed to trigger async n8n test execution: {e}", "n8n Execution Error")
        raise

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

