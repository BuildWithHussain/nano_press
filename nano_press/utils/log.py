from typing import Union

import frappe
from frappe.model.document import Document
from frappe.utils import format_datetime, now_datetime


def _resolve_target(target: Document | tuple[str, str]) -> tuple[str, str, Document | None]:
	"""Accept a Document OR a (doctype, name) tuple."""
	if isinstance(target, Document):
		return target.doctype, target.name, target
	if isinstance(target, tuple | list) and len(target) == 2:
		doctype, name = target
		return doctype, name, None
	raise ValueError("target must be a Document or a (doctype, name) tuple")


def _trim_from_start(s: str, limit_bytes: int | None) -> str:
	if not limit_bytes:
		return s
	b = s.encode("utf-8")
	if len(b) <= limit_bytes:
		return s
	return b[-limit_bytes:].decode("utf-8", "ignore")


def append_long_text(
	target: Document | tuple[str, str],
	field: str,
	text: str,
	*,
	header_title: str = "Deploy Process Started",
	newest_on_top: bool = True,
	add_header: bool = True,
	trim_to_bytes: int | None = None,
	update_modified: bool = False,
	commit: bool = True,
	reflect_in_doc: bool = True,
) -> str:
	"""
	Append timestamped text to a Long Text-like field on ANY DocType.

	Args:
	    target: Document instance OR (doctype, name)
	    field: fieldname to append into (e.g. "deployment_log", "verification_log")
	    text: content to append (single event or multi-line)
	    header_title: title used in the header line
	    newest_on_top: if True, write at the top; else append at bottom
	    add_header: include "==== <title> at <timestamp> ====" header
	    trim_to_bytes: keep only the last N bytes (None disables trimming)
	    update_modified: pass through to frappe.db.set_value
	    commit: call frappe.db.commit() after write
	    reflect_in_doc: if target is a Document, also update the in-memory value

	Returns:
	    The new field value (after append/trim).
	"""
	doctype, name, doc = _resolve_target(target)

	# Validate the field exists on the DocType
	meta = frappe.get_meta(doctype)
	if not any(df.fieldname == field for df in meta.fields):
		raise ValueError(f"Field '{field}' not found in {doctype}")

	# Optional: you can restrict to text-like fieldtypes if you prefer:
	# allowed = {"Long Text", "Text", "Small Text", "Text Editor"}
	# df = next((df for df in meta.fields if df.fieldname == field), None)
	# if df and df.fieldtype not in allowed: raise ValueError(...)

	# Serialize concurrent writers (keeps event order)
	frappe.db.sql(f"SELECT name FROM `tab{doctype}` WHERE name=%s FOR UPDATE", (name,))

	ts = format_datetime(now_datetime())
	header = f"===== {header_title} at {ts} =====\n" if add_header else ""
	entry = f"{header}{text}".rstrip() + "\n"

	current = frappe.db.get_value(doctype, name, field) or ""
	new_val = (entry + current) if newest_on_top else (current + entry)
	new_val = _trim_from_start(new_val, trim_to_bytes)

	# Fast write (no Version doc), can avoid touching modified if desired
	frappe.db.set_value(doctype, name, field, new_val, update_modified=update_modified)

	if commit:
		frappe.db.commit()

	# Keep the passed-in Document's cache consistent (handy on forms)
	if reflect_in_doc and doc:
		try:
			doc.set(field, new_val)
		except Exception:
			pass

	return new_val


def clear_long_text(
	target: Document | tuple[str, str],
	field: str,
	*,
	update_modified: bool = False,
	commit: bool = True,
	reflect_in_doc: bool = True,
):
	"""Reset the given long text field to empty."""
	doctype, name, doc = _resolve_target(target)
	frappe.db.set_value(doctype, name, field, "", update_modified=update_modified)
	if commit:
		frappe.db.commit()
	if reflect_in_doc and doc:
		try:
			doc.set(field, "")
		except Exception:
			pass
