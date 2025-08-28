# Copyright (c) 2025, Venkatesh M and contributors
# For license information, please see license.txt

import os
import subprocess

import frappe
from frappe.model.document import Document


class Server(Document):
	@staticmethod
	def _read_local_public_key() -> str | None:
		"""Attempt to read a usable SSH public key from standard locations.

		Returns the first available public key content, or None.
		"""
		candidate_paths = [
			os.path.expanduser(path)
			for path in [
				"~/.ssh/id_ed25519.pub",
				"~/.ssh/id_rsa.pub",
				"~/.ssh/id_ecdsa.pub",
				"~/.ssh/id_dsa.pub",
			]
		]
		for candidate in candidate_paths:
			try:
				if os.path.exists(candidate):
					with open(candidate) as fh:
						data = fh.read().strip()
						if data:
							return data
			except Exception:
				continue
		# Try deriving from private keys using ssh-keygen
		private_candidates = [
			os.path.expanduser(p)
			for p in [
				"~/.ssh/id_ed25519",
				"~/.ssh/id_rsa",
				"~/.ssh/id_ecdsa",
				"~/.ssh/id_dsa",
			]
		]
		for private_key in private_candidates:
			try:
				if os.path.exists(private_key):
					result = subprocess.run(
						["ssh-keygen", "-y", "-f", private_key],
						stdout=subprocess.PIPE,
						stderr=subprocess.DEVNULL,
						text=True,
						check=False,
					)
					pub = (result.stdout or "").strip()
					if pub:
						return pub
			except Exception:
				continue
		return None

	def _append_log(self, text: str) -> None:
		"""Append timestamped text to the Server.verification_log (newest at top)."""
		timestamp = frappe.utils.format_datetime(frappe.utils.now_datetime())
		header = f"\n\n===== Verification at {timestamp} =====\n"
		existing = self.get("verification_log") or ""
		self.verification_log = f"{header}{text}\n{existing}".strip()
		self.save(ignore_version=True)
		frappe.db.commit()


@frappe.whitelist()
def get_public_key_html() -> str:
	"""Render the server's local SSH public key as HTML instructions for the user.

	This reads a public key from the host running the Frappe app and returns an
	HTML snippet to show in the `public_key` HTML field.
	"""
	public_key = Server._read_local_public_key()
	if not public_key:
		return (
			'<div class="text-muted">No SSH public key found on the server. '
			"Ensure a key exists at ~/.ssh/id_ed25519.pub or ~/.ssh/id_rsa.pub.</div>"
		)

	html = f"""
        <div>
            <p><strong>Server Public Key</strong></p>
            <div style=\"margin: 6px 0;\">
                <button id=\"copy-public-key-btn\" type=\"button\" class=\"btn btn-sm btn-secondary\">Copy Public Key</button>
            </div>
            <pre id=\"server-public-key\" style=\"white-space: pre-wrap; word-break: break-all;\">{frappe.utils.escape_html(public_key)}</pre>
            <p>Copy the above key into <code>~/.ssh/authorized_keys</code> on your remote server.
            Ensure file permissions are correct and SSH is enabled for the configured user.</p>
        </div>
    """
	return html


@frappe.whitelist()
def run_ad_hoc_ping_api(name: str) -> dict:
	"""Run ad-hoc Ansible ping synchronously and update the Server doc.

	Returns a dict: {"success": bool, "last_verified_at": str|None}
	"""
	doc = frappe.get_doc("Server", name)

	# Set status to Verifying before running
	doc.verify_status = "Verifying"
	doc.save(ignore_version=True)
	frappe.db.commit()

	from nano_press.nano_press.utils.ansible_runner import run_ad_hoc_ping as _runner_ping

	try:
		output = _runner_ping(
			hostname=doc.server_ip,
			ssh_user=(doc.ssh_user or "root"),
			ssh_port=int(doc.ssh_port or 22),
		)
		doc._append_log(output)

		normalized = (output or "").upper()
		success = (
			("SUCCESS" in normalized) and ("UNREACHABLE" not in normalized) and ("FAILED" not in normalized)
		)

		if success:
			doc = frappe.get_doc("Server", name)
			doc.verify_status = "Verified"
			doc.last_verified_at = frappe.utils.now_datetime()
			doc.save(ignore_version=True)
			frappe.db.commit()
			return {
				"success": True,
				"last_verified_at": frappe.utils.format_datetime(doc.last_verified_at),
			}
		else:
			doc = frappe.get_doc("Server", name)
			doc.verify_status = "Failed"
			doc.save(ignore_version=True)
			frappe.db.commit()
			return {"success": False, "last_verified_at": None}
	except Exception as exc:
		doc = frappe.get_doc("Server", name)
		doc._append_log(f"Verification failed: {frappe.utils.cstr(exc)}")
		doc.verify_status = "Failed"
		doc.save(ignore_version=True)
		frappe.db.commit()
		return {"success": False, "last_verified_at": None}
