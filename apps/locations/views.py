from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.contrib import messages
from django.views.generic import UpdateView, ListView, CreateView, DeleteView
from django.db.models import Q

from apps.locations.models import County
from .forms import CountyConfigForm, CountyForm
from apps.accounts.mixins import AdminRequiredMixin


class CountyListView(AdminRequiredMixin, ListView):
    """List view for all counties"""
    model = County
    template_name = 'locations/county_list.html'
    context_object_name = 'counties'
    paginate_by = 50

    def get_queryset(self):
        queryset = County.objects.select_related('state')
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | 
                Q(state__name__icontains=search) |
                Q(state__abbreviation__icontains=search)
            )
        return queryset.order_by('state', 'name')


class CountyCreateView(AdminRequiredMixin, CreateView):
    """Create view for new counties"""
    model = County
    form_class = CountyForm
    template_name = 'locations/county_form.html'

    def get_success_url(self):
        messages.success(self.request, f'County "{self.object.name}" created successfully.')
        return reverse('locations:county_list')


class CountyUpdateView(AdminRequiredMixin, UpdateView):
    """Update view for counties"""
    model = County
    form_class = CountyForm
    template_name = 'locations/county_form.html'
    pk_url_kwarg = 'pk'

    def get_success_url(self):
        messages.success(self.request, f'County "{self.object.name}" updated successfully.')
        return reverse('locations:county_detail', kwargs={'pk': self.object.pk})


class CountyDeleteView(AdminRequiredMixin, DeleteView):
    """Delete view for counties"""
    model = County
    template_name = 'locations/county_confirm_delete.html'
    pk_url_kwarg = 'pk'

    def get_success_url(self):
        messages.success(self.request, f'County deleted successfully.')
        return reverse('locations:county_list')


class CountyConfigView(AdminRequiredMixin, UpdateView):
    """Configuration view for county settings"""
    model = County
    form_class = CountyConfigForm
    template_name = 'locations/county_config.html'
    pk_url_kwarg = 'pk'

    def get_success_url(self):
        messages.success(self.request, 'County configuration saved.')
        return reverse('locations:county_config', kwargs={'pk': self.object.pk})

    def get_object(self, queryset=None):
        pk = self.kwargs.get(self.pk_url_kwarg)
        return get_object_or_404(County, pk=pk)

