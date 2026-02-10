from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.locations.models import County, State
from apps.prospects.models import Prospect, ProspectActionLog, ProspectNote, log_prospect_action

User = get_user_model()


class ProspectTestMixin:
    """Shared setup for prospect tests."""

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
        )


class ProspectModelTest(ProspectTestMixin, TestCase):
    def test_str(self):
        self.assertIn("2024-001234", str(self.prospect))

    def test_unique_constraint(self):
        with self.assertRaises(Exception):
            Prospect.objects.create(
                prospect_type="TD",
                case_number="2024-001234",
                county=self.county,
                auction_date=date(2024, 6, 15),
            )

    def test_different_date_allowed(self):
        p2 = Prospect.objects.create(
            prospect_type="TD",
            case_number="2024-001234",
            county=self.county,
            auction_date=date(2024, 7, 15),
        )
        self.assertIsNotNone(p2.pk)

    def test_log_prospect_action(self):
        log = log_prospect_action(self.prospect, self.admin, "created", "Test log")
        self.assertEqual(log.action_type, "created")
        self.assertEqual(ProspectActionLog.objects.filter(prospect=self.prospect).count(), 1)


class ProspectNoteTest(ProspectTestMixin, TestCase):
    def test_create_note(self):
        note = ProspectNote.objects.create(
            prospect=self.prospect, author=self.user, content="Test note"
        )
        self.assertEqual(self.prospect.notes.count(), 1)
        self.assertIn("2024-001234", str(note))


class NavigationFlowTest(ProspectTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.client.login(username="admin", password="pass")

    def test_type_select_page(self):
        resp = self.client.get("/prospects/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Tax Deed")

    def test_state_select_page(self):
        resp = self.client.get("/prospects/TD/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Florida")

    def test_county_select_page(self):
        resp = self.client.get("/prospects/TD/FL/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Miami-Dade")

    def test_prospect_list_page(self):
        resp = self.client.get("/prospects/TD/FL/miami-dade/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "2024-001234")

    def test_prospect_detail_page(self):
        resp = self.client.get(f"/prospects/detail/{self.prospect.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "2024-001234")

    def test_prospect_list_filters(self):
        # Create a disqualified prospect
        Prospect.objects.create(
            prospect_type="TD", case_number="2024-DQ",
            county=self.county, auction_date=date(2024, 6, 16),
            qualification_status="disqualified",
        )
        # Filter for qualified only
        resp = self.client.get("/prospects/TD/FL/miami-dade/?qualification_status=qualified")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "2024-001234")
        self.assertNotContains(resp, "2024-DQ")


class AssignmentWorkflowTest(ProspectTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.client.login(username="admin", password="pass")

    def test_assign_prospect(self):
        resp = self.client.post(
            f"/prospects/detail/{self.prospect.pk}/assign/",
            {"assigned_to": self.user.pk},
        )
        self.assertEqual(resp.status_code, 302)
        self.prospect.refresh_from_db()
        self.assertEqual(self.prospect.assigned_to, self.user)
        self.assertEqual(self.prospect.workflow_status, "assigned")
        self.assertTrue(ProspectActionLog.objects.filter(
            prospect=self.prospect, action_type="assigned"
        ).exists())

    def test_add_note(self):
        resp = self.client.post(
            f"/prospects/detail/{self.prospect.pk}/notes/add/",
            {"content": "Important finding"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.prospect.notes.count(), 1)

    def test_workflow_transition(self):
        resp = self.client.post(
            f"/prospects/detail/{self.prospect.pk}/transition/",
            {"workflow_status": "researching"},
        )
        self.assertEqual(resp.status_code, 302)
        self.prospect.refresh_from_db()
        self.assertEqual(self.prospect.workflow_status, "researching")

    def test_research_update(self):
        resp = self.client.post(
            f"/prospects/detail/{self.prospect.pk}/research/",
            {"lien_check_done": True, "surplus_verified": True},
        )
        self.assertEqual(resp.status_code, 302)
        self.prospect.refresh_from_db()
        self.assertTrue(self.prospect.lien_check_done)
        self.assertTrue(self.prospect.surplus_verified)

    def test_history_page(self):
        log_prospect_action(self.prospect, self.admin, "created", "Test")
        resp = self.client.get(f"/prospects/detail/{self.prospect.pk}/history/")
        self.assertEqual(resp.status_code, 200)

    def test_my_prospects(self):
        self.prospect.assigned_to = self.user
        self.prospect.save()
        c = Client()
        c.login(username="worker", password="pass")
        resp = c.get("/prospects/my/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "2024-001234")


class AccessControlTest(ProspectTestMixin, TestCase):
    def test_cases_only_user_cannot_see_prospects(self):
        self.user.profile.role = "cases_only"
        self.user.profile.save()
        c = Client()
        c.login(username="worker", password="pass")
        resp = c.get("/prospects/")
        self.assertEqual(resp.status_code, 403)

    def test_non_admin_cannot_assign(self):
        self.user.profile.role = "prospects_only"
        self.user.profile.save()
        c = Client()
        c.login(username="worker", password="pass")
        resp = c.post(f"/prospects/detail/{self.prospect.pk}/assign/", {"assigned_to": self.user.pk})
        self.assertEqual(resp.status_code, 403)
