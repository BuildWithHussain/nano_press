# Copyright (c) 2025, Venkatesh M and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class AnsibleLog(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		bench_name: DF.Link | None
		command: DF.Text | None
		executed_on: DF.Datetime | None
		operation: DF.Literal["Playbook", "Ping", "Command", "Setup"]
		rc: DF.Int
		server_name: DF.Link | None
		site_name: DF.Data | None
		status: DF.Literal["Success", "Failed", "Unreachable", "Running"]
		triggered_by: DF.Link | None
	# end: auto-generated types

	pass


def log_ansible_result(
	result_json: dict,
	*,
	operation: str,
	server: str | None = None,
	bench: str | None = None,
	site: str | None = None,
) -> str | None:
	"""Create an Ansible Log entry matching the Ansible Log doctype fields."""
	try:
		doc = frappe.new_doc("Ansible Log")

		doc.operation = operation
		doc.server_name = server
		doc.bench_name = bench
		doc.site = site
		doc.status = "Success" if result_json.get("ok") else "Failed"
		doc.rc = int(result_json.get("rc", 1))
		doc.executed_on = frappe.utils.now_datetime()
		doc.triggered_by = getattr(frappe.session, "user", None)

		# Command text (best-effort from result payload)
		cmd_val = (result_json.get("raw_json", {}) or {}).get("cmd") or result_json.get("cmd") or ""
		if isinstance(cmd_val, list | tuple):
			doc.command = " ".join(map(str, cmd_val))
		else:
			doc.command = str(cmd_val)

		doc.insert(ignore_permissions=True)
		frappe.db.commit()
		return doc.name

	except Exception:
		frappe.log_error(frappe.get_traceback(), "AnsibleLog Insertion Error")
		return None
