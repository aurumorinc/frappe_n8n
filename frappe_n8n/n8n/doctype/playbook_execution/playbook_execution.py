import requests
import frappe

def send_webhook(playbook_name, payload, execution_name, is_test=False):
    playbook_doc = frappe.get_doc("Playbook", playbook_name)
    
    webhook_id = None
    for node in playbook_doc.get("nodes", []):
        if node.node_type == "n8n-nodes-base.webhook" and node.n8n_webhook_id:
            webhook_id = node.n8n_webhook_id
            break
            
    if not webhook_id:
        from frappe_controller.utils.controller import wait_for_event
        wait_for_event(
            event_key="n8n_workflow_created",
            condition=f"argument.get('playbook_name') == '{playbook_name}'"
        )
        playbook_doc = frappe.get_doc("Playbook", playbook_name)
        for node in playbook_doc.get("nodes", []):
            if node.node_type == "n8n-nodes-base.webhook" and node.n8n_webhook_id:
                webhook_id = node.n8n_webhook_id
                break
                
    if not webhook_id:
        frappe.log_error(f"Cannot trigger execution for Playbook {playbook_name}: No webhook node found even after waiting.", "n8n Integration Error")
        raise ValueError(f"No webhook node found for Playbook {playbook_name}")
        
    settings = frappe.get_single("n8n Settings")
    if not settings.enabled or not settings.base_url:
        frappe.log_error(f"Cannot trigger execution for Playbook {playbook_name}: n8n is not enabled or base_url is missing.", "n8n Integration Error")
        raise ValueError(f"n8n is not enabled or base_url is missing")
        
    endpoint = "webhook-test" if is_test else "webhook"
    url = f"{settings.base_url.rstrip('/')}/{endpoint}/{webhook_id}"
    
    headers = {
        "Content-Type": "application/json",
        "Frappe-Playbook-Execution-Name": execution_name
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

def trigger_test_execution(playbook_name, reference_doctype, reference_name, payload, execution_name):
    if frappe.db.exists("Playbook Execution", execution_name):
        return

    try:
        send_webhook(playbook_name, payload, execution_name, is_test=True)
        
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
        frappe.log_error(f"Failed to trigger n8n test execution: {e}", "n8n Execution Error")
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

