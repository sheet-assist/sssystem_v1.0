from django.contrib.auth import logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView, ListView

from .mixins import AdminRequiredMixin
from .models import UserProfile


class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/profile.html"


class UserListView(AdminRequiredMixin, ListView):
    model = UserProfile
    template_name = "accounts/user_list.html"
    context_object_name = "profiles"


class LogoutView(View):
    def get(self, request):
        logout(request)
        return redirect("accounts:login")

    def post(self, request):
        logout(request)
        return redirect("accounts:login")
