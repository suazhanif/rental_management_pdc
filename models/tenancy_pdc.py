# -*- coding: utf-8 -*-
# Copyright 2024
# License OPL-1
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class TenancyDetails(models.Model):
    """Extend tenancy.details with PDC cheque management."""

    _inherit = "tenancy.details"

    # ----------------------------------------------------------------------
    # Fields
    # ----------------------------------------------------------------------
    pdc_enabled = fields.Boolean(
        string="Enable PDC Cheques",
        default=True,
        help="When enabled, cheques are auto-generated from payment schedule.",
    )
    pdc_auto_generate = fields.Boolean(
        string="Auto Generate Cheques",
        default=True,
        help="Automatically create PDC records when contract is activated.",
    )
    pdc_payment_day = fields.Integer(
        string="Cheque Payment Day",
        default=1,
        help="Day of month on which each cheque is due.",
    )
    pdc_generated = fields.Boolean(
        string="Cheques Generated",
        default=False,
        copy=False,
    )
    pdc_check_ids = fields.One2many(
        "tenancy.pdc.check",
        "tenancy_id",
        string="PDC Cheques",
        copy=False,
    )
    pdc_check_count = fields.Integer(
        string="PDC Count",
        compute="_compute_pdc_check_count",
        store=True,
    )
    has_pdc_checks = fields.Boolean(
        string="Has PDC",
        compute="_compute_has_pdc_checks",
        store=True,
    )

    # ----------------------------------------------------------------------
    # Computes
    # ----------------------------------------------------------------------
    @api.depends("pdc_check_ids")
    def _compute_pdc_check_count(self):
        for rec in self:
            rec.pdc_check_count = len(rec.pdc_check_ids)

    @api.depends("pdc_check_ids")
    def _compute_has_pdc_checks(self):
        for rec in self:
            rec.has_pdc_checks = bool(rec.pdc_check_ids)

    # ----------------------------------------------------------------------
    # PDC Generation
    # ----------------------------------------------------------------------
    def _get_pdc_schedule(self):
        """
        Compute payment schedule dates and amounts based on contract terms.
        Returns list of dicts: {date, amount, sequence}.
        """
        self.ensure_one()
        schedule = []

        if not self.pdc_enabled or not self.start_date or not self.payment_term:
            return schedule

        term_intervals = {
            "monthly": 1,
            "bi_monthly": 2,
            "quarterly": 3,
            "half_year": 6,
            "year": 12,
            "daily": 1,
            "full_payment": 0,
        }
        interval_months = term_intervals.get(self.payment_term)
        if interval_months is None:
            return schedule

        # For full payment, single cheque
        if self.payment_term == "full_payment":
            schedule.append({
                "date": self.invoice_start_date,
                "amount": self.total_rent,
                "sequence": 1,
            })
            return schedule

        payment_day = self.pdc_payment_day or 1
        current_date = self.invoice_start_date
        sequence = 1

        # Count how many payments fit in contract duration
        if self.duration_type == "by_duration" and self.month:
            max_installments = self.month
        elif self.duration_type == "by_date" and self.duration_end_date:
            months_total = self._months_between(self.start_date, self.duration_end_date)
            max_installments = months_total
        else:
            return schedule

        # Adjust for payment term
        if interval_months > 0:
            max_installments = max_installments // interval_months
            if max_installments < 1:
                max_installments = 1
        else:
            max_installments = 1

        # Optionally include deposit as first cheque
        if self.is_any_deposit and self.deposit_amount:
            schedule.append({
                "date": self.invoice_start_date,
                "amount": self.deposit_amount,
                "sequence": 0,
                "is_deposit": True,
            })

        while sequence <= max_installments:
            due_date = current_date.replace(day=min(payment_day, 28))
            schedule.append({
                "date": due_date,
                "amount": self.total_rent,
                "sequence": sequence,
            })
            sequence += 1
            if interval_months:
                current_date = current_date + relativedelta(months=interval_months)
            else:
                break

        return schedule

    def _months_between(self, date1, date2):
        """Calculate months between two dates."""
        if not date1 or not date2:
            return 0
        return (date2.year - date1.year) * 12 + (date2.month - date1.month)

    def action_generate_pdc_checks(self):
        """
        Generate PDC cheque records from payment schedule.
        Called manually or automatically when contract is activated.
        """
        self.ensure_one()

        if not self.pdc_enabled:
            raise UserError(_("PDC is not enabled for this contract."))

        if self.pdc_generated:
            raise UserError(_("PDC cheques have already been generated for this contract."))

        if self.contract_type == "new_contract":
            raise UserError(_("Please activate the contract before generating PDC cheques."))

        schedule = self._get_pdc_schedule()
        if not schedule:
            raise UserError(_("Could not generate payment schedule. Check contract dates and payment terms."))

        pdc_model = self.env["pdc.wizard"]
        company = self.company_id or self.env.company

        # Check PDC accounts configured
        if not company.pdc_customer:
            raise UserError(_("Please configure PDC payment account for Customer in company settings."))

        # Find a default bank journal for the company
        bank_journal = self.env["account.journal"].search([
            ("type", "=", "bank"),
            "|",
            ("company_id", "=", company.id),
            ("company_id", "=", False),
        ], limit=1)
        if not bank_journal:
            raise UserError(_("No bank journal found. Please configure a bank journal in company settings."))

        # Find all invoices created for this contract so far
        # These are created at activation and will be extended by schedulers
        invoices = self.env["account.move"].search([
            ("tenancy_id", "=", self.id),
            ("move_type", "=", "out_invoice"),
        ])
        # Also find open (unpaid) posted invoices for account_move_ids
        open_invoices = invoices.filtered(
            lambda inv: inv.state == 'posted' and inv.payment_state != 'paid'
        )

        # Map PDC sequence to invoice
        # For now, only sequence 1 (first payment) has a corresponding invoice
        # Future invoices are created by schedulers - this allows manual linking then
        def get_invoice_ids_for_payment(payment):
            seq = payment.get("sequence", 0)
            is_deposit = payment.get("is_deposit", False)
            if is_deposit:
                # Deposit cheque - link to the standalone deposit invoice
                return invoices.filtered("is_deposit_invoice").ids
            elif seq == 1:
                # First payment - link to the first rent invoice (created at
                # activation); the deposit has its own invoice and cheque.
                rent_invoices = invoices.filtered(lambda inv: not inv.is_deposit_invoice)
                return rent_invoices.ids[:1] if rent_invoices else []
            else:
                # Future payments - no invoice exists yet, leave empty for manual linking
                return []

        cheques_created = 0
        for payment in schedule:
            # Get invoice IDs for this specific payment
            payment_invoice_ids = get_invoice_ids_for_payment(payment)
            # Compute account_move_ids (open invoices for domain)
            payment_account_move_ids = open_invoices.ids if open_invoices else []

            # Map to pdc.wizard fields
            pdc_vals = {
                "partner_id": self.tenancy_id.id,
                "payment_amount": payment["amount"],
                "payment_type": "receive_money",
                "payment_date": fields.Date.today(),
                "due_date": payment["date"],
                "memo": f"{self.tenancy_seq} - Cheque #{payment['sequence']}",
                "company_id": company.id,
                "journal_id": bank_journal.id,
                "state": "draft",
                "reference": "",  # User will fill manually
                "invoice_ids": [(6, 0, payment_invoice_ids)],
                "account_move_ids": [(6, 0, payment_account_move_ids)],
            }

            pdc = pdc_model.create(pdc_vals)

            # Create tenancy.pdc.check link record
            self.env["tenancy.pdc.check"].create({
                "tenancy_id": self.id,
                "pdc_wizard_id": pdc.id,
                "scheduled_date": payment["date"],
                "scheduled_amount": payment["amount"],
                "sequence": payment["sequence"],
                "is_deposit": payment.get("is_deposit", False),
            })
            cheques_created += 1

        self.write({"pdc_generated": True})

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "title": _("PDC Cheques Generated"),
                "message": _(f"{cheques_created} PDC cheque(s) created for this contract."),
                "sticky": False,
            },
        }

    def action_view_pdc_checks(self):
        """Open PDC cheque list view for this contract."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("PDC Cheques"),
            "res_model": "pdc.wizard",
            "domain": [("id", "in", self.pdc_check_ids.mapped("pdc_wizard_id").ids)],
            "view_mode": "list,form",
            "target": "current",
        }

    def action_update_pdc_invoice_links(self):
        """
        Update PDC cheque links to connect with newly created invoices.

        Finds PDC cheques for this contract that have no linked invoices,
        then searches for matching posted invoices and creates the links.
        This is called by schedulers after invoice creation to ensure
        PDC cheques are automatically connected to their invoices.

        Returns a dict with notification info or the number of links updated.
        """
        self.ensure_one()
        updated_count = 0

        # Find PDC cheques without linked invoices
        pdc_checks_without_invoices = self.pdc_check_ids.filtered(
            lambda p: not p.pdc_wizard_id.invoice_ids
        )

        if not pdc_checks_without_invoices:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "type": "info",
                    "title": _("No Update Needed"),
                    "message": _("All PDC cheques are already linked to invoices."),
                    "sticky": False,
                },
            }

        # Get all posted invoices for this contract
        invoices = self.env["account.move"].search([
            ("tenancy_id", "=", self.id),
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
        ])

        if not invoices:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "type": "info",
                    "title": _("No Invoices Found"),
                    "message": _("No posted invoices found to link."),
                    "sticky": False,
                },
            }

        # Match PDC cheques to invoices based on scheduled date proximity
        # Allow matching if invoice date is within 5 days of scheduled date
        date_tolerance = 5

        for pdc_check in pdc_checks_without_invoices:
            scheduled_date = pdc_check.scheduled_date
            pdc_wizard = pdc_check.pdc_wizard_id

            # Find matching invoice by date proximity
            matching_invoice = None
            for invoice in invoices:
                invoice_date = invoice.invoice_date
                if invoice_date and scheduled_date:
                    date_diff = abs((invoice_date - scheduled_date).days)
                    if date_diff <= date_tolerance:
                        # Check this invoice isn't already linked to another PDC
                        already_linked = any(
                            pdc_check.pdc_wizard_id.id in p.pdc_wizard_id.invoice_ids.ids
                            for p in self.pdc_check_ids
                            if p.id != pdc_check.id
                        )
                        if not already_linked:
                            matching_invoice = invoice
                            break

            if matching_invoice:
                # Link the invoice to the PDC wizard
                pdc_wizard.write({
                    "invoice_ids": [(4, matching_invoice.id)],
                })
                # Also update account_move_ids for domain purposes
                if matching_invoice.state == "posted":
                    current_move_ids = pdc_wizard.account_move_ids.ids
                    if matching_invoice.id not in current_move_ids:
                        pdc_wizard.write({
                            "account_move_ids": [(4, matching_invoice.id)],
                        })
                updated_count += 1

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "title": _("PDC Links Updated"),
                "message": _(f"{updated_count} PDC cheque(s) linked to invoices."),
                "sticky": False,
            },
        }

    # ----------------------------------------------------------------------
    # Hook into contract lifecycle
    # ----------------------------------------------------------------------
    def action_active_contract(self):
        """
        Override to optionally auto-generate PDC cheques on activation.
        Call super() first, then generate PDCs if enabled.
        """
        res = super().action_active_contract()

        if self.pdc_enabled and self.pdc_auto_generate and not self.pdc_generated:
            self.action_generate_pdc_checks()

        return res


class TenancyPdcCheck(models.Model):
    """
    Links pdc.wizard records to tenancy.details.
    Tracks which PDC belongs to which contract and stores the
    original scheduled date/amount for reconciliation.
    """

    _name = "tenancy.pdc.check"
    _description = "Tenancy PDC Cheque Link"
    _rec_name = "display_name"

    tenancy_id = fields.Many2one(
        "tenancy.details",
        string="Tenancy Contract",
        required=True,
        index=True,
        ondelete="cascade",
    )
    pdc_wizard_id = fields.Many2one(
        "pdc.wizard",
        string="PDC Cheque",
        required=True,
        index=True,
        ondelete="cascade",
    )
    scheduled_date = fields.Date(
        string="Scheduled Date",
        help="Original scheduled payment date from contract.",
    )
    scheduled_amount = fields.Monetary(
        string="Scheduled Amount",
    )
    sequence = fields.Integer(
        string="Installment #",
    )
    is_deposit = fields.Boolean(
        string="Is Deposit Cheque",
        default=False,
    )
    currency_id = fields.Many2one(
        related="tenancy_id.currency_id",
        string="Currency",
        store=True,
    )

    @api.depends("pdc_wizard_id.name", "tenancy_id.tenancy_seq")
    def _compute_display_name(self):
        for rec in self:
            pdc_name = rec.pdc_wizard_id.name or "New"
            rec.display_name = f"{rec.tenancy_id.tenancy_seq} / {pdc_name}"

    @api.model
    def create(self, vals):
        rec = super().create(vals)
        # Keep reference in pdc.wizard back to this contract
        if rec.pdc_wizard_id and rec.tenancy_id:
            rec.pdc_wizard_id.write({
                "tenancy_id": rec.tenancy_id.id,
            })
        return rec

    # Convenience: delegate state to underlying pdc.wizard
    @api.depends("pdc_wizard_id.state")
    def _compute_state(self):
        for rec in self:
            rec.state = rec.pdc_wizard_id.state

    def _inverse_state(self):
        pass

    state = fields.Char(
        compute="_compute_state",
        inverse="_inverse_state",
        string="State",
        store=True,
    )


# Extend pdc.wizard so PDC form shows linked tenancy contract
class PDCWizardExtend(models.Model):
    _inherit = "pdc.wizard"

    tenancy_id = fields.Many2one(
        "tenancy.details",
        string="Tenancy Contract",
        index=True,
        copy=False,
    )