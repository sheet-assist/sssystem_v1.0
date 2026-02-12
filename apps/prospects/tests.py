from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.locations.models import County, State
from apps.prospects.models import (
    Prospect,
    ProspectActionLog,
    ProspectNote,
    ProspectRuleNote,
    add_rule_note,
    log_prospect_action,
)
from apps.settings_app.models import FilterCriteria

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

    def test_add_rule_note_helper(self):
        note = add_rule_note(
            self.prospect,
            note="Below surplus threshold",
            created_by=self.admin,
            rule_name="FL Rule",
            source="rule",
            decision="disqualified",
        )
        self.assertIsInstance(note, ProspectRuleNote)
        self.assertEqual(self.prospect.rule_notes.count(), 1)
        self.assertEqual(note.created_by, self.admin)
        self.assertEqual(note.rule_name, "FL Rule")
        self.assertEqual(note.decision, "disqualified")

    def test_add_rule_note_includes_reasons_on_fail(self):
        reasons = [
            "Assessed value $50,000 below minimum $75,000 (Rule A)",
            "Auction type 'TL' not in allowed ['TD'] (Rule A)",
        ]
        note = add_rule_note(
            self.prospect,
            note="Manual review override",
            reasons=reasons,
            created_by=self.admin,
            rule_name="Rule A",
            source="rule",
            decision="disqualified",
        )
        self.assertIn("Failed criteria", note.note)
        for reason in reasons:
            self.assertIn(reason, note.note)
        self.assertGreaterEqual(note.note.count("- "), len(reasons))

    def test_add_rule_note_links_rule_and_decision(self):
        rule = FilterCriteria.objects.create(name="Auto Rule", prospect_types=["TD"])
        note = add_rule_note(
            self.prospect,
            created_by=self.admin,
            rule=rule,
            source="rule",
            decision="qualified",
        )
        self.assertEqual(note.rule, rule)
        self.assertEqual(note.rule_name, "Auto Rule")
        self.assertEqual(note.decision, "qualified")


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
        other_state = State.objects.create(name="Georgia", abbreviation="GA")
        County.objects.create(
            state=other_state,
            name="Fulton",
            slug="fulton",
            available_prospect_types=["TD"],
        )
        resp = self.client.get("/prospects/browse/TD/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Florida")
        self.assertNotContains(resp, "Georgia")
        self.assertContains(resp, "1/1")
        self.assertContains(resp, "Show All States")

        resp_all = self.client.get("/prospects/browse/TD/?show_all=1")
        self.assertEqual(resp_all.status_code, 200)
        self.assertContains(resp_all, "Georgia")

    def test_county_select_page(self):
        Prospect.objects.create(
            prospect_type="TD",
            case_number="2024-DQ-COUNTY",
            county=self.county,
            auction_date=date(2024, 6, 16),
            qualification_status="disqualified",
        )
        County.objects.create(
            state=self.state,
            name="Orange",
            slug="orange",
            available_prospect_types=["TD"],
        )
        resp = self.client.get("/prospects/browse/TD/FL/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Miami-Dade")
        self.assertNotContains(resp, "Orange")
        self.assertContains(resp, "Show All Counties")
        self.assertContains(resp, "1/2")
        self.assertContains(resp, "/prospects/browse/TD/FL/miami-dade/")
        self.assertContains(resp, "/prospects/calendar/?type=TD&state=FL&county=miami-dade")

        resp_all = self.client.get("/prospects/browse/TD/FL/?show_all=1")
        self.assertEqual(resp_all.status_code, 200)
        self.assertContains(resp_all, "Orange")

    def test_prospect_list_page(self):
        resp = self.client.get("/prospects/browse/TD/FL/miami-dade/")
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
        resp = self.client.get("/prospects/browse/TD/FL/miami-dade/?qualification_status=qualified")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "2024-001234")
        self.assertNotContains(resp, "2024-DQ")

    def test_calendar_count_links_to_filtered_list(self):
        Prospect.objects.create(
            prospect_type="TD",
            case_number="2024-DQ-SAME-DAY",
            county=self.county,
            auction_date=date(2024, 6, 15),
            qualification_status="disqualified",
        )
        resp = self.client.get("/prospects/calendar/?type=TD&state=FL&county=miami-dade&year=2024&month=6")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Qualified 1/2")
        self.assertContains(
            resp,
            "/prospects/browse/TD/all/?auction_date_from=2024-06-15&amp;auction_date_to=2024-06-15&amp;state=FL&amp;county=miami-dade&amp;qualification_status=qualified",
        )
        self.assertContains(
            resp,
            "/prospects/browse/TD/all/?auction_date_from=2024-06-15&amp;auction_date_to=2024-06-15&amp;state=FL&amp;county=miami-dade\"",
        )
        qualified_resp = self.client.get(
            "/prospects/browse/TD/all/?auction_date_from=2024-06-15&auction_date_to=2024-06-15&state=FL&county=miami-dade&qualification_status=qualified"
        )
        self.assertEqual(qualified_resp.status_code, 200)
        self.assertContains(qualified_resp, "2024-001234")
        self.assertNotContains(qualified_resp, "2024-DQ-SAME-DAY")

    def test_state_select_has_state_filtered_calendar_link(self):
        resp = self.client.get("/prospects/browse/TD/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "/prospects/calendar/?type=TD&state=FL")


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
