# -*- coding: utf-8 -*-
# Copyright 2024
# License OPL-1
from odoo import api, fields, models


class PdcDepositDigest(models.TransientModel):
    """One-shot payload for the daily PDC deposit digest email.

    A record is created per recipient per company on each cron run, then
    handed to ``rental_management_pdc.pdc_user_daily_mail_template`` as
    the rendering context. Odoo's transient-vacuum cron cleans these up
    automatically (default ``_transient_max_hours = 1``).
    """

    _name = "pdc.deposit.digest"
    _description = "PDC Daily Deposit Digest"

    user_id = fields.Many2one(
        "res.users",
        string="Recipient User",
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    digest_date = fields.Date(
        string="Digest Date",
        default=fields.Date.today,
        help="The date the digest was generated.",
    )
    deposit_date = fields.Date(
        string="Deposit Date",
        required=True,
        help="The date the listed PDC cheques are scheduled for deposit "
        "(normally tomorrow).",
    )
    line_ids = fields.Many2many(
        "pdc.wizard",
        "pdc_deposit_digest_line_rel",
        "digest_id",
        "pdc_id",
        string="PDC Lines",
    )
    line_count = fields.Integer(
        string="Number of PDCs",
        compute="_compute_line_count",
    )
    base_url = fields.Char(
        string="Base URL",
        compute="_compute_base_url",
        help="Web base URL used to render absolute View links in the email.",
    )

    @api.depends("line_ids")
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)

    def _compute_base_url(self):
        base = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("web.base.url", default="")
        )
        for rec in self:
            rec.base_url = base
