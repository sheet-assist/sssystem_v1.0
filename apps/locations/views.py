from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.contrib import messages
from django.views.generic import UpdateView

from apps.locations.models import County
from .forms import CountyConfigForm
from apps.accounts.mixins import AdminRequiredMixin


class CountyConfigView(AdminRequiredMixin, UpdateView):
    model = County
    form_class = CountyConfigForm
    template_name = 'locations/county_config.html'
    pk_url_kwarg = 'pk'

    def get_success_url(self):
        messages.success(self.request, 'County configuration saved.')
        return reverse('county_config', kwargs={'pk': self.object.pk})

    def get_object(self, queryset=None):
        pk = self.kwargs.get(self.pk_url_kwarg)
        return get_object_or_404(County, pk=pk)
from django.shortcuts import render

# Create your views here.
