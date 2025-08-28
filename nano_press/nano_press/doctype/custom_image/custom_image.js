// Copyright (c) 2025, Venkatesh M and contributors
// For license information, please see license.txt

frappe.ui.form.on("Custom Image", {
	refresh: function (frm) {
		// Add Preview Apps JSON button
		if (frm.doc.apps_config && frm.doc.apps_config.length > 0) {
			frm.add_custom_button(
				__("Preview Apps JSON"),
				function () {
					preview_apps_json(frm);
				},
				__("Actions")
			);
		}

		// Add Build Image button if not building
		if (frm.doc.server_name && frm.doc.build_status !== "Building") {
			frm.add_custom_button(
				__("Build Image"),
				function () {
					build_custom_image(frm);
				},
				__("Actions")
			);
		}

		// Show build status indicator
		if (frm.doc.build_status) {
			show_build_status_indicator(frm);
		}

		// Setup real-time notifications
		setup_realtime_notifications(frm);
	},

	apps_config: function (frm) {
		// Refresh buttons when apps config changes
		frm.trigger("refresh");
	},
});

function preview_apps_json(frm) {
	frappe.call({
		method: "preview_apps_json_for_form",
		doc: frm.doc,
		callback: function (r) {
			if (r.message && r.message.success) {
				const data = r.message;

				// Create dialog to show preview
				const dialog = new frappe.ui.Dialog({
					title: __("Apps JSON Preview"),
					size: "large",
					fields: [
						{
							fieldtype: "HTML",
							fieldname: "apps_summary",
							label: __("Apps Summary"),
						},
						{
							fieldtype: "Code",
							fieldname: "apps_json",
							label: __("Generated apps.json"),
							options: "JSON",
							read_only: 1,
						},
						{
							fieldtype: "Small Text",
							fieldname: "base64_preview",
							label: __("Base64 (first 200 chars)"),
							read_only: 1,
						},
					],
				});

				// Build apps summary HTML
				let summary_html = `<div class="apps-summary">
					<p><strong>Total Apps:</strong> ${data.app_count}</p>
					<table class="table table-bordered">
						<thead>
							<tr>
								<th>App Name</th>
								<th>Repository</th>
								<th>Branch</th>
							</tr>
						</thead>
						<tbody>`;

				data.apps_summary.forEach((app) => {
					summary_html += `
						<tr>
							<td><code>${app.name}</code></td>
							<td><small>${app.url}</small></td>
							<td><span class="badge badge-info">${app.branch}</span></td>
						</tr>`;
				});

				summary_html += `</tbody></table></div>`;

				// Set dialog values
				dialog.set_value("apps_summary", summary_html);
				dialog.set_value("apps_json", data.apps_json);
				dialog.set_value(
					"base64_preview",
					data.apps_json_base64.substring(0, 200) + "..."
				);

				dialog.show();
			} else {
				frappe.msgprint({
					title: __("Preview Failed"),
					message: r.message
						? r.message.error
						: __("Failed to generate apps.json preview"),
					indicator: "red",
				});
			}
		},
	});
}

function build_custom_image(frm) {
	// Show confirmation dialog
	frappe.confirm(
		__(
			"This will build the custom Docker image on the linked server. This process may take 10-30 minutes. Continue?"
		),
		function () {
			// Start build process
			frappe.call({
				method: "nano_press.nano_press.utils.remote_builder.trigger_remote_build",
				args: {
					custom_image_name: frm.doc.name,
				},
				callback: function (r) {
					if (r.message && r.message.success) {
						frappe.msgprint({
							title: __("Build Started"),
							message: __(
								"Image build has been initiated. Check the build log for progress."
							),
							indicator: "green",
						});
						frm.reload_doc();
					} else {
						frappe.msgprint({
							title: __("Build Failed"),
							message: r.message
								? r.message.error
								: __("Failed to start image build"),
							indicator: "red",
						});
					}
				},
			});
		}
	);
}

function show_build_status_indicator(frm) {
	const status = frm.doc.build_status;
	let indicator_color = "gray";
	let message = status;

	switch (status) {
		case "Building":
			indicator_color = "orange";
			message = __("Build in Progress...");
			break;
		case "Built":
			indicator_color = "green";
			message = __("Image Built Successfully");
			break;
		case "Failed":
			indicator_color = "red";
			message = __("Build Failed");
			break;
		case "Draft":
			indicator_color = "gray";
			message = __("Ready to Build");
			break;
	}

	frm.dashboard.add_indicator(message, indicator_color);
}

function setup_realtime_notifications(frm) {
	// Listen for build completion updates
	frappe.realtime.on("custom_image_build_update", function (data) {
		if (data.custom_image === frm.doc.name) {
			// Show notification
			frappe.show_alert(
				{
					message: data.message,
					indicator: data.status === "success" ? "green" : "red",
				},
				5
			);

			// Refresh form to show updated status
			frm.reload_doc();

			// Show desktop notification if supported
			if ("Notification" in window && Notification.permission === "granted") {
				new Notification(`Custom Image: ${frm.doc.image_name}`, {
					body: data.message,
					icon: "/assets/frappe/images/frappe-favicon.svg",
				});
			}
		}
	});

	// Listen for live build updates (real-time streaming)
	frappe.realtime.on("custom_image_build_live_update", function (data) {
		console.log("Received live update:", data); // Debug log
		if (data.custom_image === frm.doc.name) {
			// Update live build log in UI
			update_live_build_log(frm, data.log_line);

			// Auto-scroll to bottom if build log is visible
			auto_scroll_build_log();
		}
	});

	// Request notification permission
	if ("Notification" in window && Notification.permission === "default") {
		Notification.requestPermission();
	}
}

function update_live_build_log(frm, log_line) {
	console.log("Updating build log with:", log_line); // Debug log

	// Find the build_log field and append new line
	const build_log_field = frm.get_field("build_log");
	if (build_log_field) {
		const current_value = frm.doc.build_log || "";
		const new_value = current_value + log_line + "\n";

		// Update the field directly without triggering save
		frm.doc.build_log = new_value;
		build_log_field.refresh();

		// Show live indicator
		show_live_build_indicator(frm, log_line);

		console.log("Build log updated successfully"); // Debug log
	} else {
		console.log("Build log field not found"); // Debug log
	}
}

function show_live_build_indicator(frm, latest_line) {
	// Show a small indicator with latest build activity
	if (
		latest_line.includes("TASK") ||
		latest_line.includes("Step") ||
		latest_line.includes("Pulling")
	) {
		frappe.show_alert(
			{
				message: `🔨 ${latest_line}`,
				indicator: "blue",
			},
			3
		);
	}
}

function auto_scroll_build_log() {
	// Auto-scroll build log textarea to bottom
	setTimeout(() => {
		const build_log_textarea = $('textarea[data-fieldname="build_log"]');
		if (build_log_textarea.length) {
			build_log_textarea.scrollTop(build_log_textarea[0].scrollHeight);
		}
	}, 100);
}
