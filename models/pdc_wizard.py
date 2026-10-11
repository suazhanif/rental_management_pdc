# -*- coding: utf-8 -*-
# Copyright 2024
# License OPL-1
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class PdcWizard(models.Model):
    """Extend pdc.wizard with the daily PDC-User digest cron entry point.

    The cron's ``model_id`` points at ``sh_pdc.model_pdc_wizard`` (to stay
    consistent with the existing sh_pdc crons), but the digest logic lives
    here so that ``sh_pdc`` is not modified.
    """

    _inherit = "pdc.wizard"

    # ------------------------------------------------------------------
    #  CRON: Daily PDC-User deposit digest
    # ------------------------------------------------------------------
    @api.model
    def notify_pdc_user_daily(self):
        """Send one digest email per (user, company) listing every PDC
        cheque whose ``due_date`` is tomorrow and whose ``state`` is still
        ``draft`` or ``registered``.

        Gated per-company by ``res.company.is_pdc_user_daily_notify``.
        Recipients are every active user in
        ``rental_management_pdc.group_pdc_user`` (PDC Manager is implied,
        so managers receive the digest too) whose ``company_ids`` includes
        the company being processed and whose ``partner_id`` has an email.
        """
        tomorrow = fields.Date.add(fields.Date.today(), days=1)

        group = self.env.ref(
            "rental_management_pdc.group_pdc_user", raise_if_not_found=False
        )
        if not group:
            _logger.warning(
                "PDC daily digest: group_pdc_user not found, skipping."
            )
            return

        template = self.env.ref(
            "rental_management_pdc.pdc_user_daily_mail_template",
            raise_if_not_found=False,
        )
        if not template:
            _logger.warning(
                "PDC daily digest: mail template not found, skipping."
            )
            return

        Digest = self.env["pdc.deposit.digest"]
        Users = self.env["res.users"]

        companies = self.env["res.company"].search(
            [("is_pdc_user_daily_notify", "=", True)]
        )
        if not companies:
            return

        for company in companies:
            pdcs = self.search(
                [
                    ("state", "in", ("draft", "registered")),
                    ("due_date", "=", tomorrow),
                    ("company_id", "=", company.id),
                ]
            )
            if not pdcs:
                continue

            # ``all_group_ids`` is the computed field that exposes the
            # transitive closure of implied groups, with a custom search
            # that joins through ``all_implied_ids``. Using it here means
            # PDC Managers (who imply PDC User) are included even if the
            # implied_ids cascade hasn't yet been applied to their stored
            # ``group_ids`` column (e.g. when the user was added to the
            # manager group via ``res.groups.user_ids`` rather than via a
            # write on ``res.users.group_ids``).
            users = Users.search(
                [
                    ("all_group_ids", "in", group.ids),
                    ("company_ids", "in", company.id),
                    ("active", "=", True),
                ]
            )
            if not users:
                _logger.info(
                    "PDC daily digest: no eligible recipients in company %s",
                    company.display_name,
                )
                continue

            for user in users:
                if not user.partner_id.email:
                    continue
                
                digest = Digest.create(
                    {
                        "user_id": user.id,
                        "company_id": company.id,
                        "deposit_date": tomorrow,
                        "line_ids": [(6, 0, pdcs.ids)],
                    }
                )
                try:
                    template.with_company(company).send_mail(
                        digest.id,
                        email_values={"email_to": user.partner_id.email},
                        email_layout_xmlid="mail.mail_notification_light",
                        force_send=True,
                    )
                    _logger.info(
                        "PDC daily digest sent to %s (company=%s, %d PDC(s))",
                        user.partner_id.email,
                        company.display_name,
                        len(pdcs),
                    )
                except Exception:  # noqa: BLE001 - never let one bad user kill the cron
                    _logger.exception(
                        "PDC daily digest: failed to email %s (company=%s)",
                        user.partner_id.email,
                        company.display_name,
                    )
