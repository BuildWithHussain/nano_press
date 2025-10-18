# Nano Press

Nano Press automates the full lifecycle of a self-hosted Frappe/ERPNext deployment—from connecting a fresh server to shipping production-ready sites. It wraps Ansible automation, server health checks, app management, and site provisioning into a guided workflow that lives inside your Frappe desk.

![Nano Press Dashboard](nano_press/public/images/dashboard.png)

## Why teams choose Nano Press

- Automates server preparation (Docker, Traefik, lets-encrypt) and ongoing health checks.
- Orchestrates benches, sites, and custom apps without leaving the Frappe UI.
- Logs every Ansible run for traceability and surfaces build/deploy notifications in-app and by email.
- Adds optional custom images so repeated deployments are significantly faster.
- Ships with onboarding guides and video walkthroughs so new operators can go live in minutes.

## Prerequisites

- Frappe/ERPNext bench where the `nano_press` app is installed and enabled.
- Target VM or bare-metal host (Ubuntu 20.04 LTS or newer recommended) with SSH access.
- User with `sudo` privileges on the target host.
- Domain name (optional but required for HTTPS; Nano Press can provision a free `traefik.me` subdomain if you do not have one).
- Open ports 22, 80, and 443 on the target network.

> Docker, Docker Compose, Traefik, and other runtime dependencies are installed for you during the server preparation step.

## Quick start

1. Install the app on your bench:
   ```bash
   cd $PATH_TO_YOUR_BENCH
   bench get-app https://github.com/<your-org>/nano_press.git --branch develop
   bench install-app nano_press
   ```
2. Log in to your desk as a system manager and open **Nano Press** from the workspace sidebar.
3. Follow the guided onboarding shown below to connect a server, add apps, and launch your site.

## Guided onboarding workflow

| Step | What happens | Related doctypes | Watch the walkthrough |
| --- | --- | --- | --- |
| 1. Create a Server | Register the host, SSH credentials, and Traefik settings. Nano Press keeps the connection info and prepares the machine with Docker and dependencies. | `Server` | [Create a Server](https://drive.google.com/file/d/1LtpQADJkGMXgfdmlQG12rEYQcgfm9y-_/view?usp=sharing) |
| 2. Verify Server Connection | Trigger an Ansible ping to confirm Nano Press can reach the host. | `Server` | [Verify Server Connection](https://drive.google.com/file/d/1LtpQADJkGMXgfdmlQG12rEYQcgfm9y-_/view?usp=sharing) |
| 3. Add Frappe Apps | Add official or custom GitHub apps you want baked into your bench. Supports private repos via deploy keys. | `Apps` | [Add Frappe Apps](https://drive.google.com/file/d/1mRkhB61ZIk0NVC8P_KfnnIG-q401Mr68/view?usp=sharing) |
| 4. Build Custom Image (optional) | Build a reusable Docker image that includes your chosen apps. Great for staging/prod parity or repeated rollouts. | `Custom Image` | [Build a Custom Image](https://drive.google.com/file/d/1X_N84--9Z6gFQuaJ0LZnReGEVRM7KsLW/view?usp=sharing) |
| 5. Deploy Server | Launch a Frappe site with your selected apps, configure domains/SSL, and receive email notifications when it is live. | `Frappe Site` | [Deploy Your Server](https://drive.google.com/file/d/1qyBLdLIorqgm_V61DoUIFWqH78ltN-_G/view?usp=sharing) |

### Accessing a freshly deployed site

- Default URL: `https://<site_url>` (swap for your domain if SSL is configured).
- Default credentials: `Administrator` and the password set during deployment.

## Operations checklist

- **Monitor builds**: Track progress from the **Build Log** doctype; Nano Press also raises desk notifications and optional emails when a build or deploy completes.
- **Review automation output**: Each Ansible run is stored under `Ansible Log` for audit and troubleshooting.
- **Rerun preparation**: If your server drifts, trigger the preparation playbook again from the Server dashboard to reinstall Docker or refresh Traefik certificates.
- **Add more sites**: Once the server is verified, you can deploy additional benches or sites without repeating the onboarding steps.

## Development & contributing

Nano Press uses [pre-commit](https://pre-commit.com/#installation) to keep Python, JS, and schema changes linted.

```bash
cd apps/nano_press
pre-commit install
```

Configured hooks include `ruff`, `eslint`, `prettier`, and `pyupgrade`. Run `pre-commit run --all-files` before opening a pull request.

### Continuous integration

GitHub Actions workflows (located under `.github/workflows/`) install the app on a test bench, run unit tests on pushes to `develop`, and execute security/static analysis via Frappe Semgrep rules and `pip-audit` on pull requests.

## Support

- Raise issues or feature requests via GitHub Discussions/Issues.
- Share deployment logs (redacted for secrets) when reporting problems.
- For enterprise onboarding or bespoke automation, reach out to the maintainers listed in the repository metadata.

## License

MIT
