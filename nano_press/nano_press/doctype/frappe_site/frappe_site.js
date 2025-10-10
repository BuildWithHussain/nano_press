frappe.ui.form.on("Frappe Site", {
  refresh(frm) {
    frm.add_custom_button(__("Refresh"), () => frm.reload_doc());

    if (frm.doc.status === "Not Deployed") {
      frm.add_custom_button(__("Prepare for Deployment"), () => call_doc_method(frm, "prepare_for_deployment")).addClass("btn-default");
    } else if (frm.doc.status === "Ready To Deploy") {
      frm.add_custom_button(__("Deploy Site"), () => call_doc_method(frm, "deploy_site")).addClass("btn-primary");
    } else if (frm.doc.status === "Deployed") {
      frm.add_custom_button(__("Stop Containers"), () => call_doc_method(frm, "stop_site")).addClass("btn-danger");
      frm.add_custom_button(__("Visit Site"), () => window.open(`https://${frm.doc.site_name}`)).addClass("btn-info");
      if (frm.doc.status === "Stopped") {
        frm.add_custom_button(__("Deploy Site"), () => call_doc_method(frm, "deploy_site")).addClass("btn-primary");
        frm.add_custom_button(__("Remove Site"), () => {
          frappe.confirm(
            __("Are you sure you want to remove this site? This action cannot be undone."),
            () => call_doc_method(frm, "remove_site")
          );
        }).addClass("btn-danger");
      } else if (!frm.doc.ssl_enabled && frm.doc.server_name) {
        frappe.db.get_doc("Server", frm.doc.server_name).then(server => {
          const ip = server.server_ip || "localhost";
          const port = frm.doc.port || 8080;
          frm.add_custom_button(__("Visit Site (Insecure)"), () => window.open(`http://${ip}:${port}`)).addClass("btn-warning");
        });
      }
    }

    // (Re)bind clipboard handlers safely on every refresh
    bind_clipboard_handlers(frm);
  }
});

function bind_clipboard_handlers(frm) {
  const hasCreds = frm.doc.admin_password && frm.doc.username;
  const pwdField = frm.fields_dict["admin_password"];
  const userField = frm.fields_dict["username"];
  if (!hasCreds || !pwdField || !userField) return;

  // Set labels once per form lifetime
  if (!pwdField._label_patched) {
    pwdField.set_label('Admin Password - <span class="fa fa-clipboard" title="Copy to Clipboard"></span>');
    userField.set_label('Admin Username - <span class="fa fa-clipboard" title="Copy to Clipboard"></span>');
    pwdField._label_patched = true;
    userField._label_patched = true;
  }

  // Always remove old handlers before adding new ones (use event namespaces)
  $(pwdField.label_area)
    .off('click.copy') // prevent duplicates
    .on('click.copy', function () {
      frappe.call({
        method: 'nano_press.get_admin_password',
        args: { site_name: frm.doc.name },
        callback: function (r) {
          const val = r && r.message;
          if (val) {
            navigator.clipboard.writeText(val)
              .then(() => frappe.show_alert('Admin password copied to clipboard!'))
              .catch((error) => frappe.show_alert('Error copying password: ' + error));
          } else {
            frappe.show_alert('Could not retrieve admin password.');
          }
        }
      });
    });

  $(userField.label_area)
    .off('click.copy')
    .on('click.copy', function () {
      navigator.clipboard.writeText(frm.doc.username)
        .then(() => frappe.show_alert('Username copied to clipboard!'))
        .catch((error) => frappe.show_alert('Error copying username: ' + error));
    });
}

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
