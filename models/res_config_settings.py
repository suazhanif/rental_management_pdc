# -*- coding: utf-8 -*-
# Copyright 2024
# License OPL-1
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    is_pdc_user_daily_notify = fields.Boolean(
        string="PDC User Daily Digest",
        related="company_id.is_pdc_user_daily_notify",
        readonly=False,
    )
