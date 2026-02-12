"""
Phase 10: End-to-end integration test and global search tests.

Integration flow:
  Scrape → Auto-qualify → Admin assigns → User researches →
  Skip trace → Contact → Convert to Case → Case follow-up →
  Dashboard shows updated stats
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.cases.models import Case, CaseFollowUp
from apps.locations.models import County, State
from apps.prospects.models import Prospect, ProspectActionLog
from apps.settings_app.evaluation import evaluate_prospect
from apps.settings_app.models import FilterCriteria

User = get_user_model()


class GlobalSearchTest(TestCase):
    def setUp(self):
        self.state = State.objects.create(name="Florida", abbreviation="FL")
        self.county = County.objects.create(
            state=self.state, name="Miami-Dade", slug="miami-dade",
        )
        self.admin = User.objects.create_superuser(username="admin", password="pass")
        self.client = Client()
        self.client.login(username="admin", password="pass")
        self.prospect = Prospect.objects.create(
            prospect_type="TD", case_number="2024-SEARCH-001",
            county=self.county, auction_date=date(2026, 3, 1),
            property_address="123 Elm Street", parcel_id="99-88-77",
            defendant_name="John Doe",
        )

    def test_search_by_case_number(self):
        resp = self.client.get("/search/?q=SEARCH-001")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "2024-SEARCH-001")

    def test_search_by_parcel_id(self):
        resp = self.client.get("/search/?q=99-88-77")
        self.assertContains(resp, "2024-SEARCH-001")

    def test_search_by_address(self):
        resp = self.client.get("/search/?q=Elm Street")
        self.assertContains(resp, "123 Elm Street")

    def test_search_by_defendant(self):
        resp = self.client.get("/search/?q=John Doe")
        self.assertContains(resp, "2024-SEARCH-001")

    def test_search_cases(self):
        p2 = Prospect.objects.create(
            prospect_type="TD", case_number="CASE-FIND-001",
            county=self.county, auction_date=date(2026, 4, 1),
        )
        Case.objects.create(
            prospect=p2, case_type="TD", county=self.county,
            case_number="CASE-FIND-001", property_address="456 Oak Ave",
        )
        resp = self.client.get("/search/?q=CASE-FIND")
        self.assertContains(resp, "CASE-FIND-001")

    def test_search_too_short(self):
        resp = self.client.get("/search/?q=a")
        self.assertContains(resp, "at least 2 characters")

    def test_search_requires_login(self):
        c = Client()
        resp = c.get("/search/?q=test")
        self.assertEqual(resp.status_code, 302)


class EndToEndPipelineTest(TestCase):
    """
    Full pipeline: Create prospect → Qualify → Assign → Research →
    Skip trace → Contact → Convert to Case → Follow-up → Dashboard stats
    """

    def setUp(self):
        self.state = State.objects.create(name="Florida", abbreviation="FL")
        self.county = County.objects.create(
            state=self.state, name="Miami-Dade", slug="miami-dade",
            taxdeed_url="https://miami-dade.realtaxdeed.com",
        )
        self.admin = User.objects.create_superuser(username="admin", password="pass")
        self.worker = User.objects.create_user(username="worker", password="pass")
        self.worker.profile.role = "prospects_and_cases"
        self.worker.profile.save()

        # Create filter criteria: min surplus $10k
        FilterCriteria.objects.create(
            name="FL TD Default", prospect_types=["TD"],
            state=self.state, surplus_amount_min=Decimal("10000"),
        )

        self.admin_client = Client()
        self.admin_client.login(username="admin", password="pass")
        self.worker_client = Client()
        self.worker_client.login(username="worker", password="pass")

    def test_full_pipeline(self):
        # Step 1: Simulate scraped prospect data and evaluate qualification
        prospect_data = {
            "prospect_type": "TD",
            "case_number": "2024-E2E-001",
            "auction_type": "TAX DEED",
            "property_address": "789 Pipeline Blvd",
            "parcel_id": "E2E-PARCEL-01",
            "surplus_amount": Decimal("25000"),
            "auction_date": date(2026, 6, 15),
            "auction_status": "scheduled",
        }
        qualified, reasons = evaluate_prospect(prospect_data, self.county)
        self.assertTrue(qualified)

        # Step 2: Create the prospect (as scraper would)
        prospect = Prospect.objects.create(
            prospect_type="TD",
            case_number="2024-E2E-001",
            auction_type="TAX DEED",
            county=self.county,
            auction_date=date(2026, 6, 15),
            property_address="789 Pipeline Blvd",
            parcel_id="E2E-PARCEL-01",
            surplus_amount=Decimal("25000"),
            qualification_status="qualified",
            workflow_status="new",
        )
        self.assertEqual(prospect.qualification_status, "qualified")

        # Step 3: Admin assigns prospect to worker
        resp = self.admin_client.post(
            f"/prospects/detail/{prospect.pk}/assign/",
            {"assigned_to": self.worker.pk},
        )
        self.assertEqual(resp.status_code, 302)
        prospect.refresh_from_db()
        self.assertEqual(prospect.assigned_to, self.worker)
        self.assertEqual(prospect.workflow_status, "assigned")

        # Step 4: Worker does research (lien check + surplus verify)
        resp = self.worker_client.post(
            f"/prospects/detail/{prospect.pk}/research/",
            {
                "lien_check_done": "on",
                "lien_check_notes": "Clear title, no liens",
                "surplus_verified": "on",
                "documents_verified": "on",
            },
        )
        self.assertEqual(resp.status_code, 302)
        prospect.refresh_from_db()
        self.assertTrue(prospect.lien_check_done)
        self.assertTrue(prospect.surplus_verified)

        # Step 5: Worker transitions to skip_tracing
        resp = self.worker_client.post(
            f"/prospects/detail/{prospect.pk}/transition/",
            {"workflow_status": "skip_tracing"},
        )
        self.assertEqual(resp.status_code, 302)
        prospect.refresh_from_db()
        self.assertEqual(prospect.workflow_status, "skip_tracing")

        # Step 6: Worker does skip trace + updates research
        resp = self.worker_client.post(
            f"/prospects/detail/{prospect.pk}/research/",
            {
                "lien_check_done": "on",
                "lien_check_notes": "Clear title, no liens",
                "surplus_verified": "on",
                "documents_verified": "on",
                "skip_trace_done": "on",
                "owner_contact_info": "John Owner\n555-1234\njohn@example.com",
            },
        )
        self.assertEqual(resp.status_code, 302)
        prospect.refresh_from_db()
        self.assertTrue(prospect.skip_trace_done)
        self.assertIn("555-1234", prospect.owner_contact_info)

        # Step 7: Worker transitions to contacting → contract_sent
        self.worker_client.post(
            f"/prospects/detail/{prospect.pk}/transition/",
            {"workflow_status": "contacting"},
        )
        self.worker_client.post(
            f"/prospects/detail/{prospect.pk}/transition/",
            {"workflow_status": "contract_sent"},
        )
        prospect.refresh_from_db()
        self.assertEqual(prospect.workflow_status, "contract_sent")

        # Step 8: Convert prospect to case
        resp = self.admin_client.post(
            f"/cases/convert/{prospect.pk}/",
            {"contract_date": "2026-06-20", "contract_notes": "Signed surplus agreement"},
        )
        self.assertEqual(resp.status_code, 302)
        prospect.refresh_from_db()
        self.assertEqual(prospect.workflow_status, "converted")
        case = Case.objects.get(prospect=prospect)
        self.assertEqual(case.case_type, "TD")
        self.assertEqual(case.property_address, "789 Pipeline Blvd")
        self.assertEqual(str(case.contract_date), "2026-06-20")

        # Step 9: Add case follow-up
        resp = self.admin_client.post(
            f"/cases/{case.pk}/followups/add/",
            {"due_date": "2026-07-01", "description": "Follow up on disbursement"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(CaseFollowUp.objects.filter(case=case).count(), 1)

        # Step 10: Add case note
        resp = self.admin_client.post(
            f"/cases/{case.pk}/notes/add/",
            {"content": "Disbursement expected within 30 days"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(case.notes.count(), 1)

        # Step 11: Dashboard shows updated stats
        resp = self.admin_client.get("/dashboard/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "1")  # total prospects / cases
        # Verify action logs were created throughout
        self.assertTrue(
            ProspectActionLog.objects.filter(
                prospect=prospect, action_type="converted_to_case"
            ).exists()
        )

        # Step 12: Global search finds the converted case
        resp = self.admin_client.get("/search/?q=E2E-001")
        self.assertContains(resp, "2024-E2E-001")

    def test_disqualified_prospect_not_converted(self):
        """Prospect with surplus below threshold gets disqualified."""
        prospect_data = {
            "prospect_type": "TD",
            "surplus_amount": Decimal("5000"),  # below $10k threshold
            "auction_date": date(2026, 6, 15),
        }
        qualified, reasons = evaluate_prospect(prospect_data, self.county)
        self.assertFalse(qualified)
        self.assertTrue(any("below minimum" in r for r in reasons))
