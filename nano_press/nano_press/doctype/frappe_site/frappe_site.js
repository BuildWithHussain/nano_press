frappe.ui.form.on("Frappe Site", {
  refresh(frm) {
    frm.add_custom_button(__("Refresh"), () => frm.reload_doc());


    frm.add_custom_button(__("Prepare for Deployment"), () => call_doc_method(frm, "prepare_for_deployment")).addClass("btn-default");

    frm.add_custom_button(__("Deploy Site"), () => call_doc_method(frm, "queue_deploy_site")).addClass("btn-primary");

    frm.add_custom_button(__("Stop Containers"), () => call_doc_method(frm, "queue_stop_all_containers")).addClass("btn-danger");

    if (frm.doc.status === "Deployed") {
      if (frm.doc.site_url) {
        frm.add_custom_button(__("Visit Site"), () => window.open(frm.doc.site_url)).addClass("btn-info");
      } else if (!frm.doc.ssl_enabled && frm.doc.server_name) {
        // Fetch server doc to get IP
        frappe.db.get_doc("Server", frm.doc.server_name).then(server => {
          const ip = server.server_ip || "localhost";
          frm.add_custom_button(__("Visit Site (Insecure)"), () => window.open(`http://${ip}:8080`)).addClass("btn-warning");
        });
      }
    }
    if (frm.doc.admin_password) {
      // Add a clipboard icon to the label
      frm.fields_dict["admin_password"].set_label('Admin Password - <span class="fa fa-clipboard" title="Copy to Clipboard"></span>');

      // Bind click event to copy the value
      $(frm.fields_dict["admin_password"].label_area).on('click', function () {
        // Call server to get the admin password
        frappe.call({
          method: 'nano_press.get_admin_password',
          args: { site_name: frm.doc.name },
          callback: function (r) {
            if (r.message) {
              navigator.clipboard.writeText(r.message)
                .then(function () {
                  frappe.msgprint('Admin password copied to clipboard!');
                })
                .catch(function (error) {
                  frappe.msgprint('Error copying password: ' + error);
                });
            } else {
              frappe.msgprint('Could not retrieve admin password.');
            }
          }
        });
      });
    }

  }
});


function call_doc_method(frm, method_name) {
  if (!frm.doc.name) {
    frappe.msgprint(__("Please save the document before calling this action."));
    return;
  }

  frappe.show_alert({ message: __("Processing..."), indicator: "blue" }, 3);

  frm.call(method_name)
    .then((r) => {
      const msg = r?.message || {};
      const display = (typeof msg === "string") ? msg : (msg.job_id || msg.message || JSON.stringify(msg));
      frappe.show_alert({ message: __("Result: {0}", [display]), indicator: "green" }, 6);
      frm.reload_doc();
    })
    .catch((err) => {
      console.error(err);
      frappe.msgprint(err?.message || __("Server call failed"));
    });
}