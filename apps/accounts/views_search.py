from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.views.generic import TemplateView

from apps.cases.models import Case
from apps.prospects.models import Prospect


class GlobalSearchView(LoginRequiredMixin, TemplateView):
    template_name = "search_results.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        q = self.request.GET.get("q", "").strip()
        ctx["query"] = q

        if not q or len(q) < 2:
            ctx["prospects"] = Prospect.objects.none()
            ctx["cases"] = Case.objects.none()
            return ctx

        # Search prospects
        ctx["prospects"] = Prospect.objects.filter(
            Q(case_number__icontains=q)
            | Q(parcel_id__icontains=q)
            | Q(property_address__icontains=q)
            | Q(defendant_name__icontains=q)
            | Q(plaintiff_name__icontains=q)
            | Q(auction_item_number__icontains=q)
        ).select_related("county", "county__state", "assigned_to")[:50]

        # Search cases
        ctx["cases"] = Case.objects.filter(
            Q(case_number__icontains=q)
            | Q(parcel_id__icontains=q)
            | Q(property_address__icontains=q)
        ).select_related("county", "county__state")[:50]

        return ctx
