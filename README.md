### Frappe n8n

**Version:** 16.0.1

Frappe n8n is a powerful provider plugin for the Frappe Playbook ecosystem. It seamlessly integrates your Frappe applications with n8n, the leading fair-code workflow automation tool. By acting as a bridge between Frappe Playbook and n8n, this app allows you to trigger, manage, and monitor complex n8n workflows directly from within your Frappe environment.

**Key Features:**
- **Automated Workflow Execution:** Trigger n8n workflows automatically based on Frappe document events (e.g., when a Lead is created or a Deal is won).
- **Playbook Integration:** Fully compatible with the Frappe Playbook architecture, allowing you to define conditions and filters for when workflows should run.
- **Execution Tracking:** Monitor the status of your n8n workflow executions (Running, Success, Error, Canceled) directly from the Frappe interface.
- **Seamless Authentication:** Manage n8n API credentials and webhook configurations securely within Frappe.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch main
bench install-app frappe_n8n
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/frappe_n8n
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
