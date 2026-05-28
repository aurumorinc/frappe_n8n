import frappe

def after_install():
    if not frappe.db.exists("Playbook Provider", "n8n"):
        provider = frappe.get_doc({
            "doctype": "Playbook Provider",
            "provider_name": "n8n",
            "enabled": 0
        })
        provider.insert(ignore_permissions=True)
