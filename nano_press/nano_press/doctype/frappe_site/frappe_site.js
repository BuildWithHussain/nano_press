frappe.ui.form.on('Frappe Site', {
	refresh(frm) {
		if (frm.doc.status === 'Not Deployed') {
			frm
				.add_custom_button(__('Prepare for Deployment'), () =>
					call_doc_method(frm, 'prepare_for_deployment'),
				)
				.addClass('btn-default');
		} else if (frm.doc.status === 'Ready To Deploy') {
			frm
				.add_custom_button(__('Deploy Site'), () =>
					call_doc_method(frm, 'deploy_site'),
				)
				.addClass('btn-primary');
		} else if (frm.doc.status === 'Deployed') {
			frm
				.add_custom_button(__('Stop Containers'), () =>
					call_doc_method(frm, 'stop_site'),
				)
				.addClass('btn-danger');
			frm
				.add_custom_button(__('Restart Containers'), () =>
					call_doc_method(frm, 'restart_site'),
				)
				.addClass('btn-warning');
			frm
				.add_custom_button(__('Visit Site'), () =>
					window.open(`https://${frm.doc.site_url}`),
				)
				.addClass('btn-info');
			frm.set_intro(
				`The site has been successfully deployed and will soon be accessible at:
        <strong>https://${frm.doc.site_url}</strong>.
        Please note that deployment time may vary depending on the number of applications being installed.
        Typically, the first app becomes available within 5 minutes.
        If the site remains inaccessible after 10 minutes, you are advised to restart the containers.`,
				'yellow',
			);
		} else if (frm.doc.status === 'Stopped') {
			frm
				.add_custom_button(__('Deploy Site'), () =>
					call_doc_method(frm, 'deploy_site'),
				)
				.addClass('btn-primary');
			frm
				.add_custom_button(__('Remove Site'), () => {
					frappe.confirm(
						__(
							'Are you sure you want to remove this site? This action cannot be undone.',
						),
						() => call_doc_method(frm, 'remove_site'),
					);
				})
				.addClass('btn-danger');
		} else if (!frm.doc.ssl_enabled && frm.doc.server_name) {
			frappe.db.get_doc('Server', frm.doc.server_name).then((server) => {
				const ip = server.server_ip || 'localhost';
				frm
					.add_custom_button(__('Visit Site (Insecure)'), () =>
						window.open(`http://${ip}:8080`),
					)
					.addClass('btn-warning');
			});
		} else if (frm.doc.status === 'Failed') {
			frm
				.add_custom_button(__('Retry Deployment'), () =>
					call_doc_method(frm, 'prepare_for_deployment'),
				)
				.addClass('btn-default');
		}

		// (Re)bind clipboard handlers safely on every refresh
		bind_clipboard_handlers(frm);
	},
});

function bind_clipboard_handlers(frm) {
	const hasCreds = frm.doc.admin_password && frm.doc.username;
	const pwdField = frm.fields_dict.admin_password;
	const userField = frm.fields_dict.username;
	if (!hasCreds || !pwdField || !userField) return;

	// Set labels once per form lifetime
	if (!pwdField._label_patched) {
		pwdField.set_label(
			'Admin Password - <span class="fa fa-clipboard" title="Copy to Clipboard"></span>',
		);
		userField.set_label(
			'Admin Username - <span class="fa fa-clipboard" title="Copy to Clipboard"></span>',
		);
		pwdField._label_patched = true;
		userField._label_patched = true;
	}

	// Always remove old handlers before adding new ones (use event namespaces)
	$(pwdField.label_area)
		.off('click.copy') // prevent duplicates
		.on('click.copy', () => {
			frappe.call({
				method: 'nano_press.get_admin_password',
				args: { site_name: frm.doc.name },
				callback: (r) => {
					const val = r?.message;
					if (val) {
						navigator.clipboard
							.writeText(val)
							.then(() =>
								frappe.show_alert(__('Admin password copied to clipboard!')),
							)
							.catch((error) =>
								frappe.show_alert(__('Error copying password: {0}', [error])),
							);
					} else {
						frappe.show_alert(__('Could not retrieve admin password.'));
					}
				},
			});
		});

	$(userField.label_area)
		.off('click.copy')
		.on('click.copy', () => {
			navigator.clipboard
				.writeText(frm.doc.username)
				.then(() => frappe.show_alert(__('Username copied to clipboard!')))
				.catch((error) =>
					frappe.show_alert(__('Error copying username: {0}', [error])),
				);
		});
}

function call_doc_method(frm, method_name) {
	if (!frm.doc.name) {
		frappe.msgprint(__('Please save the document before calling this action.'));
		return;
	}

	const actionLabels = {
		prepare_for_deployment: __('Prepare for Deployment'),
		deploy_site: __('Deploy Site'),
		stop_site: __('Stop Containers'),
		remove_site: __('Remove Site'),
	};
	const actionLabel = actionLabels[method_name] || method_name;
	frappe.show_alert(
		{ message: __('Processing: {0}', [actionLabel]), indicator: 'blue' },
		3,
	);

	frm
		.call(method_name)
		.then((r) => {
			const msg = r?.message || {};
			const display =
				typeof msg === 'string'
					? msg
					: msg.job_id || msg.message || JSON.stringify(msg);
			frappe.show_alert(
				{ message: __('Result: {0}', [display]), indicator: 'green' },
				6,
			);
			frm.reload_doc();
		})
		.catch((err) => {
			console.error(err);
			frappe.msgprint(err?.message || __('Server call failed'));
		});
}
