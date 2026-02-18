from django.urls import path

from . import views

app_name = "cases"

urlpatterns = [
    path("", views.CaseListView.as_view(), name="list"),
    path("<int:pk>/", views.CaseDetailView.as_view(), name="detail"),
    path("<int:pk>/status/", views.CaseStatusUpdateView.as_view(), name="status_update"),
    path("<int:pk>/notes/add/", views.CaseNoteCreateView.as_view(), name="note_add"),
    path("<int:pk>/followups/add/", views.CaseFollowUpCreateView.as_view(), name="followup_add"),
    path("<int:pk>/followups/<int:followup_pk>/complete/", views.CaseFollowUpCompleteView.as_view(), name="followup_complete"),
    path("<int:pk>/history/", views.CaseHistoryView.as_view(), name="history"),
    path("<int:pk>/autodialer/", views.CaseAutodialerView.as_view(), name="autodialer"),
    path("<int:pk>/email/", views.CaseEmailView.as_view(), name="email"),
    path("convert/<int:pk>/", views.ConvertProspectToCaseView.as_view(), name="convert"),
]
