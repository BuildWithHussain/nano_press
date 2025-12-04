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
		cmd_val = None
		if result_json.get("cmd"):
			cmd_val = result_json["cmd"]
		else:
			raw = result_json.get("raw_json", {})
			for play in raw.get("plays", []):
				for task in play.get("tasks", []):
					hosts = task.get("hosts", {})
					for _h, host_data in hosts.items():
						if "cmd" in host_data:
							cmd_val = host_data["cmd"]
							break
					if cmd_val:
						break
				if cmd_val:
					break

		doc.stdout_tail = result_json.get("stdout_tail") or result_json.get("data", {}).get("stdout_tail")
		doc.stderr_tail = result_json.get("stderr_tail") or result_json.get("data", {}).get("stderr_tail")

		summary = None
		# e.g. summary under result_json["data"]["summary"] or result_json["summary"] or raw_json["stats"]
		if result_json.get("data", {}).get("summary"):
			summary = result_json["data"]["summary"]
		elif result_json.get("summary"):
			summary = result_json["summary"]
		elif result_json.get("raw_json", {}).get("stats"):
			summary = result_json["raw_json"]["stats"]

		if summary is not None:
			doc.output = frappe.as_json(summary)

		doc.insert(ignore_permissions=True)
		frappe.db.commit()
		return doc.name

	except Exception:
		frappe.log_error(frappe.get_traceback(), "AnsibleLog Insertion Error")
		return None
