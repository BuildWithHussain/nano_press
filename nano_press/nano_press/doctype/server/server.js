// Copyright (c) 2025, Venkatesh M and contributors
// For license information, please see license.txt

frappe.ui.form.on('Server', {
	refresh(frm) {
		// avoid duplicate buttons
		if (frm.clear_custom_buttons) frm.clear_custom_buttons();

		// only add action buttons for saved docs
		if (!frm.is_new()) {
			// Show Prepare Server button with option to include Traefik
			if (
				frm.doc.verify_status === 'Verified' ||
				frm.doc.verify_status === 'Prepared'
			) {
				// Only show Prepare when verified or already prepared
				frm
					.add_custom_button('Prepare Server', () => {
						// Check if server is already prepared
						if (frm.doc.verify_status === 'Prepared') {
							frappe.confirm(
								'This server is already prepared. Do you want to prepare it again?',
								() => {
									// User confirmed - show options dialog
									show_preparation_dialog(frm);
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
							// Server is only verified, not prepared yet - show options directly
							show_preparation_dialog(frm);
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

// Helper function to show preparation options dialog
function show_preparation_dialog(frm) {
	const d = new frappe.ui.Dialog({
		title: 'Prepare Server',
		fields: [
			{
				label: 'Preparation Options',
				fieldname: 'preparation_info',
				fieldtype: 'HTML',
				options: `
					<div class="alert alert-info">
						<strong>What will be installed:</strong>
						<ul>
							<li>Docker (if not already installed)</li>
							<li>Docker Compose (if not already installed)</li>
							<li>Traefik (optional - only if enabled below)</li>
						</ul>
						<small>The system will check for existing installations and skip them.</small>
					</div>
				`,
			},
			{
				label: 'Include Traefik',
				fieldname: 'include_traefik',
				fieldtype: 'Check',
				description: 'Also deploy Traefik reverse proxy with SSL support',
				default: 0,
				onchange: () => {
					// Show/hide Traefik fields based on checkbox
					const include = d.get_value('include_traefik');
					d.get_field('traefik_section').df.hidden = !include;
					d.refresh();
				},
			},
			{
				fieldname: 'traefik_section',
				fieldtype: 'Section Break',
				label: 'Traefik Configuration',
				hidden: 1,
			},
			{
				label: 'Domain',
				fieldname: 'traefik_domain',
				fieldtype: 'Data',
				reqd: 0,
				default: frm.doc.traefik_domain || '',
				description: 'Domain for Traefik dashboard (e.g., traefik.example.com)',
			},
			{
				label: 'Email',
				fieldname: 'traefik_email',
				fieldtype: 'Data',
				reqd: 0,
				default: frm.doc.traefik_email || '',
				description: "Email for Let's Encrypt SSL certificates",
			},
			{
				fieldname: 'col_break_1',
				fieldtype: 'Column Break',
			},
			{
				label: 'Username',
				fieldname: 'traefik_username',
				fieldtype: 'Data',
				reqd: 0,
				default: frm.doc.traefik_username || 'admin',
				description: 'Username for Traefik dashboard',
			},
			{
				label: 'Password',
				fieldname: 'traefik_password',
				fieldtype: 'Password',
				reqd: 0,
				default: frm.doc.traefik_password || '',
				description: 'Password for Traefik dashboard',
			},
		],
		primary_action_label: 'Prepare Server',
		primary_action(values) {
			// Validate Traefik fields if Traefik is enabled
			if (values.include_traefik) {
				if (
					!values.traefik_domain ||
					!values.traefik_email ||
					!values.traefik_username ||
					!values.traefik_password
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

				// Save Traefik fields to the form
				frm.set_value('traefik_domain', values.traefik_domain);
				frm.set_value('traefik_email', values.traefik_email);
				frm.set_value('traefik_username', values.traefik_username);
				frm.set_value('traefik_password', values.traefik_password);
			}

			d.hide();
			frm.set_value('verify_status', 'Preparing');

			// Show progress message
			frappe.show_alert({
				message: values.include_traefik
					? 'Preparing server with Docker and Traefik...'
					: 'Preparing server with Docker...',
				indicator: 'blue',
			});

			// Call the unified prepare_server API
			frappe.call({
				method: 'nano_press.nano_press.doctype.server.server.prepare_server',
				args: {
					server_name: frm.doc.name,
					include_traefik: values.include_traefik ? 1 : 0,
				},
				freeze: true,
				freeze_message: 'Preparing server, please wait...',
				callback: (r) => {
					console.log(r);
					if (r?.message) {
						if (r.message.status === 200) {
							let message = r.message.message || 'Server prepared successfully';

							// Show detailed success message
							if (values.include_traefik && r.message.traefik_version) {
								message = `Server prepared successfully!<br>
									Docker: ${r.message.docker_version}<br>
									Compose: ${r.message.compose_version}<br>
									Traefik: ${r.message.traefik_version}<br>
									Domain: ${r.message.traefik_domain}`;
							} else {
								message = `Server prepared successfully!<br>
									Docker: ${r.message.docker_version}<br>
									Compose: ${r.message.compose_version}`;
							}

							frappe.msgprint({
								title: __('Success'),
								indicator: 'green',
								message: __(message),
							});
						} else {
							frappe.msgprint({
								title: __('Failed'),
								indicator: 'red',
								message: __('Server preparation failed'),
							});
						}
						frm.reload_doc();
					}
				},
				error: (r) => {
					frappe.msgprint({
						title: __('Error'),
						indicator: 'red',
						message: __(
							'Server preparation failed. Check error log for details.',
						),
					});
					frm.reload_doc();
				},
			});
		},
	});

	d.show();
}
