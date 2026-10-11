# -*- coding: utf-8 -*-
# Copyright 2024
# License OPL-1
{
    "name": "Rental Management - PDC Integration",
    "summary": "Integrates PDC cheque management with tenancy contracts",
    "description": """
    Auto-generates PDC cheques from tenancy contract payment terms.
    Links pdc.wizard records to tenancy.details and enforces role-based
    action permissions (User vs Manager).
    Adds a daily digest email for PDC Users listing cheques to deposit
    the next day.
    """,
    "author": "",
    "website": "",
    "category": "Realestate",
    "version": "1.0.0",
    "depends": [
        "rental_management",
        "sh_pdc",
    ],
    "data": [
        "security/pdc_groups.xml",
        "security/ir.model.access.csv",
        "security/pdc_server_actions_inherit_role.xml",
        "data/pdc_user_daily_mail_template.xml",
        "data/pdc_user_daily_cron.xml",
        "views/tenancy_pdc_views.xml",
        "views/pdc_wizard_view_inherit_role.xml",
        "views/res_config_settings_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}