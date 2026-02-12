from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from apps.locations.models import County, State
from apps.prospects.models import Prospect
from apps.settings_app.evaluation import evaluate_prospect
from apps.settings_app.models import FilterCriteria

User = get_user_model()


class FilterCriteriaModelTest(TestCase):
    def setUp(self):
        self.state = State.objects.create(name="Florida", abbreviation="FL")
        self.county = County.objects.create(
            state=self.state, name="Miami-Dade", slug="miami-dade"
        )

    def test_create_rule(self):
        rule = FilterCriteria.objects.create(
            name="Test Rule", prospect_types=["TD"], state=self.state,
            surplus_amount_min=Decimal("10000"), is_active=True,
        )
        self.assertIn("Test Rule", str(rule))

    def test_scope_display(self):
        global_rule = FilterCriteria.objects.create(
            name="Global", prospect_type="TD"
        )
        self.assertIn("Global", str(global_rule))

        state_rule = FilterCriteria.objects.create(
            name="State", prospect_types=["TD"], state=self.state
        )
        self.assertIn("State: Florida", str(state_rule))

        county_rule = FilterCriteria.objects.create(
            name="County", prospect_types=["TD"], state=self.state
        )
        county_rule.counties.add(self.county)
        self.assertIn("Counties: Miami-Dade", str(county_rule))

    def test_verbose_summary_all_counties_of_state(self):
        county2 = County.objects.create(
            state=self.state, name="Broward", slug="broward"
        )
        rule = FilterCriteria.objects.create(
            name="FL All Counties",
            prospect_types=["TD"],
            state=self.state,
            surplus_amount_min=Decimal("10000"),
            sold_to="3rd Party Bidder",
        )
        rule.counties.add(self.county, county2)
        summary = rule.get_verbose_summary()
        self.assertIn("Surplus amount higher than $10,000", summary)
        self.assertNotIn("for TD", summary)
        self.assertIn("sold to 3rd Party Bidder", summary)
        self.assertIn("in all counties of FL state", summary)
        self.assertIn("will be marked as qualified.", summary)

class SeedCriteriaTest(TestCase):
    def test_seed_creates_default_rule(self):
        call_command("load_states")
        call_command("seed_criteria")
        rule = FilterCriteria.objects.get(name="Florida TD Default")
        self.assertTrue(rule.is_active)
        self.assertEqual(rule.surplus_amount_min, Decimal("10000"))
        self.assertEqual(rule.min_date, date(2024, 1, 1))

    def test_seed_idempotent(self):
        call_command("load_states")
        call_command("seed_criteria")
        call_command("seed_criteria")
        self.assertEqual(FilterCriteria.objects.filter(name="Florida TD Default").count(), 1)


class EvaluateProspectTest(TestCase):
    def setUp(self):
        self.state = State.objects.create(name="Florida", abbreviation="FL")
        self.county = County.objects.create(
            state=self.state, name="Miami-Dade", slug="miami-dade"
        )
        FilterCriteria.objects.create(
            name="FL TD Rule", prospect_types=["TD"], state=self.state,
            surplus_amount_min=Decimal("10000"),
            min_date=date(2024, 1, 1),
            status_types=["Live", "Upcoming"],
            is_active=True,
        )

    def test_qualified_prospect(self):
        data = {
            "prospect_type": "TD",
            "surplus_amount": 15000,
            "auction_date": date(2024, 6, 1),
            "auction_status": "Live",
        }
        qualified, reasons = evaluate_prospect(data, self.county)
        self.assertTrue(qualified)

    def test_disqualified_low_surplus(self):
        data = {
            "prospect_type": "TD",
            "surplus_amount": 5000,
            "auction_date": date(2024, 6, 1),
            "auction_status": "Live",
        }
        qualified, reasons = evaluate_prospect(data, self.county)
        self.assertFalse(qualified)
        self.assertTrue(any("below minimum" in r for r in reasons))

    def test_old_date_outside_filter_range_is_not_evaluated(self):
        data = {
            "prospect_type": "TD",
            "surplus_amount": 15000,
            "auction_date": date(2023, 6, 1),
            "auction_status": "Live",
        }
        qualified, reasons = evaluate_prospect(data, self.county)
        self.assertTrue(qualified)
        self.assertTrue(any("No matching filter rules" in r for r in reasons))

    def test_disqualified_wrong_status(self):
        data = {
            "prospect_type": "TD",
            "surplus_amount": 15000,
            "auction_date": date(2024, 6, 1),
            "auction_status": "Cancelled",
        }
        qualified, reasons = evaluate_prospect(data, self.county)
        self.assertFalse(qualified)

    def test_no_rules_auto_qualifies(self):
        county2 = County.objects.create(
            state=self.state, name="Broward", slug="broward"
        )
        # Create a county-specific rule for Broward so state rule doesn't apply
        # Actually, remove all rules for a different type
        data = {
            "prospect_type": "TL",
            "surplus_amount": 500,
        }
        qualified, reasons = evaluate_prospect(data, county2)
        self.assertTrue(qualified)
        self.assertTrue(any("No matching filter rules" in r for r in reasons))

    def test_county_rule_takes_precedence(self):
        # County-specific rule with lower threshold
        rule = FilterCriteria.objects.create(
            name="Miami Low", prospect_types=["TD"],
            state=self.state,
            surplus_amount_min=Decimal("1000"),
            is_active=True,
        )
        rule.counties.add(self.county)
        data = {
            "prospect_type": "TD",
            "surplus_amount": 5000,
            "auction_date": date(2024, 6, 1),
        }
        # County rule (min 1000) should be used instead of state rule (min 10000)
        qualified, reasons = evaluate_prospect(data, self.county)
        self.assertTrue(qualified)

    def test_rule_matches_document_type_multiselect(self):
        mixed_rule = FilterCriteria.objects.create(
            name="TD and TL",
            prospect_types=["TD", "TL"],
            state=self.state,
            surplus_amount_min=Decimal("1000"),
            is_active=True,
        )
        mixed_rule.counties.add(self.county)

        td_data = {
            "prospect_type": "TD",
            "surplus_amount": 2000,
            "auction_date": date(2024, 7, 1),
            "auction_status": "Live",
        }
        td_qualified, _ = evaluate_prospect(td_data, self.county)
        self.assertTrue(td_qualified)

        mf_data = {
            "prospect_type": "MF",
            "surplus_amount": 2000,
            "auction_date": date(2024, 8, 1),
            "auction_status": "Live",
        }
        mf_qualified, mf_reasons = evaluate_prospect(mf_data, self.county)
        self.assertTrue(mf_qualified)
        self.assertTrue(any("No matching filter rules" in r for r in mf_reasons))


class CriteriaViewsTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username="adm", password="pass")
        self.user = User.objects.create_user(username="reg", password="pass")

    def test_settings_home_admin_only(self):
        c = Client()
        c.login(username="reg", password="pass")
        resp = c.get("/settings/")
        self.assertEqual(resp.status_code, 403)

    def test_settings_home_renders(self):
        c = Client()
        c.login(username="adm", password="pass")
        resp = c.get("/settings/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Filter Criteria")

    def test_criteria_list(self):
        c = Client()
        c.login(username="adm", password="pass")
        resp = c.get("/settings/criteria/")
        self.assertEqual(resp.status_code, 200)

    def test_criteria_create(self):
        state = State.objects.create(name="Florida", abbreviation="FL")
        c = Client()
        c.login(username="adm", password="pass")
        resp = c.post("/settings/criteria/add/", {
            "name": "New Rule",
            "prospect_types": ["TD", "TL"],
            "state": state.pk,
            "surplus_amount_min": "5000",
            "is_active": True,
            "status_types": [],
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(FilterCriteria.objects.filter(name="New Rule", prospect_types=["TD", "TL"]).exists())

    def test_apply_rule_endpoint_updates_prospects(self):
        state = State.objects.create(name="Florida", abbreviation="FL")
        county = County.objects.create(state=state, name="Miami-Dade", slug="miami-dade")
        rule = FilterCriteria.objects.create(
            name="Apply Test",
            prospect_types=["TD"],
            state=state,
            surplus_amount_min=Decimal("1000"),
            is_active=True,
        )
        rule.counties.add(county)
        prospect = Prospect.objects.create(
            prospect_type="TD",
            county=county,
            case_number="2024-XYZ",
            auction_date=date(2024, 6, 15),
            surplus_amount=Decimal("1500"),
            qualification_status="disqualified",
        )

        c = Client()
        c.login(username="adm", password="pass")
        resp = c.post(reverse("settings_app:criteria_apply", args=[rule.pk]))
        self.assertRedirects(resp, reverse("settings_app:criteria_edit", args=[rule.pk]))
        prospect.refresh_from_db()
        self.assertEqual(prospect.qualification_status, "qualified")
        self.assertEqual(prospect.rule_notes.filter(decision="qualified").count(), 1)
        note = prospect.rule_notes.first()
        self.assertEqual(note.created_by, self.admin)
        self.assertIn("applied by adm at", note.note or "")

    def test_apply_rule_records_rule_note_on_disqualification(self):
        state = State.objects.create(name="Florida", abbreviation="FL")
        county = County.objects.create(state=state, name="Miami-Dade", slug="miami-dade")
        rule = FilterCriteria.objects.create(
            name="Strict Surplus",
            prospect_types=["TD"],
            state=state,
            surplus_amount_min=Decimal("50000"),
            is_active=True,
        )
        rule.counties.add(county)
        prospect = Prospect.objects.create(
            prospect_type="TD",
            county=county,
            case_number="2024-LOW",
            auction_date=date(2024, 7, 1),
            surplus_amount=Decimal("1000"),
            qualification_status="qualified",
        )

        c = Client()
        c.login(username="adm", password="pass")
        resp = c.post(reverse("settings_app:criteria_apply", args=[rule.pk]))
        self.assertRedirects(resp, reverse("settings_app:criteria_edit", args=[rule.pk]))
        prospect.refresh_from_db()
        self.assertEqual(prospect.qualification_status, "disqualified")
        self.assertEqual(prospect.rule_notes.filter(decision="disqualified").count(), 1)
        note = prospect.rule_notes.first()
        self.assertEqual(note.created_by, self.admin)
        self.assertIn("Strict Surplus", note.note or "")
        self.assertIn("applied by adm at", note.note or "")

    def test_apply_rule_uses_date_filter_fields_for_target_records(self):
        state = State.objects.create(name="Florida", abbreviation="FL")
        county = County.objects.create(state=state, name="Miami-Dade", slug="miami-dade")
        rule = FilterCriteria.objects.create(
            name="Date Scoped Rule",
            prospect_types=["TD"],
            state=state,
            min_date=date(2024, 7, 1),
            max_date=date(2024, 7, 31),
            surplus_amount_min=Decimal("5000"),
            is_active=True,
        )
        rule.counties.add(county)
        in_range = Prospect.objects.create(
            prospect_type="TD",
            county=county,
            case_number="2024-IN",
            auction_date=date(2024, 7, 15),
            surplus_amount=Decimal("1000"),
            qualification_status="qualified",
        )
        out_of_range = Prospect.objects.create(
            prospect_type="TD",
            county=county,
            case_number="2024-OUT",
            auction_date=date(2024, 8, 5),
            surplus_amount=Decimal("1000"),
            qualification_status="qualified",
        )

        c = Client()
        c.login(username="adm", password="pass")
        resp = c.post(reverse("settings_app:criteria_apply", args=[rule.pk]))
        self.assertRedirects(resp, reverse("settings_app:criteria_edit", args=[rule.pk]))
        in_range.refresh_from_db()
        out_of_range.refresh_from_db()
        self.assertEqual(in_range.qualification_status, "disqualified")
        self.assertEqual(out_of_range.qualification_status, "qualified")
