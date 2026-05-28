app_name = "frappe_n8n"
app_title = "Frappe n8n"
app_publisher = "Aquiveal"
app_description = "n8n Provider Plugin for Frappe Playbook"
app_email = "aquiveal@example.com"
app_license = "mit"

scheduler_events = {
    "all": [
        "frappe_n8n.n8n.doctype.playbook_provider.playbook_provider.queue_update_playbooks",
        "frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.poll_executions"
    ],
    "cron": {
        "0 0 1 */3 *": [
            "frappe_n8n.n8n.doctype.n8n_settings.n8n_settings.rotate_credentials"
        ]
    }
}

controller_events = {
    "frappe_n8n.n8n.doctype.playbook_provider.playbook_provider.update_a_playbook": {},
    "frappe_n8n.n8n.doctype.playbook_provider.playbook_provider.retrieve_workflow": {}
}

# Apps
# ------------------

required_apps = ["frappe_playbook", "frappe_controller"]

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "frappe_n8n",
# 		"logo": "/assets/frappe_n8n/logo.png",
# 		"title": "Frappe n8n",
# 		"route": "/frappe_n8n",
# 		"has_permission": "frappe_n8n.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/frappe_n8n/css/frappe_n8n.css"
# app_include_js = "/assets/frappe_n8n/js/frappe_n8n.js"

# include js, css files in header of web template
# web_include_css = "/assets/frappe_n8n/css/frappe_n8n.css"
# web_include_js = "/assets/frappe_n8n/js/frappe_n8n.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "frappe_n8n/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "frappe_n8n/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "frappe_n8n.utils.jinja_methods",
# 	"filters": "frappe_n8n.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "frappe_n8n.install.before_install"
after_install = "frappe_n8n.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "frappe_n8n.uninstall.before_uninstall"
# after_uninstall = "frappe_n8n.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "frappe_n8n.utils.before_app_install"
# after_app_install = "frappe_n8n.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "frappe_n8n.utils.before_app_uninstall"
# after_app_uninstall = "frappe_n8n.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "frappe_n8n.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

controller_events = {
    "n8n Execution": [
        {
            "method": "frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.trigger_execution",
            "rate_limit_per_minute": 50
        },
        {
            "method": "frappe_n8n.n8n.doctype.playbook_execution.playbook_execution.resume_execution",
            "rate_limit_per_minute": 50
        }
    ]
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"frappe_n8n.tasks.all"
# 	],
# 	"daily": [
# 		"frappe_n8n.tasks.daily"
# 	],
# 	"hourly": [
# 		"frappe_n8n.tasks.hourly"
# 	],
# 	"weekly": [
# 		"frappe_n8n.tasks.weekly"
# 	],
# 	"monthly": [
# 		"frappe_n8n.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "frappe_n8n.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "frappe_n8n.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "frappe_n8n.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "frappe_n8n.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["frappe_n8n.utils.before_request"]
# after_request = ["frappe_n8n.utils.after_request"]

# Job Events
# ----------
# before_job = ["frappe_n8n.utils.before_job"]
# after_job = ["frappe_n8n.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"frappe_n8n.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []


fixtures = [
    {"dt": "Custom Field", "filters": [
        [
            "name", "in", [
                "Playbook-n8n_workflow_id",
                "Playbook-n8n_webhook_url",
                "Playbook Execution-n8n_execution_id"
            ]
        ]
    ]}
]

playbook_providers = {
    "n8n": "frappe_n8n.n8n.doctype.playbook_provider.playbook_provider.N8nPlaybookProvider"
}
