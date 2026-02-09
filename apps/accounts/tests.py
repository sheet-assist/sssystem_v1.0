from django.contrib.auth import get_user_model
from django.test import Client, TestCase

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
