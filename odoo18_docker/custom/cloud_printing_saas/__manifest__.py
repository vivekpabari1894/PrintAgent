{
    "name": "Cloud Printing SaaS Provider",
    "version": "1.0",
    "category": "SaaS",
    "summary": "Manage Cloud Printing Licenses and Automate via Subscriptions",
    "depends": ["base", "sale_management", "web", "website_sale", "account", "subscription_oca"],
    "data": [
        "security/ir.model.access.csv",
        "security/saas_security.xml",
        "views/saas_license_views.xml",
        "views/saas_printer_views.xml",
        "views/portal_templates.xml",
        "data/ir_cron_data.xml",
    ],
    "installable": True,
    "application": True,
    "license": "LGPL-3"
}
