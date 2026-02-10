from django.urls import path

from . import views

app_name = "prospects"

urlpatterns = [
    # Type selection (landing page)
    path("", views.TypeSelectView.as_view(), name="type_select"),

    # My assigned prospects (must be before <str:type> catch-all)
    path("my/", views.MyProspectsView.as_view(), name="my_prospects"),

    # Detail & actions (must be before <str:type> catch-all)
    path("detail/<int:pk>/", views.ProspectDetailView.as_view(), name="detail"),
    path("detail/<int:pk>/assign/", views.AssignProspectView.as_view(), name="assign"),
    path("detail/<int:pk>/notes/add/", views.ProspectNoteCreateView.as_view(), name="note_add"),
    path("detail/<int:pk>/research/", views.ResearchUpdateView.as_view(), name="research"),
    path("detail/<int:pk>/transition/", views.WorkflowTransitionView.as_view(), name="transition"),
    path("detail/<int:pk>/history/", views.ProspectHistoryView.as_view(), name="history"),

    # Navigation flow: type → state → county → list
    path("<str:type>/", views.StateSelectView.as_view(), name="state_select"),
    path("<str:type>/<str:state>/", views.CountySelectView.as_view(), name="county_select"),
    path("<str:type>/<str:state>/<slug:county>/", views.ProspectListView.as_view(), name="list"),
]
