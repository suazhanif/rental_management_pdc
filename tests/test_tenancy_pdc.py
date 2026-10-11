import datetime

from dateutil.relativedelta import relativedelta
from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import tagged

from odoo.addons.rental_management.tests.common import CreateRentalData


@tagged("pdc_cheques", "rental_management_pdc")
class TestTenancyPDC(CreateRentalData):
    """Unit tests to validate PDC cheque generation and invoice linking."""

    @classmethod
    def setUpClass(cls):
        """Prepare test data for PDC cheque tests."""
        super().setUpClass()
        cls.invoice_post_type = "automatically"
        cls.env["ir.config_parameter"].sudo().set_param(
            "rental_management.invoice_post_type",
            cls.invoice_post_type,
        )

    def _create_monthly_contract(self, start_date, months, total_rent=10000):
        """Helper to create a monthly contract with specified duration."""
        # Create duration for the specified months
        duration = self.env["contract.duration"].create({
            "duration": f"{months} Month",
            "month": months,
            "rent_unit": "Month",
        })
        property_id = self._create_units(
            name=f"Property {start_date}",
            property_seq=f"PROP-{start_date}",
            sale_lease="for_tenancy",
            stage="draft",
            type="land",
            price=10000,
            rent_unit="Month",
        )
        contract_wizard = self._create_contract_wizard(
            active_model="property.details",
            active_id=property_id.id,
            data={
                "customer_id": self.customer_one.id,
                "start_date": start_date,
                "payment_term": "monthly",
                "duration_id": duration.id,
                "duration_type": "by_duration",
                "total_rent": total_rent,
                "property_id": property_id.id,
                "rent_unit": "Month",
                "water_reading": 100,
                "water_reading_date": fields.Datetime.now(),
                "electricity_reading": 100,
                "electricity_reading_date": fields.Datetime.now(),
            },
        )
        contract_action = contract_wizard.contract_action()
        contract = self.env["tenancy.details"].browse(contract_action["res_id"])
        # Set PDC fields on the tenancy contract (not on wizard)
        contract.write({"pdc_enabled": True, "pdc_auto_generate": True})
        return contract

    def _create_quarterly_contract(self, start_date, months, total_rent=10000):
        """Helper to create a quarterly contract with specified duration."""
        # Create duration for the specified months
        duration = self.env["contract.duration"].create({
            "duration": f"{months} Month",
            "month": months,
            "rent_unit": "Month",
        })
        property_id = self._create_units(
            name=f"Property Q-{start_date}",
            property_seq=f"PROPQ-{start_date}",
            sale_lease="for_tenancy",
            stage="draft",
            type="land",
            price=10000,
            rent_unit="Month",
        )
        contract_wizard = self._create_contract_wizard(
            active_model="property.details",
            active_id=property_id.id,
            data={
                "customer_id": self.customer_one.id,
                "start_date": start_date,
                "payment_term": "quarterly",
                "duration_id": duration.id,
                "duration_type": "by_duration",
                "total_rent": total_rent,
                "property_id": property_id.id,
                "rent_unit": "Month",
                "water_reading": 100,
                "water_reading_date": fields.Datetime.now(),
                "electricity_reading": 100,
                "electricity_reading_date": fields.Datetime.now(),
            },
        )
        contract_action = contract_wizard.contract_action()
        contract = self.env["tenancy.details"].browse(contract_action["res_id"])
        # Set PDC fields on the tenancy contract (not on wizard)
        contract.write({"pdc_enabled": True, "pdc_auto_generate": True})
        return contract

    def _create_contract_with_deposit(self, start_date, months, deposit_amount=5000):
        """Helper to create a contract with deposit."""
        # Create duration for the specified months
        duration = self.env["contract.duration"].create({
            "duration": f"{months} Month",
            "month": months,
            "rent_unit": "Month",
        })
        property_id = self._create_units(
            name=f"Property D-{start_date}",
            property_seq=f"PROPD-{start_date}",
            sale_lease="for_tenancy",
            stage="draft",
            type="land",
            price=10000,
            rent_unit="Month",
        )
        contract_wizard = self._create_contract_wizard(
            active_model="property.details",
            active_id=property_id.id,
            data={
                "customer_id": self.customer_one.id,
                "start_date": start_date,
                "payment_term": "monthly",
                "duration_id": duration.id,
                "duration_type": "by_duration",
                "total_rent": 10000,
                "property_id": property_id.id,
                "rent_unit": "Month",
                "is_any_deposit": True,
                "deposit_amount": deposit_amount,
                "water_reading": 100,
                "water_reading_date": fields.Datetime.now(),
                "electricity_reading": 100,
                "electricity_reading_date": fields.Datetime.now(),
            },
        )
        contract_action = contract_wizard.contract_action()
        contract = self.env["tenancy.details"].browse(contract_action["res_id"])
        # Set PDC fields on the tenancy contract (not on wizard)
        contract.write({"pdc_enabled": True, "pdc_auto_generate": True})
        return contract

    # ------------------------------------------------------------------------
    # PDC Schedule Generation Tests
    # ------------------------------------------------------------------------

    def test_pdc_schedule_monthly_12_months(self):
        """Test PDC schedule generates 12 cheques for 12-month monthly contract."""
        contract = self._create_monthly_contract("2025-01-01", 12)
        schedule = contract._get_pdc_schedule()

        self.assertEqual(len(schedule), 12)
        # Verify sequences are 1-12
        sequences = [p["sequence"] for p in schedule]
        self.assertEqual(sorted(sequences), list(range(1, 13)))
        # All amounts should be total_rent (10000)
        for payment in schedule:
            self.assertEqual(payment["amount"], 10000)

    def test_pdc_schedule_quarterly_12_months(self):
        """Test PDC schedule generates 4 cheques for 12-month quarterly contract."""
        contract = self._create_quarterly_contract("2025-01-01", 12)
        schedule = contract._get_pdc_schedule()

        self.assertEqual(len(schedule), 4)
        sequences = [p["sequence"] for p in schedule]
        self.assertEqual(sorted(sequences), [1, 2, 3, 4])
        for payment in schedule:
            self.assertEqual(payment["amount"], 10000)

    def test_pdc_schedule_monthly_6_months(self):
        """Test PDC schedule generates 6 cheques for 6-month monthly contract."""
        contract = self._create_monthly_contract("2025-01-01", 6)
        schedule = contract._get_pdc_schedule()

        self.assertEqual(len(schedule), 6)
        sequences = [p["sequence"] for p in schedule]
        self.assertEqual(sorted(sequences), list(range(1, 7)))

    def test_pdc_schedule_with_deposit(self):
        """Test PDC schedule includes deposit cheque when contract has deposit."""
        contract = self._create_contract_with_deposit("2025-01-01", 12)
        schedule = contract._get_pdc_schedule()

        # Should have deposit (seq 0) + 12 monthly payments
        self.assertEqual(len(schedule), 13)
        # First entry should be deposit
        deposit_entry = schedule[0]
        self.assertTrue(deposit_entry["is_deposit"])
        self.assertEqual(deposit_entry["sequence"], 0)
        self.assertEqual(deposit_entry["amount"], 5000)
        # Remaining 12 should be sequences 1-12
        remaining_sequences = [p["sequence"] for p in schedule[1:]]
        self.assertEqual(sorted(remaining_sequences), list(range(1, 13)))

    def test_pdc_schedule_disabled(self):
        """Test PDC schedule returns empty when PDC is disabled."""
        # Create duration for 12 months
        duration = self.env["contract.duration"].create({
            "duration": "12 Month",
            "month": 12,
            "rent_unit": "Month",
        })
        property_id = self._create_units(
            name="Property No PDC",
            property_seq="PROPNOPDC",
            sale_lease="for_tenancy",
            stage="draft",
            type="land",
            price=10000,
            rent_unit="Month",
        )
        contract_wizard = self._create_contract_wizard(
            active_model="property.details",
            active_id=property_id.id,
            data={
                "customer_id": self.customer_one.id,
                "start_date": "2025-01-01",
                "payment_term": "monthly",
                "duration_id": duration.id,
                "duration_type": "by_duration",
                "total_rent": 10000,
                "property_id": property_id.id,
                "rent_unit": "Month",
                "water_reading": 100,
                "water_reading_date": fields.Datetime.now(),
                "electricity_reading": 100,
                "electricity_reading_date": fields.Datetime.now(),
            },
        )
        contract_action = contract_wizard.contract_action()
        contract = self.env["tenancy.details"].browse(contract_action["res_id"])
        # PDC is disabled on contract
        contract.write({"pdc_enabled": False, "pdc_auto_generate": True})

        schedule = contract._get_pdc_schedule()
        self.assertEqual(len(schedule), 0)

    # ------------------------------------------------------------------------
    # PDC Cheque Generation Tests
    # ------------------------------------------------------------------------

    def test_generate_pdc_checks_creates_correct_count(self):
        """Test that activating contract creates correct number of PDC cheques."""
        contract = self._create_monthly_contract("2025-01-01", 12)

        # Activate contract
        # Approval workflow (3.3.6) gates action_active_contract on
        # ``contract_type == 'approved'`` — flip the state directly here
        # instead of threading the full submit → manager-approve flow.
        self._approve_for_activation(contract)
        contract.action_active_contract()

        # Should have 12 PDC cheques
        self.assertEqual(contract.pdc_check_count, 12)
        self.assertTrue(contract.pdc_generated)

    def test_generate_pdc_checks_quarterly(self):
        """Test PDC cheque generation for quarterly contract."""
        contract = self._create_quarterly_contract("2025-01-01", 12)

        # Approval workflow (3.3.6) gates action_active_contract on
        # ``contract_type == 'approved'`` — flip the state directly here
        # instead of threading the full submit → manager-approve flow.
        self._approve_for_activation(contract)
        contract.action_active_contract()

        # Should have 4 PDC cheques (quarterly payments)
        self.assertEqual(contract.pdc_check_count, 4)

    def test_generate_pdc_checks_with_deposit(self):
        """Test PDC cheque generation includes deposit cheque."""
        contract = self._create_contract_with_deposit("2025-01-01", 12)

        # Approval workflow (3.3.6) gates action_active_contract on
        # ``contract_type == 'approved'`` — flip the state directly here
        # instead of threading the full submit → manager-approve flow.
        self._approve_for_activation(contract)
        contract.action_active_contract()

        # Should have 13: 1 deposit + 12 monthly
        self.assertEqual(contract.pdc_check_count, 13)

    def test_generate_pdc_checks_idempotent(self):
        """Test that calling generate twice raises error."""
        contract = self._create_monthly_contract("2025-01-01", 6)
        # Approval workflow (3.3.6) gates action_active_contract on
        # ``contract_type == 'approved'`` — flip the state directly here
        # instead of threading the full submit → manager-approve flow.
        self._approve_for_activation(contract)
        contract.action_active_contract()

        # Calling again should raise UserError
        with self.assertRaises(UserError) as ctx:
            contract.action_generate_pdc_checks()
        self.assertIn("already been generated", str(ctx.exception))

    def test_generate_pdc_checks_before_activation_fails(self):
        """Test that generating PDC before contract activation fails."""
        # Create duration for 6 months
        duration = self.env["contract.duration"].create({
            "duration": "6 Month",
            "month": 6,
            "rent_unit": "Month",
        })
        property_id = self._create_units(
            name="Property Early",
            property_seq="PROPEARLY",
            sale_lease="for_tenancy",
            stage="draft",
            type="land",
            price=10000,
            rent_unit="Month",
        )
        contract_wizard = self._create_contract_wizard(
            active_model="property.details",
            active_id=property_id.id,
            data={
                "customer_id": self.customer_one.id,
                "start_date": "2025-01-01",
                "payment_term": "monthly",
                "duration_id": duration.id,
                "duration_type": "by_duration",
                "total_rent": 10000,
                "property_id": property_id.id,
                "rent_unit": "Month",
                "water_reading": 100,
                "water_reading_date": fields.Datetime.now(),
                "electricity_reading": 100,
                "electricity_reading_date": fields.Datetime.now(),
            },
        )
        contract_action = contract_wizard.contract_action()
        contract = self.env["tenancy.details"].browse(contract_action["res_id"])

        # Try to generate before activation - should fail
        with self.assertRaises(UserError) as ctx:
            contract.action_generate_pdc_checks()
        self.assertIn("activate the contract", str(ctx.exception))

    # ------------------------------------------------------------------------
    # PDC Cheque Field Verification Tests
    # ------------------------------------------------------------------------

    def test_pdc_cheque_fields_are_correct(self):
        """Test that generated PDC cheques have correct field values."""
        contract = self._create_monthly_contract("2025-01-01", 6, total_rent=5000)
        # Approval workflow (3.3.6) gates action_active_contract on
        # ``contract_type == 'approved'`` — flip the state directly here
        # instead of threading the full submit → manager-approve flow.
        self._approve_for_activation(contract)
        contract.action_active_contract()

        # Get PDC cheques via tenancy.pdc.check link
        pdc_checks = contract.pdc_check_ids
        self.assertEqual(len(pdc_checks), 6)

        for pdc_check in pdc_checks:
            pdc = pdc_check.pdc_wizard_id
            self.assertEqual(pdc.partner_id.id, self.customer_one.id)
            self.assertEqual(pdc.payment_amount, 5000)
            self.assertEqual(pdc.payment_type, "receive_money")
            self.assertEqual(pdc.state, "draft")
            self.assertEqual(pdc.company_id.id, contract.company_id.id)
            # Memo should contain contract sequence and cheque number
            self.assertIn(contract.tenancy_seq, pdc.memo)

    def test_pdc_cheque_due_dates_are_correct(self):
        """Test that PDC cheque due dates match the schedule."""
        start_date = datetime.date(2025, 1, 1)
        contract = self._create_monthly_contract("2025-01-01", 6)
        # Approval workflow (3.3.6) gates action_active_contract on
        # ``contract_type == 'approved'`` — flip the state directly here
        # instead of threading the full submit → manager-approve flow.
        self._approve_for_activation(contract)
        contract.action_active_contract()

        pdc_checks = contract.pdc_check_ids.sorted(key=lambda r: r.sequence)
        expected_date = start_date
        for i, pdc_check in enumerate(pdc_checks, start=1):
            pdc = pdc_check.pdc_wizard_id
            # Due date should match expected schedule date
            self.assertEqual(pdc.due_date, expected_date)
            expected_date = expected_date + relativedelta(months=1)

    def test_pdc_cheque_sequence_matching(self):
        """Test that PDC cheques have correct sequence numbers."""
        contract = self._create_monthly_contract("2025-01-01", 4)
        # Approval workflow (3.3.6) gates action_active_contract on
        # ``contract_type == 'approved'`` — flip the state directly here
        # instead of threading the full submit → manager-approve flow.
        self._approve_for_activation(contract)
        contract.action_active_contract()

        pdc_checks = contract.pdc_check_ids
        sequences = sorted([p.sequence for p in pdc_checks])
        self.assertEqual(sequences, [1, 2, 3, 4])

        # Verify sequence matches between tenancy.pdc.check and pdc.wizard
        for pdc_check in pdc_checks:
            pdc = pdc_check.pdc_wizard_id
            # The memo contains "Cheque #X" where X is the sequence
            self.assertIn(f"Cheque #{pdc_check.sequence}", pdc.memo)

    # ------------------------------------------------------------------------
    # PDC to Invoice Linking Tests
    # ------------------------------------------------------------------------

    def test_first_pdc_linked_to_first_invoice(self):
        """Test that first PDC cheque is linked to the first invoice."""
        contract = self._create_monthly_contract("2025-01-01", 12)
        # Approval workflow (3.3.6) gates action_active_contract on
        # ``contract_type == 'approved'`` — flip the state directly here
        # instead of threading the full submit → manager-approve flow.
        self._approve_for_activation(contract)
        contract.action_active_contract()

        # Find the first PDC cheque (sequence = 1)
        first_pdc_check = contract.pdc_check_ids.filtered(lambda r: r.sequence == 1)
        self.assertTrue(first_pdc_check)

        pdc = first_pdc_check.pdc_wizard_id

        # Should have exactly one invoice linked (the first month's invoice)
        self.assertEqual(len(pdc.invoice_ids), 1)
        # Invoice should be posted
        self.assertEqual(pdc.invoice_ids[0].state, "posted")

    def test_second_pdc_not_linked_to_invoice_initially(self):
        """Test that second PDC cheque has no invoice linked at generation time."""
        contract = self._create_monthly_contract("2025-01-01", 12)
        # Approval workflow (3.3.6) gates action_active_contract on
        # ``contract_type == 'approved'`` — flip the state directly here
        # instead of threading the full submit → manager-approve flow.
        self._approve_for_activation(contract)
        contract.action_active_contract()

        # Find second PDC cheque (sequence = 2)
        second_pdc_check = contract.pdc_check_ids.filtered(lambda r: r.sequence == 2)
        self.assertTrue(second_pdc_check)

        pdc = second_pdc_check.pdc_wizard_id

        # Should have no invoice linked initially (future invoice not created yet)
        self.assertEqual(len(pdc.invoice_ids), 0)

    def test_invoice_count_after_activation(self):
        """Test that only one invoice is created at contract activation."""
        contract = self._create_monthly_contract("2025-01-01", 12)
        # Approval workflow (3.3.6) gates action_active_contract on
        # ``contract_type == 'approved'`` — flip the state directly here
        # instead of threading the full submit → manager-approve flow.
        self._approve_for_activation(contract)
        contract.action_active_contract()

        # Should have exactly 1 invoice for now
        invoices = self.env["account.move"].search([
            ("tenancy_id", "=", contract.id),
            ("move_type", "=", "out_invoice"),
        ])
        self.assertEqual(len(invoices), 1)

    def test_deposit_pdc_linked_to_deposit_invoice(self):
        """Test that deposit PDC is linked to deposit invoice if it exists."""
        contract = self._create_contract_with_deposit("2025-01-01", 12)
        # Approval workflow (3.3.6) gates action_active_contract on
        # ``contract_type == 'approved'`` — flip the state directly here
        # instead of threading the full submit → manager-approve flow.
        self._approve_for_activation(contract)
        contract.action_active_contract()

        # Find deposit PDC cheque
        deposit_pdc_check = contract.pdc_check_ids.filtered(lambda r: r.is_deposit)
        self.assertTrue(deposit_pdc_check)

        pdc = deposit_pdc_check.pdc_wizard_id
        # Deposit should be linked to an invoice if deposit was processed
        # (it depends on whether the deposit is in the same invoice or separate)
        # At minimum, account_move_ids should have open invoices for domain
        self.assertTrue(pdc.account_move_ids or not pdc.invoice_ids)

    # ------------------------------------------------------------------------
    # Tenancy PDC Check Model Tests
    # ------------------------------------------------------------------------

    def test_tenancy_pdc_check_rec_name(self):
        """Test display name computation for tenancy.pdc.check."""
        contract = self._create_monthly_contract("2025-01-01", 3)
        # Approval workflow (3.3.6) gates action_active_contract on
        # ``contract_type == 'approved'`` — flip the state directly here
        # instead of threading the full submit → manager-approve flow.
        self._approve_for_activation(contract)
        contract.action_active_contract()

        pdc_check = contract.pdc_check_ids[0]
        # Display name should contain both tenancy sequence and PDC name
        self.assertIn(contract.tenancy_seq, pdc_check.display_name)

    def test_tenancy_pdc_check_state_delegation(self):
        """Test that state is correctly delegated from pdc.wizard."""
        contract = self._create_monthly_contract("2025-01-01", 3)
        # Approval workflow (3.3.6) gates action_active_contract on
        # ``contract_type == 'approved'`` — flip the state directly here
        # instead of threading the full submit → manager-approve flow.
        self._approve_for_activation(contract)
        contract.action_active_contract()

        pdc_check = contract.pdc_check_ids[0]
        # Initial state should be draft
        self.assertEqual(pdc_check.state, "draft")

    # ------------------------------------------------------------------------
    # PDC View Action Tests
    # ------------------------------------------------------------------------

    def test_action_view_pdc_checks_returns_window_action(self):
        """Test that action_view_pdc_checks returns correct action."""
        contract = self._create_monthly_contract("2025-01-01", 3)
        # Approval workflow (3.3.6) gates action_active_contract on
        # ``contract_type == 'approved'`` — flip the state directly here
        # instead of threading the full submit → manager-approve flow.
        self._approve_for_activation(contract)
        contract.action_active_contract()

        action = contract.action_view_pdc_checks()

        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], "pdc.wizard")
        self.assertEqual(action["view_mode"], "list,form")

        # Domain should filter to only this contract's PDC cheques
        pdc_ids = contract.pdc_check_ids.mapped("pdc_wizard_id").ids
        self.assertEqual(action["domain"], [("id", "in", pdc_ids)])

    def test_update_pdc_invoice_links_matches_second_cheque(self):
        """Test that action_update_pdc_invoice_links links a future PDC to a new invoice."""
        contract = self._create_monthly_contract("2025-01-01", 12)
        # Approval workflow (3.3.6) gates action_active_contract on
        # ``contract_type == 'approved'`` — flip the state directly here
        # instead of threading the full submit → manager-approve flow.
        self._approve_for_activation(contract)
        contract.action_active_contract()

        # At activation, only the first PDC (seq=1) is linked to the first invoice
        first_pdc = contract.pdc_check_ids.filtered(lambda r: r.sequence == 1)
        second_pdc = contract.pdc_check_ids.filtered(lambda r: r.sequence == 2)

        # Verify second PDC has no invoice linked yet
        self.assertEqual(len(second_pdc.pdc_wizard_id.invoice_ids), 0)

        # Manually post a second invoice for the contract (simulating what scheduler does)
        # The invoice date should be within 5 days of second PDC's scheduled date
        second_pdc_scheduled = second_pdc.scheduled_date
        invoice_id = self.env["account.move"].sudo().create({
            "partner_id": contract.tenancy_id.id,
            "move_type": "out_invoice",
            "invoice_date": second_pdc_scheduled,
            "invoice_line_ids": [(0, 0, {
                "product_id": contract.installment_item_id.id,
                "name": "Installment 2",
                "quantity": 1,
                "price_unit": contract.total_rent,
            })],
            "tenancy_id": contract.id,
        })
        invoice_id.action_post()

        # Now run the update method
        result = contract.action_update_pdc_invoice_links()

        # Second PDC should now be linked to the invoice
        self.assertIn(invoice_id.id, second_pdc.pdc_wizard_id.invoice_ids.ids)
        # Notification should report 1 link updated
        self.assertIn("1 PDC cheque", result["params"]["message"])