from django.urls import path

from . import views

app_name = "prospects"

urlpatterns = [
    # Navigation flow: type → state → county → list
    path("", views.TypeSelectView.as_view(), name="type_select"),
    path("<str:type>/", views.StateSelectView.as_view(), name="state_select"),
    path("<str:type>/<str:state>/", views.CountySelectView.as_view(), name="county_select"),
    path("<str:type>/<str:state>/<slug:county>/", views.ProspectListView.as_view(), name="list"),

    # My assigned prospects
    path("my/", views.MyProspectsView.as_view(), name="my_prospects"),

    # Detail & actions
    path("<int:pk>/", views.ProspectDetailView.as_view(), name="detail"),
    path("<int:pk>/assign/", views.AssignProspectView.as_view(), name="assign"),
    path("<int:pk>/notes/add/", views.ProspectNoteCreateView.as_view(), name="note_add"),
    path("<int:pk>/research/", views.ResearchUpdateView.as_view(), name="research"),
    path("<int:pk>/transition/", views.WorkflowTransitionView.as_view(), name="transition"),
    path("<int:pk>/history/", views.ProspectHistoryView.as_view(), name="history"),
]
