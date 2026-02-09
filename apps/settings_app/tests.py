from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase

from apps.locations.models import County, State
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
            name="Test Rule", prospect_type="TD", state=self.state,
            min_surplus_amount=Decimal("10000"), is_active=True,
        )
        self.assertIn("Test Rule", str(rule))

    def test_scope_display(self):
        global_rule = FilterCriteria.objects.create(
            name="Global", prospect_type="TD"
        )
        self.assertIn("Global", str(global_rule))

        state_rule = FilterCriteria.objects.create(
            name="State", prospect_type="TD", state=self.state
        )
        self.assertIn("State: Florida", str(state_rule))

        county_rule = FilterCriteria.objects.create(
            name="County", prospect_type="TD", state=self.state, county=self.county
        )
        self.assertIn("County: Miami-Dade", str(county_rule))


class SeedCriteriaTest(TestCase):
    def test_seed_creates_default_rule(self):
        call_command("load_states")
        call_command("seed_criteria")
        rule = FilterCriteria.objects.get(name="Florida TD Default")
        self.assertTrue(rule.is_active)
        self.assertEqual(rule.min_surplus_amount, Decimal("10000"))
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
            name="FL TD Rule", prospect_type="TD", state=self.state,
            min_surplus_amount=Decimal("10000"),
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

    def test_disqualified_old_date(self):
        data = {
            "prospect_type": "TD",
            "surplus_amount": 15000,
            "auction_date": date(2023, 6, 1),
            "auction_status": "Live",
        }
        qualified, reasons = evaluate_prospect(data, self.county)
        self.assertFalse(qualified)

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
        self.assertTrue(any("No filter rules" in r for r in reasons))

    def test_county_rule_takes_precedence(self):
        # County-specific rule with lower threshold
        FilterCriteria.objects.create(
            name="Miami Low", prospect_type="TD",
            state=self.state, county=self.county,
            min_surplus_amount=Decimal("1000"),
            is_active=True,
        )
        data = {
            "prospect_type": "TD",
            "surplus_amount": 5000,
            "auction_date": date(2024, 6, 1),
        }
        # County rule (min 1000) should be used instead of state rule (min 10000)
        qualified, reasons = evaluate_prospect(data, self.county)
        self.assertTrue(qualified)


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
            "prospect_type": "TD",
            "state": state.pk,
            "min_surplus_amount": "5000",
            "is_active": True,
            "status_types": "[]",
            "auction_types": "[]",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(FilterCriteria.objects.filter(name="New Rule").exists())
