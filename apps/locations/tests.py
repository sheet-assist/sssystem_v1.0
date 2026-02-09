from django.core.management import call_command
from django.test import TestCase

from apps.locations.models import County, State


class LoadStatesTest(TestCase):
    def test_creates_50_states(self):
        call_command("load_states")
        self.assertEqual(State.objects.count(), 50)
        self.assertTrue(State.objects.filter(abbreviation="FL").exists())

    def test_idempotent(self):
        call_command("load_states")
        call_command("load_states")
        self.assertEqual(State.objects.count(), 50)


class LoadFLCountiesTest(TestCase):
    def setUp(self):
        call_command("load_states")

    def test_creates_67_counties(self):
        call_command("load_fl_counties")
        fl = State.objects.get(abbreviation="FL")
        self.assertEqual(County.objects.filter(state=fl).count(), 67)

    def test_counties_have_urls(self):
        call_command("load_fl_counties")
        miami = County.objects.get(slug="miami-dade")
        self.assertIn("realforeclose.com", miami.foreclosure_url)
        self.assertIn("realtaxdeed.com", miami.taxdeed_url)
        self.assertEqual(miami.available_prospect_types, ["TD"])

    def test_idempotent(self):
        call_command("load_fl_counties")
        call_command("load_fl_counties")
        fl = State.objects.get(abbreviation="FL")
        self.assertEqual(County.objects.filter(state=fl).count(), 67)


class CountyModelTest(TestCase):
    def setUp(self):
        self.state = State.objects.create(name="Florida", abbreviation="FL")
        self.county = County.objects.create(
            state=self.state, name="Test County", slug="test-county"
        )

    def test_str(self):
        self.assertEqual(str(self.county), "Test County, FL")

    def test_update_last_scraped(self):
        self.assertIsNone(self.county.last_scraped)
        self.county.update_last_scraped()
        self.county.refresh_from_db()
        self.assertIsNotNone(self.county.last_scraped)
