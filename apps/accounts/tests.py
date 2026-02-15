from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.cases.models import Case
from apps.locations.models import County, State
from apps.prospects.models import Prospect, log_prospect_action
from apps.scraper.models import ScrapeJob

from .models import UserProfile

User = get_user_model()


class ProfileAutoCreationTest(TestCase):
    def test_profile_created_on_user_create(self):
        user = User.objects.create_user(username="tester", password="pass")
        self.assertTrue(hasattr(user, "profile"))
        self.assertIsInstance(user.profile, UserProfile)
        self.assertEqual(user.profile.role, UserProfile.ROLE_PROSPECTS_ONLY)


class RolePermissionsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="roleuser", password="pass")
        self.profile = self.user.profile

    def test_prospects_only(self):
        self.profile.role = UserProfile.ROLE_PROSPECTS_ONLY
        self.profile.save()
        self.assertTrue(self.profile.can_view_prospects)
        self.assertFalse(self.profile.can_view_cases)
        self.assertFalse(self.profile.is_admin)

    def test_cases_only(self):
        self.profile.role = UserProfile.ROLE_CASES_ONLY
        self.profile.save()
        self.assertFalse(self.profile.can_view_prospects)
        self.assertTrue(self.profile.can_view_cases)

    def test_both(self):
        self.profile.role = UserProfile.ROLE_BOTH
        self.profile.save()
        self.assertTrue(self.profile.can_view_prospects)
        self.assertTrue(self.profile.can_view_cases)

    def test_admin(self):
        self.profile.role = UserProfile.ROLE_ADMIN
        self.profile.save()
        self.assertTrue(self.profile.can_view_prospects)
        self.assertTrue(self.profile.can_view_cases)
        self.assertTrue(self.profile.is_admin)


class AuthViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="authuser", password="testpass123")

    def test_login_page_renders(self):
        resp = self.client.get("/accounts/login/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Surplus Squad")

    def test_login_success_redirects_to_dashboard(self):
        resp = self.client.post("/accounts/login/", {"username": "authuser", "password": "testpass123"})
        self.assertRedirects(resp, "/dashboard/")

    def test_logout_redirects_to_login(self):
        self.client.login(username="authuser", password="testpass123")
        resp = self.client.get("/accounts/logout/")
        self.assertRedirects(resp, "/accounts/login/")

    def test_profile_requires_login(self):
        resp = self.client.get("/accounts/profile/")
        self.assertEqual(resp.status_code, 302)

    def test_profile_renders_for_logged_in(self):
        self.client.login(username="authuser", password="testpass123")
        resp = self.client.get("/accounts/profile/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "authuser")


class AccessControlTest(TestCase):
    def test_user_list_admin_only(self):
        user = User.objects.create_user(username="regular", password="pass")
        user.profile.role = UserProfile.ROLE_PROSPECTS_ONLY
        user.profile.save()
        c = Client()
        c.login(username="regular", password="pass")
        resp = c.get("/accounts/users/")
        self.assertEqual(resp.status_code, 403)

    def test_user_list_accessible_to_admin(self):
        admin = User.objects.create_superuser(username="adm", password="pass")
        c = Client()
        c.login(username="adm", password="pass")
        resp = c.get("/accounts/users/")
        self.assertEqual(resp.status_code, 200)


class DashboardTest(TestCase):
    def setUp(self):
        self.state = State.objects.create(name="Florida", abbreviation="FL")
        self.county = County.objects.create(
            state=self.state, name="Miami-Dade", slug="miami-dade",
            taxdeed_url="https://miami-dade.realtaxdeed.com",
        )
        self.admin = User.objects.create_superuser(username="admin", password="pass")
        self.user = User.objects.create_user(username="worker", password="pass")
        self.client = Client()

    def test_dashboard_requires_login(self):
        resp = self.client.get("/dashboard/")
        self.assertEqual(resp.status_code, 302)

    def test_dashboard_renders_for_admin(self):
        self.client.login(username="admin", password="pass")
        resp = self.client.get("/dashboard/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Dashboard")
        self.assertContains(resp, "Total Prospects")
        self.assertContains(resp, "Active Cases")
        self.assertContains(resp, "Conversion Rate")
        self.assertContains(resp, "Qualified Surplus Amount")
        self.assertContains(resp, "Total Revenue")
        self.assertContains(resp, "Daily Qualified Count (Last 30 Days)")
        self.assertContains(resp, "Prospect Conversion % (Assigned to Converted by User)")

    def test_dashboard_shows_correct_prospect_counts(self):
        Prospect.objects.create(
            prospect_type="TD", case_number="001", county=self.county,
            auction_date=date(2026, 3, 1), qualification_status="qualified",
        )
        Prospect.objects.create(
            prospect_type="TD", case_number="002", county=self.county,
            auction_date=date(2026, 3, 1), qualification_status="disqualified",
        )
        Prospect.objects.create(
            prospect_type="TD", case_number="003", county=self.county,
            auction_date=date(2026, 3, 1), qualification_status="pending",
        )
        self.client.login(username="admin", password="pass")
        resp = self.client.get("/dashboard/")
        self.assertContains(resp, "3")  # total
        self.assertContains(resp, "1 qualified")
        self.assertContains(resp, "1 disqualified")
        self.assertContains(resp, "1 pending")

    def test_dashboard_shows_case_stats(self):
        p = Prospect.objects.create(
            prospect_type="TD", case_number="100", county=self.county,
            auction_date=date(2026, 3, 1),
        )
        Case.objects.create(prospect=p, case_type="TD", county=self.county, status="active")
        self.client.login(username="admin", password="pass")
        resp = self.client.get("/dashboard/")
        self.assertContains(resp, "1")  # active cases

    def test_dashboard_pipeline(self):
        Prospect.objects.create(
            prospect_type="TD", case_number="P1", county=self.county,
            auction_date=date(2026, 3, 1), workflow_status="new",
        )
        Prospect.objects.create(
            prospect_type="TD", case_number="P2", county=self.county,
            auction_date=date(2026, 3, 1), workflow_status="assigned",
        )
        self.client.login(username="admin", password="pass")
        resp = self.client.get("/dashboard/")
        self.assertContains(resp, "Prospect Pipeline")
        self.assertContains(resp, "New")
        self.assertContains(resp, "Assigned")

    def test_dashboard_recent_activity(self):
        p = Prospect.objects.create(
            prospect_type="TD", case_number="ACT-001", county=self.county,
            auction_date=date(2026, 3, 1),
        )
        log_prospect_action(p, self.admin, "created", "Test action")
        self.client.login(username="admin", password="pass")
        resp = self.client.get("/dashboard/")
        self.assertContains(resp, "Recent Activity")
        self.assertContains(resp, "ACT-001")

    def test_dashboard_scraper_status_admin_only(self):
        ScrapeJob.objects.create(
            name="Dashboard Job",
            county=self.county, job_type="TD", target_date=date(2026, 3, 1),
        )
        self.client.login(username="admin", password="pass")
        resp = self.client.get("/dashboard/")
        self.assertContains(resp, "Scraper Status")

    def test_dashboard_non_admin_shows_my_work(self):
        self.user.profile.role = "prospects_and_cases"
        self.user.profile.save()
        self.client.login(username="worker", password="pass")
        resp = self.client.get("/dashboard/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "My Work")
        self.assertNotContains(resp, "Scraper Status")
