import frappe

def on_update(doc, method=None):
    if doc.status == "Closed" and doc.has_value_changed("status") and doc.playbook_execution:
        execution_doc = frappe.get_doc("Playbook Execution", doc.playbook_execution)
        playbook = frappe.db.get_value("Playbook", execution_doc.playbook, "provider")
        
        if playbook == "n8n":
            execution_name = frappe.generate_hash(f"{doc.name}-{doc.modified}", length=10)
            
            payload = doc.response_body or {}
            if isinstance(payload, str):
                try:
                    import json
                    payload = json.loads(payload)
                except Exception:
                    payload = {"data": payload}
            if execution_name:
                payload["execution_name"] = execution_name
                
            from frappe_controller.utils.background_jobs import enqueue
            enqueue("frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.resume_execution", url=doc.callback_url, payload=payload, execution_id=execution_doc.name)
