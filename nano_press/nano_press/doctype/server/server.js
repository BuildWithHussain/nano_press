// Copyright (c) 2025, Venkatesh M and contributors
// For license information, please see license.txt

frappe.ui.form.on("Server", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button("Verify Server", () => {
				frm.set_value("verify_status", "Verifying");
				frappe.call({
					method: "nano_press.nano_press.doctype.server.server.run_ad_hoc_ping_api",
					args: { name: frm.doc.name },
					callback: (r) => {
						if (r && r.message) {
							if (r.message.success) {
								frm.set_value("verify_status", "Verified");
								if (r.message.last_verified_at) {
									frm.set_value("last_verified_at", r.message.last_verified_at);
								}
								frappe.show_alert({
									message: "Server verified",
									indicator: "green",
								});
							} else {
								frm.set_value("verify_status", "Failed");
								frappe.show_alert({
									message: "Verification failed",
									indicator: "red",
								});
							}
							frm.reload_doc();
						}
					},
				});
			}).addClass("btn-primary");
		}

		// render public key in the HTML field
		frappe.call({
			method: "nano_press.nano_press.doctype.server.server.get_public_key_html",
			callback: (r) => {
				if (r && r.message && frm.fields_dict.public_key) {
					frm.fields_dict.public_key.$wrapper.html(r.message);
					const btn = frm.fields_dict.public_key.$wrapper.find("#copy-public-key-btn");
					btn &&
						btn.on("click", async () => {
							const text = frm.fields_dict.public_key.$wrapper
								.find("#server-public-key")
								.text();
							try {
								await navigator.clipboard.writeText(text);
								frappe.show_alert({
									message: "Public key copied",
									indicator: "green",
								});
							} catch (e) {
								const ta = document.createElement("textarea");
								ta.value = text;
								document.body.appendChild(ta);
								ta.select();
								document.execCommand("copy");
								document.body.removeChild(ta);
								frappe.show_alert({
									message: "Public key copied",
									indicator: "green",
								});
							}
						});
				}
			},
		});
	},
});
