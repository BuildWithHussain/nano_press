// Copyright (c) 2025, Venkatesh M and contributors
// For license information, please see license.txt

frappe.ui.form.on('Server', {
	refresh(frm) {
		// avoid duplicate buttons
		if (frm.clear_custom_buttons) frm.clear_custom_buttons();

		// only add action buttons for saved docs
		if (!frm.is_new()) {
			// Show Deploy Traefik button when server is prepared
			if (frm.doc.verify_status === 'Prepared' && !frm.doc.traefik_deployed) {
				frm
					.add_custom_button('Deploy Traefik', () => {
						// Validate required fields before calling
						if (
							!frm.doc.traefik_domain ||
							!frm.doc.traefik_email ||
							!frm.doc.traefik_username ||
							!frm.doc.traefik_password
						) {
							frappe.msgprint({
								title: __('Missing Information'),
								indicator: 'orange',
								message: __(
									'Please fill in all Traefik fields: Domain, Email, Username, and Password',
								),
							});
							return;
						}

						frappe.call({
							method:
								'nano_press.nano_press.doctype.server.server.deploy_traefik',
							args: {
								server_name: frm.doc.name,
							},
							callback: (r) => {
								if (r?.message) {
									if (r.message.status === 200) {
										frappe.show_alert({
											message: `Traefik deployed successfully on ${r.message.traefik_domain}`,
											indicator: 'green',
										});
									} else {
										frappe.show_alert({
											message: 'Traefik deployment failed',
											indicator: 'red',
										});
									}
									frm.reload_doc();
								}
							},
						});
					})
					.addClass('btn-primary');
			}

			if (
				frm.doc.verify_status === 'Verified' ||
				frm.doc.verify_status === 'Prepared'
			) {
				// Only show Prepare when verified
				frm
					.add_custom_button('Prepare Server', () => {
						// Warn if server is already prepared
						if (frm.doc.verify_status === 'Prepared') {
							frappe.confirm(
								'This server is already prepared. Do you want to prepare it again?',
								() => {
									// User confirmed - proceed with preparation
									frm.set_value('verify_status', 'Preparing');
									frappe.call({
										method:
											'nano_press.nano_press.doctype.server.server.prepare_server',
										args: {
											server_name: frm.doc.name,
										},
										callback: (r) => {
											console.log(r);
											if (r?.message) {
												if (r.message.status === 200) {
													frappe.show_alert({
														message: 'Server prepared successfully',
														indicator: 'green',
													});
												} else {
													frappe.show_alert({
														message: 'Server preparation failed',
														indicator: 'red',
													});
												}
												frm.reload_doc();
											}
										},
									});
								},
								() => {
									// User cancelled - do nothing
									frappe.show_alert({
										message: 'Preparation cancelled',
										indicator: 'orange',
									});
								},
							);
						} else {
							// Server is only verified, not prepared yet - proceed directly
							frm.set_value('verify_status', 'Preparing');
							frappe.call({
								method:
									'nano_press.nano_press.doctype.server.server.prepare_server',
								args: {
									server_name: frm.doc.name,
								},
								callback: (r) => {
									console.log(r);
									if (r?.message) {
										if (r.message.status === 200) {
											frappe.show_alert({
												message: 'Server prepared successfully',
												indicator: 'green',
											});
										} else {
											frappe.show_alert({
												message: 'Server preparation failed',
												indicator: 'red',
											});
										}
										frm.reload_doc();
									}
								},
							});
						}
					})
					.addClass('btn-primary');
			} else {
				// Not verified yet → show Verify button
				frm
					.add_custom_button('Verify Server', () => {
						frm.set_value('verify_status', 'Verifying');
						frappe.call({
							method: 'nano_press.utils.ansible_runner.ping_server',
							args: { host: frm.doc.server_ip },
							callback: (r) => {
								if (r?.message) {
									if (r.message.status === 'success') {
										frappe.show_alert({
											message: 'Server verified',
											indicator: 'green',
										});
									} else {
										frm.set_value('verify_status', 'Failed');
										frappe.show_alert({
											message: 'Verification failed',
											indicator: 'red',
										});
									}
									frm.reload_doc();
								}
							},
						});
					})
					.addClass('btn-primary');
			}
		}

		// Render public key HTML & copy handler
		frappe.call({
			method: 'nano_press.nano_press.doctype.server.server.get_public_key_html',
			callback: (r) => {
				if (r?.message && frm.fields_dict.public_key) {
					frm.fields_dict.public_key.$wrapper.html(r.message);
					const btn = frm.fields_dict.public_key.$wrapper.find(
						'#copy-public-key-btn',
					);
					btn?.on('click', async () => {
						const text = frm.fields_dict.public_key.$wrapper
							.find('#server-public-key')
							.text();
						try {
							await navigator.clipboard.writeText(text);
						} catch (e) {
							const ta = document.createElement('textarea');
							ta.value = text;
							document.body.appendChild(ta);
							ta.select();
							document.execCommand('copy');
							document.body.removeChild(ta);
						}
						frappe.show_alert({
							message: 'Public key copied',
							indicator: 'green',
						});
					});
				}
			},
		});
	},
});
