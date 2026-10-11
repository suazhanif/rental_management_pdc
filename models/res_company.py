# -*- coding: utf-8 -*-
# Copyright 2024
# License OPL-1
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    is_pdc_user_daily_notify = fields.Boolean(
        string="PDC User Daily Digest",
        help="When enabled, all PDC Users in this company receive a daily "
        "morning email listing every PDC cheque scheduled for deposit "
        "the next day (state in Draft or Registered).",
    )
