import frappe

@frappe.whitelist(allow_guest=True)
def callback(execution_name=None, **kwargs):
    payload = frappe.request.json if getattr(frappe, "request", None) and frappe.request.json else kwargs
    
    if not execution_name:
        execution_name = payload.get("name") or payload.get("execution_name") or frappe.form_dict.get("execution_name")
        
    if not execution_name:
        execution_name = frappe.generate_hash(length=10)
        
    is_test = str(execution_name).startswith("test-")
    
    DISALLOWED_FIELDS = {
        "name", "owner", "creation", "modified", "modified_by",
        "idx", "docstatus", "doctype", "playbook",
        "reference_doctype", "reference_name"
    }
    
    import json
    
    if is_test:
        playbook_name = payload.get("playbook")
        
        doc_data = {
            "doctype": "Playbook Execution",
            "name": execution_name,
            "playbook": playbook_name,
            "reference_doctype": payload.get("reference_doctype"),
            "reference_name": payload.get("reference_name"),
            "status": payload.get("status", "running"),
        }
        
        doc = frappe.get_doc(doc_data)
        
        for key, value in payload.items():
            if key in DISALLOWED_FIELDS:
                continue
            if doc.meta.has_field(key):
                if key == "execution_data" and isinstance(value, dict):
                    doc.set(key, json.dumps(value))
                else:
                    doc.set(key, value)
                    
        # Maintain backwards compatibility for the n8n execution ID
        if "execution" in payload and isinstance(payload["execution"], dict) and payload["execution"].get("id"):
            if doc.meta.has_field("n8n_execution_id"):
                doc.n8n_execution_id = str(payload["execution"]["id"])
                
        doc.run_method("validate")
        if hasattr(doc, "_validate_mandatory"):
            doc._validate_mandatory()
        
        return doc.as_dict()
        
    if not frappe.db.exists("Playbook Execution", execution_name):
        playbook_name = payload.get("playbook")
        if not playbook_name:
            frappe.throw("Execution not found and 'playbook' not provided in payload to create one.")
            
        doc = frappe.get_doc({
            "doctype": "Playbook Execution",
            "name": execution_name,
            "playbook": playbook_name,
            "reference_doctype": payload.get("reference_doctype"),
            "reference_name": payload.get("reference_name"),
            "status": payload.get("status", "running"),
        })
        
        if "execution_data" in payload and isinstance(payload["execution_data"], dict):
            doc.execution_data = json.dumps(payload["execution_data"])
            
        doc.insert(ignore_permissions=True)
    else:
        doc = frappe.get_doc("Playbook Execution", execution_name)
    
    for key, value in payload.items():
        if key in DISALLOWED_FIELDS:
            continue
        if doc.meta.has_field(key):
            if key == "execution_data" and isinstance(value, dict):
                doc.set(key, json.dumps(value))
            else:
                doc.set(key, value)
                
    # Maintain backwards compatibility for the n8n execution ID
    if "execution" in payload and isinstance(payload["execution"], dict) and payload["execution"].get("id"):
        if doc.meta.has_field("n8n_execution_id"):
            doc.n8n_execution_id = str(payload["execution"]["id"])
            
    doc.save(ignore_permissions=True)
    if not frappe.flags.in_test:
        frappe.db.commit()
    return doc.as_dict()
