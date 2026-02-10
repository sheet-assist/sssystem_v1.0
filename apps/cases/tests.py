from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.locations.models import County, State
from apps.prospects.models import Prospect, log_prospect_action

from .models import Case, CaseActionLog, CaseFollowUp, CaseNote, log_case_action

User = get_user_model()


class CaseTestMixin:
    """Shared setup for case tests."""

    def setUp(self):
        self.state = State.objects.create(name="Florida", abbreviation="FL")
        self.county = County.objects.create(
            state=self.state, name="Miami-Dade", slug="miami-dade",
            available_prospect_types=["TD"],
        )
        self.admin = User.objects.create_superuser(username="admin", password="pass")
        self.user = User.objects.create_user(username="worker", password="pass")
        self.prospect = Prospect.objects.create(
            prospect_type="TD",
            case_number="2024-001234",
            county=self.county,
            auction_date=date(2024, 6, 15),
            surplus_amount=Decimal("15000.00"),
            qualification_status="qualified",
            workflow_status="contract_sent",
            property_address="123 Main St",
            parcel_id="12-34-56",
            assigned_to=self.user,
        )


class CaseModelTest(CaseTestMixin, TestCase):
    def test_create_case(self):
        case = Case.objects.create(
            prospect=self.prospect, case_type="TD", county=self.county,
            case_number="2024-001234", property_address="123 Main St",
        )
        self.assertEqual(str(case), "Case 2024-001234 (TD)")

    def test_case_status_default(self):
        case = Case.objects.create(
            prospect=self.prospect, case_type="TD", county=self.county,
        )
        self.assertEqual(case.status, "active")

    def test_log_case_action(self):
        case = Case.objects.create(
            prospect=self.prospect, case_type="TD", county=self.county,
        )
        log = log_case_action(case, self.admin, "created", "Test log")
        self.assertEqual(log.action_type, "created")
        self.assertEqual(CaseActionLog.objects.filter(case=case).count(), 1)

    def test_case_note(self):
        case = Case.objects.create(
            prospect=self.prospect, case_type="TD", county=self.county,
        )
        note = CaseNote.objects.create(case=case, author=self.user, content="Test note")
        self.assertEqual(case.notes.count(), 1)
        self.assertIn("Case", str(note))

    def test_case_followup(self):
        case = Case.objects.create(
            prospect=self.prospect, case_type="TD", county=self.county,
        )
        fu = CaseFollowUp.objects.create(
            case=case, assigned_to=self.user,
            due_date=date(2024, 7, 1), description="Call owner",
        )
        self.assertFalse(fu.is_completed)
        self.assertEqual(case.followups.count(), 1)


class ConvertProspectTest(CaseTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.client.login(username="admin", password="pass")

    def test_convert_prospect_to_case(self):
        resp = self.client.post(
            f"/cases/convert/{self.prospect.pk}/",
            {"contract_date": "2024-06-20", "contract_notes": "Signed contract"},
        )
        self.assertEqual(resp.status_code, 302)
        case = Case.objects.get(prospect=self.prospect)
        self.assertEqual(case.case_type, "TD")
        self.assertEqual(case.property_address, "123 Main St")
        self.assertEqual(case.parcel_id, "12-34-56")
        self.assertEqual(case.contract_date, date(2024, 6, 20))
        self.assertEqual(case.contract_notes, "Signed contract")
        self.prospect.refresh_from_db()
        self.assertEqual(self.prospect.workflow_status, "converted")

    def test_convert_already_converted(self):
        # First conversion
        self.client.post(f"/cases/convert/{self.prospect.pk}/", {})
        # Second attempt should redirect
        resp = self.client.post(f"/cases/convert/{self.prospect.pk}/", {})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Case.objects.filter(prospect=self.prospect).count(), 1)

    def test_convert_creates_action_logs(self):
        self.client.post(f"/cases/convert/{self.prospect.pk}/", {})
        case = Case.objects.get(prospect=self.prospect)
        self.assertTrue(CaseActionLog.objects.filter(case=case, action_type="created").exists())
        from apps.prospects.models import ProspectActionLog
        self.assertTrue(ProspectActionLog.objects.filter(
            prospect=self.prospect, action_type="converted_to_case"
        ).exists())


class CaseViewsTest(CaseTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.client.login(username="admin", password="pass")
        self.case = Case.objects.create(
            prospect=self.prospect, case_type="TD", county=self.county,
            case_number="2024-001234", property_address="123 Main St",
            assigned_to=self.user,
        )

    def test_case_list(self):
        resp = self.client.get("/cases/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "2024-001234")

    def test_case_list_filter_type(self):
        resp = self.client.get("/cases/?case_type=TD")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "2024-001234")
        resp2 = self.client.get("/cases/?case_type=SS")
        self.assertNotContains(resp2, "2024-001234")

    def test_case_detail(self):
        resp = self.client.get(f"/cases/{self.case.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "2024-001234")
        self.assertContains(resp, "123 Main St")

    def test_add_case_note(self):
        resp = self.client.post(
            f"/cases/{self.case.pk}/notes/add/",
            {"content": "Important finding"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.case.notes.count(), 1)
        self.assertTrue(CaseActionLog.objects.filter(case=self.case, action_type="note_added").exists())

    def test_add_followup(self):
        resp = self.client.post(
            f"/cases/{self.case.pk}/followups/add/",
            {"due_date": "2024-07-01", "description": "Call owner"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.case.followups.count(), 1)

    def test_complete_followup(self):
        fu = CaseFollowUp.objects.create(
            case=self.case, due_date=date(2024, 7, 1), description="Call",
        )
        resp = self.client.post(f"/cases/{self.case.pk}/followups/{fu.pk}/complete/")
        self.assertEqual(resp.status_code, 302)
        fu.refresh_from_db()
        self.assertTrue(fu.is_completed)
        self.assertIsNotNone(fu.completed_at)

    def test_status_update(self):
        resp = self.client.post(
            f"/cases/{self.case.pk}/status/",
            {"status": "closed_won"},
        )
        self.assertEqual(resp.status_code, 302)
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, "closed_won")

    def test_case_history(self):
        log_case_action(self.case, self.admin, "created", "Test")
        resp = self.client.get(f"/cases/{self.case.pk}/history/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "created")


class CaseAccessControlTest(CaseTestMixin, TestCase):
    def test_prospects_only_user_cannot_see_cases(self):
        self.user.profile.role = "prospects_only"
        self.user.profile.save()
        c = Client()
        c.login(username="worker", password="pass")
        resp = c.get("/cases/")
        self.assertEqual(resp.status_code, 403)

    def test_cases_only_user_can_see_cases(self):
        self.user.profile.role = "cases_only"
        self.user.profile.save()
        c = Client()
        c.login(username="worker", password="pass")
        resp = c.get("/cases/")
        self.assertEqual(resp.status_code, 200)
