// Copyright (c) 2025, Venkatesh M and contributors
// For license information, please see license.txt

frappe.ui.form.on("Frappe Site", {
	refresh: function (frm) {
		// Add custom buttons to the form

		if (frm.doc.status == "Not Deployed") {
			frm.set_intro(
				"Click on Prepare for Deployment to start the deployment process",
				"info"
			);
		}

		if (frm.doc.status == "Deployed") {
			frm.set_intro(
				"Site is deployed. But the apps are in progress of being installed. So it may take a few minutes to be fully functional.",
				"yellow"
			);
		}

		frm.add_custom_button(__("Refresh"), () => {
			frm.reload_doc();
		});

		if (frm.doc.status == "Deployed") {
			frm.add_custom_button(__("Destroy Site"), function () {
				frappe.msgprint(__("Feature coming soon"));
			});
		}

		if (frm.doc.status == "Not Deployed") {
			frm.add_custom_button(__("Prepare for Deployment"), function () {
				prepare_for_deployment(frm);
			});
		}

		if (frm.doc.status == "Ready To Deploy") {
			frm.add_custom_button(__("Deploy"), function () {
				deploy_site(frm);
			});
		}

		if (frm.doc.status == "Deploying") {
			frm.add_custom_button(__("Cancel Deployment"), function () {
				frappe.msgprint(__("Feature to be implemented"));
			});
		}

		if (frm.doc.status == "Deployed") {
			frm.add_custom_button(__("View Site"), function () {
				if (frm.doc.server_name) {
					window.open(
						`https://${frm.doc.server_name}/login`,
						"_blank",
						"noopener,noreferrer"
					);
				} else {
					frappe.msgprint(__("Server name not found"));
				}
			});
		}

		if (frm.doc.status == "Failed" || frm.doc.status == "Stopped") {
			frm.add_custom_button(__("Retry Deployment"), function () {
				deploy_site(frm);
			});
		}

		if (frm.doc.status == "Deployed") {
			frm.add_custom_button(__("Stop All Containers"), function () {
				stop_all_containers(frm);
			}).addClass("btn-danger");
		}

		// Setup real-time notifications for deployment updates
		setup_deployment_notifications(frm);
	},
});

// Functions

function prepare_for_deployment(frm) {
	frappe.show_alert(
		"Server preparation has been initiated. Check the deployment log for progress.",
		5
	);
	frm.call("prepare_for_deployment")
		.then((r) => {
			if (r.message && r.message.status === 200) {
				frappe.msgprint(__("Deployment prepared successfully"));
				frm.reload_doc();
			} else {
				frappe.throw(
					(r.message && r.message.message) || __("Failed to prepare deployment")
				);
			}
		})
		.catch((e) => frappe.throw(e.message || e));
}

function deploy_site(frm) {
	frappe.show_alert("Server Deployment Started ....", 5);
	frm.call("frappe_site")
		.then((r) => {
			if (r.message && r.message.status === 200) {
				frappe.msgprint(__("Site deployed successfully"));
				frm.reload_doc();
			} else {
				frappe.throw((r.message && r.message.message) || __("Deployment failed"));
			}
		})
		.catch((e) => frappe.throw(e.message || e));
}

function stop_all_containers(frm) {
	frappe.warn(
		__("Stop All Containers"),
		__(
			"This will stop the running site and make it unavailable. You can restart it later using the Deploy button."
		),
		function () {
			frappe.show_alert("Stopping all containers...", 5),
				frm
					.call("stop_all_containers")
					.then((r) => {
						if (r.message && r.message.status === 200) {
							frappe.msgprint(r.message.message);
							frm.reload_doc();
						} else {
							frappe.throw((r.message && r.message.message) || __("Stop failed"));
						}
					})
					.catch((e) => frappe.throw(e.message || e));
		},
		__("Stop Containers"),
		true
	);
}

// Real-time notification setup for deployment
function setup_deployment_notifications(frm) {
	// Listen for deployment completion updates
	frappe.realtime.on("frappe_site_update", function (data) {
		if (data.frappe_site === frm.doc.name) {
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
				new Notification(`Frappe Site: ${frm.doc.site_name}`, {
					body: data.message,
					icon: "/assets/frappe/images/frappe-favicon.svg",
				});
			}
		}
	});

	// Listen for live deployment updates (real-time streaming)
	frappe.realtime.on("frappe_site_live_update", function (data) {
		console.log("Received live deployment update:", data);
		if (data.frappe_site === frm.doc.name) {
			// Update live deployment log in UI
			update_live_deployment_log(frm, data.log_line);

			// Auto-scroll to bottom if deployment log is visible
			auto_scroll_deployment_log();
		}
	});

	// Request notification permission
	if ("Notification" in window && Notification.permission === "default") {
		Notification.requestPermission();
	}
}

function update_live_deployment_log(frm, log_line) {
	console.log("Updating deployment log with:", log_line);

	// Find the deployment_log field and append new line
	const deployment_log_field = frm.get_field("deployment_log");
	if (deployment_log_field) {
		const current_value = frm.doc.deployment_log || "";
		const new_value = current_value + log_line + "\n";

		// Update the field directly without triggering save
		frm.doc.deployment_log = new_value;
		deployment_log_field.refresh();

		// Show live indicator
		show_live_deployment_indicator(frm, log_line);

		console.log("Deployment log updated successfully");
	} else {
		console.log("Deployment log field not found");
	}
}

function show_live_deployment_indicator(frm, latest_line) {
	// Show a small indicator with latest deployment activity
	if (
		latest_line.includes("TASK") ||
		latest_line.includes("Step") ||
		latest_line.includes("Pulling") ||
		latest_line.includes("Creating") ||
		latest_line.includes("Starting") ||
		latest_line.includes("Installing")
	) {
		frappe.show_alert(
			{
				message: `🚀 ${latest_line}`,
				indicator: "blue",
			},
			3
		);
	}
}

function auto_scroll_deployment_log() {
	// Auto-scroll deployment log textarea to bottom
	setTimeout(() => {
		const deployment_log_textarea = $('textarea[data-fieldname="deployment_log"]');
		if (deployment_log_textarea.length) {
			deployment_log_textarea.scrollTop(deployment_log_textarea[0].scrollHeight);
		}
	}, 100);
}
