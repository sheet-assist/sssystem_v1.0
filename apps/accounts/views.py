from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import TemplateView, ListView, UpdateView, CreateView

from .mixins import AdminRequiredMixin
from .models import UserProfile
from .forms import UserProfileForm, UserCreateForm

User = get_user_model()


class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/profile.html"


class UserListView(AdminRequiredMixin, ListView):
    model = UserProfile
    template_name = "accounts/user_list.html"
    context_object_name = "profiles"
    paginate_by = 25

    def get_queryset(self):
        return UserProfile.objects.select_related('user').order_by('user__first_name', 'user__last_name')
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # Organize profiles by role
        profiles = self.get_queryset()
        roles_dict = {}
        
        for profile in profiles:
            role = profile.get_role_display()
            if role not in roles_dict:
                roles_dict[role] = []
            roles_dict[role].append(profile)
        
        # Order roles for display
        role_order = ['Admin', 'Prospects and Cases', 'Prospects Only', 'Cases Only']
        ordered_roles = {}
        for role in role_order:
            if role in roles_dict:
                ordered_roles[role] = roles_dict[role]
        
        # Add any remaining roles not in the predefined order
        for role in roles_dict:
            if role not in ordered_roles:
                ordered_roles[role] = roles_dict[role]
        
        ctx['profiles_by_role'] = ordered_roles
        ctx['role_choices'] = UserProfile.ROLE_CHOICES
        
        return ctx


class UserUpdateView(AdminRequiredMixin, UpdateView):
    model = UserProfile
    form_class = UserProfileForm
    template_name = "accounts/user_form.html"
    success_url = reverse_lazy("accounts:user_list")

    def form_valid(self, form):
        messages.success(self.request, f"User {self.object.user.username} updated successfully.")
        return super().form_valid(form)


class UserCreateView(AdminRequiredMixin, CreateView):
    model = User
    form_class = UserCreateForm
    template_name = "accounts/user_create.html"
    success_url = reverse_lazy("accounts:user_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"User {self.object.username} created successfully.")
        return response


class LogoutView(View):
    def get(self, request):
        logout(request)
        return redirect("accounts:login")

    def post(self, request):
        logout(request)
        return redirect("accounts:login")
