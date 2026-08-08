"""Small, repeatable local ERPNext seed; loaded into the container at runtime."""
import os

import frappe


def _insert(doctype, values):
    name = values.get("name")
    if name and frappe.db.exists(doctype, name):
        return frappe.get_doc(doctype, name)
    doc = frappe.get_doc({"doctype": doctype, **values})
    doc.insert(ignore_permissions=True)
    return doc


def run():
    if os.getenv("SEED_ENABLED", "false").lower() != "true":
        print("Seed disabled")
        return
    company_name = os.environ["COMPANY_NAME"]
    abbr = os.environ["COMPANY_ABBR"]
    company = _insert("Company", {
        "name": company_name, "company_name": company_name, "abbr": abbr,
        "country": frappe.conf.get("country", "Vietnam"),
        "default_currency": frappe.conf.get("currency", "VND"),
        "domain": os.environ["COMPANY_DOMAIN"],
    })
    _insert("Cost Center", {
        "name": f"{company.name} - {abbr}", "cost_center_name": "Main Cost Center",
        "company": company.name, "is_group": 0,
    })
    _insert("Warehouse", {
        "name": os.environ["WAREHOUSE_NAME"],
        "warehouse_name": os.environ["WAREHOUSE_NAME"], "company": company.name,
    })
    frappe.db.commit()
    print(f"Seed complete (company={company.name}, warehouse={os.environ['WAREHOUSE_NAME']})")
