import requests
import frappe
import uuid
from cloudevents.http import CloudEvent, to_structured

def trigger_execution(playbook_name, reference_doctype, reference_name, payload, idempotency_key):
    from frappe_controller.utils.controller import wait_for_event
    
    # Idempotency check
    if frappe.db.exists("Playbook Execution", {"idempotency_key": idempotency_key}):
        return

    playbook_doc = frappe.get_doc("Playbook", playbook_name)
    
    webhook_id = None
    for node in playbook_doc.get("nodes", []):
        if node.node_type == "n8n-nodes-base.webhook" and node.n8n_webhook_id:
            webhook_id = node.n8n_webhook_id
            break
            
    if not webhook_id:
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
        
    url = f"{settings.base_url.rstrip('/')}/webhook/{webhook_id}"
    
    try:
        provisional_name = frappe.generate_hash(length=10)
        cloudevent_id = str(uuid.uuid4())
        attributes = {
            "type": "playbook.execution.triggered",
            "source": "frappe",
            "id": cloudevent_id,
            "name": provisional_name
        }
        event = CloudEvent(attributes, payload)
        headers, data = to_structured(event)
        
        # Ensure Content-Type is strictly application/json so n8n parses the body correctly
        headers = {k: v for k, v in headers.items() if k.lower() != "content-type"}
        headers["Content-Type"] = "application/json"
        
        webhook_security = settings.get_password("webhook_security", raise_exception=False) or settings.webhook_security
        if webhook_security:
            headers["Authorization"] = f"Bearer {webhook_security}"
        
        response = requests.post(url, headers=headers, data=data, timeout=10)
        response.raise_for_status()
        
        # Webhook trigger does not return executionId synchronously (returns {"message": "Workflow was started"})
        # The execution ID will be retrieved asynchronously via retrieve_executions background job.
        n8n_execution_id = None
        
        # Create Playbook Execution only after successful webhook call
        execution_doc = frappe.get_doc({
            "doctype": "Playbook Execution",
            "name": provisional_name,
            "playbook": playbook_name,
            "reference_doctype": reference_doctype,
            "reference_name": reference_name,
            "status": "running",
            "idempotency_key": idempotency_key,
            "n8n_execution_id": n8n_execution_id
        })
        execution_doc.insert(ignore_permissions=True)
        frappe.db.commit()

        # Enqueue sync to get the execution ID if not returned synchronously
        from frappe_controller.utils.background_jobs import enqueue
        enqueue(
            "frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.retrieve_executions",
            playbook_name=playbook_name
        )
        
    except Exception as e:
        frappe.log_error(f"Failed to trigger n8n execution: {e}", "n8n Execution Error")
        raise

def retrieve_executions(playbook_name):
    playbook_doc = frappe.get_doc("Playbook", playbook_name)
    if not playbook_doc.n8n_workflow_id:
        frappe.log_error(f"Cannot retrieve executions for Playbook {playbook_name}: Missing n8n_workflow_id", "n8n Sync Error")
        raise ValueError(f"Playbook {playbook_name} is not linked to an n8n workflow.")
        
    settings = frappe.get_single("n8n Settings")
    if not settings.enabled or not settings.base_url or not settings.api_key:
        return
        
    url = f"{settings.base_url.rstrip('/')}/api/v1/executions?workflowId={playbook_doc.n8n_workflow_id}&includeData=true&limit=50"
    api_key = settings.get_password("api_key") or settings.api_key
    headers = {
        "X-N8N-API-KEY": api_key,
        "Accept": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        for exec_data in data.get("data", []):
            n8n_execution_id = str(exec_data.get("id"))
            
            # Check if we already have this execution
            existing = frappe.get_all("Playbook Execution", filters={"n8n_execution_id": n8n_execution_id}, limit=1)
            if existing:
                # Update status if needed
                status_map = {
                    "success": "success",
                    "error": "error",
                    "crashed": "error",
                    "canceled": "canceled",
                    "running": "running",
                    "waiting": "waiting"
                }
                new_status = status_map.get(exec_data.get("status"), "running")
                
                doc = frappe.get_doc("Playbook Execution", existing[0].name)
                if doc.status != new_status:
                    doc.status = new_status
                    doc.save(ignore_permissions=True)
                    frappe.db.commit()
                continue
                
            # If not, try to find the Playbook Execution by CloudEvent ID
            if exec_data.get("mode") == "webhook":
                run_data = exec_data.get("data", {}).get("resultData", {}).get("runData", {})
                for node_name, node_runs in run_data.items():
                    if "Webhook" in node_name:
                        try:
                            node_output = node_runs[0]["data"]["main"][0][0]["json"]
                            # CloudEvent ID is at top level, or inside 'body' if n8n wraps it
                            execution_name = node_output.get("name")
                            if not execution_name and node_output.get("body"):
                                payload = node_output.get("body")
                                if isinstance(payload, str):
                                    import json
                                    try:
                                        payload = json.loads(payload)
                                    except Exception:
                                        payload = {}
                                if isinstance(payload, dict):
                                    execution_name = payload.get("name")

                            if execution_name:
                                # Try to find by name first (for backward compatibility)
                                doc_name = None
                                if frappe.db.exists("Playbook Execution", execution_name):
                                    doc_name = execution_name
                                else:
                                    # Try to find by idempotency_key
                                    res = frappe.get_all("Playbook Execution", filters={"idempotency_key": execution_name}, limit=1)
                                    if res:
                                        doc_name = res[0].name
                                    else:
                                        # If not found, it might be because the record hasn't been committed yet.
                                        # Wait for it to be created if it's a recent execution.
                                        from frappe.utils import now_datetime, add_minutes, get_datetime
                                        started_at = get_datetime(exec_data.get("startedAt"))
                                        if started_at and started_at > add_minutes(now_datetime(), -10):
                                            from frappe_controller.utils.controller import wait_for_event
                                            wait_for_event(
                                                event_key="doc:Playbook Execution:after_insert",
                                                condition=f"doc.name == '{execution_name}' or doc.idempotency_key == '{execution_name}'"
                                            )

                                if doc_name:
                                    status_map = {
                                        "success": "success",
                                        "error": "error",
                                        "crashed": "error",
                                        "canceled": "canceled",
                                        "running": "running",
                                        "waiting": "waiting"
                                    }
                                    new_status = status_map.get(exec_data.get("status"), "running")
                                    
                                    doc = frappe.get_doc("Playbook Execution", doc_name)
                                    doc.n8n_execution_id = n8n_execution_id
                                    doc.status = new_status
                                    doc.save(ignore_permissions=True)
                                    frappe.db.commit()
                        except Exception:
                            pass
                        break
                        
    except Exception as e:
        frappe.log_error(f"Failed to retrieve n8n executions: {e}", "n8n Sync Error")
        raise

def poll_executions():
    settings = frappe.get_single("n8n Settings")
    if not settings.enabled or not settings.base_url or not settings.api_key:
        return
        
    executions = frappe.get_all(
        "Playbook Execution",
        filters={
            "status": ["in", ["running", "waiting"]]
        },
        fields=["name", "n8n_execution_id", "status", "playbook"]
    )
    
    if not executions:
        return
        
    from frappe_playbook.playbook.doctype.playbook_provider.playbook_provider import get_provider_instance
    provider = get_provider_instance("n8n")
    
    playbooks_to_retrieve = set()
    
    for execution in executions:
        if not execution.n8n_execution_id:
            playbooks_to_retrieve.add(execution.playbook)
            continue
            
        try:
            exec_data = provider.get_execution_status(execution.n8n_execution_id)
            if not exec_data:
                continue
                
            status_map = {
                "success": "success",
                "error": "error",
                "crashed": "error",
                "canceled": "canceled",
                "running": "running",
                "waiting": "waiting"
            }
            new_status = status_map.get(exec_data.get("status"), "running")
            
            if new_status != execution.status:
                doc = frappe.get_doc("Playbook Execution", execution.name)
                doc.status = new_status
                doc.save(ignore_permissions=True)
                frappe.db.commit()
                
        except Exception as e:
            frappe.log_error(f"Failed to poll n8n execution {execution.n8n_execution_id}: {e}", "n8n Polling Error")
            
    for playbook_name in playbooks_to_retrieve:
        try:
            retrieve_executions(playbook_name)
        except Exception as e:
            frappe.log_error(f"Failed to retrieve executions for playbook {playbook_name}: {e}", "n8n Polling Error")

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
        if error_execution_id:
            doc = frappe.get_doc("Playbook Execution", error_execution_id)
            doc.status = "error"
            doc.save(ignore_permissions=True)
            frappe.db.commit()
        raise
