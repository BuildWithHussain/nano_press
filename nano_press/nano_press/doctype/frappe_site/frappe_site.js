// Copyright (c) 2025
// Frappe Site doctype JS

console.log("[Frappe Site JS] loaded");

const STATUS = {
  NOT_DEPLOYED: "Not Deployed",
  READY: "Ready To Deploy",
  DEPLOYING: "Deploying",
  DEPLOYED: "Deployed",
  FAILED: "Failed",
  STOPPED: "Stopped",
};

frappe.ui.form.on("Frappe Site", {
  async refresh(frm) {

    // Intro banners (submitted docs only)
    if (frm.doc.docstatus === 1 && frm.doc.status === STATUS.NOT_DEPLOYED) {
      frm.set_intro(__("Click on <b>Prepare for Deployment</b> to start the deployment process."), "info");
    }
    if (frm.doc.docstatus === 1 && frm.doc.status === STATUS.DEPLOYED) {
      frm.set_intro(__("Site is deployed. App installs may still be running; it can take a few minutes to be fully functional."), "warning");
    }

    // A visible refresh button (header)
    frm.add_custom_button(__("Refresh"), () => frm.reload_doc());

    // Actions by status (shown as header buttons - no group param)
    if (frm.doc.docstatus === 1 && frm.doc.status === STATUS.NOT_DEPLOYED) {
      frm.add_custom_button(__("Prepare for Deployment"), () => queue_prepare_for_deployment(frm)).addClass("btn-primary");
    }

    if (frm.doc.status === STATUS.READY) {
      frm.add_custom_button(__("Deploy"), () => queue_deploy_site(frm)).addClass("btn-primary");
    }

    if (frm.doc.status === STATUS.DEPLOYING) {
      frm.add_custom_button(__("Cancel Deployment"), () => {
        frappe.msgprint(__("Cancel is not implemented yet."));
      });
    }

    if (frm.doc.status === STATUS.DEPLOYED) {
      frm.add_custom_button(__("View Site"), () => {
        const url = (frm.doc.site_name || "").trim();
        if (url) window.open(`https://${url}`, "_blank", "noopener,noreferrer");
        else frappe.msgprint(__("Site URL (site_name) not found."));
      });

      frm.add_custom_button(__("Stop All Containers"), () => queue_stop_all_containers(frm)).addClass("btn-danger");

	  frm.add_custom_button(__("Destroy Site"), () => {
		frappe.warn(
			__("Destroy Site"),
			__("This will irreversibly remove containers/volumes. Are you sure?"),
			() => frappe.msgprint(__("Not implemented yet.")),
			__("I Understand"),
			true
		);
		}).addClass("btn-danger");
    }

    if (frm.doc.status === STATUS.FAILED || frm.doc.status === STATUS.STOPPED) {
      frm.add_custom_button(__("Retry Deployment"), () => queue_deploy_site(frm)).addClass("btn-primary");
    }

    // Realtime listeners once
    setup_deployment_notifications(frm);
  },
});

/* -------------------- Actions (background-queued) -------------------- */

async function queue_prepare_for_deployment(frm) {
  if (frm.__busy_prepare) return;
  frm.__busy_prepare = true;
  try {
    frappe.show_alert(__("Queuing server preparation..."), 5);
    const r = await frm.call("queue_prepare_for_deployment");
    const msg = r.message || {};
    frappe.show_alert({ message: __("Queued: {0}", [msg.job_id || "job"]), indicator: "blue" }, 5);
    frm.reload_doc();
  } catch (e) {
    frappe.throw(e.message || e);
  } finally {
    frm.__busy_prepare = false;
  }
}

async function queue_deploy_site(frm) {
  if (frm.__busy_deploy) return;
  frm.__busy_deploy = true;
  try {
    frappe.show_alert(__("Queuing deployment..."), 5);
    const r = await frm.call("queue_deploy_site");
    const msg = r.message || {};
    frappe.show_alert({ message: __("Queued: {0}", [msg.job_id || "job"]), indicator: "blue" }, 5);
    frm.reload_doc();
  } catch (e) {
    frappe.throw(e.message || e);
  } finally {
    frm.__busy_deploy = false;
  }
}

async function queue_stop_all_containers(frm) {
  if (frm.__busy_stop) return;
  frappe.warn(
    __("Stop All Containers"),
    __("This will stop the running site and make it unavailable. You can redeploy later."),
    async () => {
      frm.__busy_stop = true;
      try {
        frappe.show_alert(__("Queuing stop-all-containers..."), 5);
        const r = await frm.call("queue_stop_all_containers");
        const msg = r.message || {};
        frappe.show_alert({ message: __("Queued: {0}", [msg.job_id || "job"]), indicator: "orange" }, 5);
        frm.reload_doc();
      } catch (e) {
        frappe.throw(e.message || e);
      } finally {
        frm.__busy_stop = false;
      }
    },
    __("Stop Containers"),
    true
  );
}

/* -------------------- Realtime streaming + UX -------------------- */

function setup_deployment_notifications(frm) {
  if (frm.__siteRealtimeBound) return;
  frm.__siteRealtimeBound = true;

  frappe.realtime.on("frappe_site_update", (data) => {
    if (!data || data.frappe_site !== frm.doc.name) return;
    frappe.show_alert({ message: data.message || __("Update received"), indicator: data.status === "success" ? "green" : "red" }, 5);
    frm.reload_doc();
    if ("Notification" in window && Notification.permission === "granted") {
      new Notification(`Frappe Site: ${frm.doc.site_name || frm.doc.name}`, {
        body: data.message || "",
        icon: "/assets/frappe/images/frappe-favicon.svg",
      });
    }
  });

  frappe.realtime.on("frappe_site_live_update", (data) => {
    if (!data || data.frappe_site !== frm.doc.name) return;
    update_live_deployment_log(frm, data.log_line || "");
    auto_scroll_deployment_log();
  });

  if ("Notification" in window && Notification.permission === "default") {
    Notification.requestPermission();
  }
}

function update_live_deployment_log(frm, log_line) {
  if (!log_line) return;
  const field = frm.get_field("deployment_log");
  if (!field) return;

  const current = frm.doc.deployment_log || "";
  frm.doc.deployment_log = log_line + "\n" + current; // PREPEND newest first
  field.refresh();

  const line = (log_line || "").toLowerCase();
  const hits = ["task", "step", "pulling", "creating", "starting", "installing", "error", "failed", "ok:", "changed:"];
  if (hits.some((k) => line.includes(k))) {
    frappe.show_alert({ message: `🚀 ${log_line}`, indicator: "blue" }, 5);
  }
}

function auto_scroll_deployment_log() {
  setTimeout(() => {
    const $ta = $(`div[data-fieldname="deployment_log"] textarea, textarea[data-fieldname="deployment_log"]`);
    if ($ta && $ta.length) $ta.scrollTop(0); // stay at top
  }, 100);
}
