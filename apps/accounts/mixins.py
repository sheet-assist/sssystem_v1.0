from django.contrib.auth.mixins import UserPassesTestMixin, LoginRequiredMixin


class AdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        user = self.request.user
        return hasattr(user, 'profile') and user.profile.is_admin


class ProspectsAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        user = self.request.user
        if not hasattr(user, 'profile'):
            return False
        return user.profile.can_view_prospects or user.profile.is_admin


class CasesAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        user = self.request.user
        if not hasattr(user, 'profile'):
            return False
        return user.profile.can_view_cases or user.profile.is_admin
