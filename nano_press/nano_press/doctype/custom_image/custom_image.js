// Copyright (c) 2025, Venkatesh M
// For license information, please see license.txt

frappe.ui.form.on('Custom Image', {
	refresh(frm) {
		// Add Preview Apps JSON button
		if (frm.doc.apps_config && frm.doc.apps_config.length > 0) {
			frm.add_custom_button(
				__('Preview Apps JSON'),
				() => preview_apps_json(frm),
				__('Actions'),
			);
		}

		// Add Build Image button if not already building
		if (frm.doc.server_name && frm.doc.build_status !== 'Building') {
			frm.add_custom_button(
				__('Build Image'),
				() => build_custom_image(frm),
				__('Actions'),
			);
		}

		// Add standalone Refresh button (outside grouped actions)
		frm.add_custom_button(__('Refresh'), () => frm.reload_doc());

		// Show current build status indicator
		if (frm.doc.build_status) {
			show_build_status_indicator(frm);
		}
	},

	apps_config(frm) {
		frm.trigger('refresh');
	},
});

function build_custom_image(frm) {
	frappe.confirm(
		__(
			'This will build the custom Docker image on the linked server. This process may take 10–30 minutes. Continue?',
		),
		() => {
			frappe.call({
				method: 'enqueue_build_custom_image',
				doc: frm.doc,
				callback: (r) => {
					if (r.message && r.message.status === 'queued') {
						frappe.msgprint({
							title: __('Build Started'),
							message: __(
								'Image build has been queued successfully. Check the build log for progress.',
							),
							indicator: 'green',
						});
						frm.reload_doc(); // Fetch updated status from backend
					} else {
						frappe.msgprint({
							title: __('Build Failed'),
							message:
								r.message?.error ||
								__('Failed to enqueue the image build process.'),
							indicator: 'red',
						});
					}
				},
			});
		},
	);
}

function show_build_status_indicator(frm) {
	const status = frm.doc.build_status;
	let color;
	let message;

	switch (status) {
		case 'Building':
			color = 'orange';
			message = __('Build in Progress...');
			break;
		case 'Built':
			color = 'green';
			message = __('Image Built Successfully');
			break;
		case 'Failed':
			color = 'red';
			message = __('Build Failed');
			break;
		default:
			color = 'gray';
			message = __('Ready to Build');
			break;
	}

	frm.dashboard.add_indicator(message, color);
}

function preview_apps_json(frm) {
	frappe.call({
		method: 'preview_apps_json_for_form',
		doc: frm.doc,
		callback: (r) => {
			if (r.message?.success) {
				const data = r.message;
				const dialog = new frappe.ui.Dialog({
					title: __('Apps JSON Preview'),
					size: 'large',
					fields: [
						{
							fieldtype: 'HTML',
							fieldname: 'apps_summary',
							label: __('Apps Summary'),
						},
						{
							fieldtype: 'Code',
							fieldname: 'apps_json',
							label: __('Generated apps.json'),
							options: 'JSON',
							read_only: 1,
						},
						{
							fieldtype: 'Small Text',
							fieldname: 'base64_preview',
							label: __('Base64 (first 200 chars)'),
							read_only: 1,
						},
					],
				});

				let summary_html = `<div class="apps-summary">
					<p><strong>Total Apps:</strong> ${data.app_count}</p>
					<table class="table table-bordered">
						<thead><tr><th>App Name</th><th>Repository</th><th>Branch</th></tr></thead>
						<tbody>`;

				for (const app of data.apps_summary) {
					summary_html += `
						<tr>
							<td><code>${app.name}</code></td>
							<td><small>${app.url}</small></td>
							<td><span class="badge badge-info">${app.branch}</span></td>
						</tr>`;
				}

				summary_html += '</tbody></table></div>';

				dialog.set_value('apps_summary', summary_html);
				dialog.set_value('apps_json', data.apps_json);
				dialog.set_value(
					'base64_preview',
					`${data.apps_json_base64.substring(0, 200)}...`,
				);
				dialog.show();
			} else {
				frappe.msgprint({
					title: __('Preview Failed'),
					message:
						r.message?.error || __('Failed to generate apps.json preview'),
					indicator: 'red',
				});
			}
		},
	});
}
