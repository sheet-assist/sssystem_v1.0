from django.urls import path, register_converter

from . import views
from .converters import ProspectTypeConverter

app_name = "prospects"

register_converter(ProspectTypeConverter, "ptype")

urlpatterns = [
    # Type selection (landing page)
    path("", views.TypeSelectView.as_view(), name="type_select"),

    # Utility pages
    path("my/", views.MyProspectsView.as_view(), name="my_prospects"),
    path("calendar/", views.ProspectCaseCalendarView.as_view(), name="calendar"),

    # Detail & actions
    path("detail/<int:pk>/", views.ProspectDetailView.as_view(), name="detail"),
    path("detail/<int:pk>/assign/", views.AssignProspectView.as_view(), name="assign"),
    path("detail/<int:pk>/delete/", views.ProspectDeleteView.as_view(), name="delete"),
    path("detail/<int:pk>/notes/add/", views.ProspectNoteCreateView.as_view(), name="note_add"),
    path("detail/<int:pk>/research/", views.ResearchUpdateView.as_view(), name="research"),
    path("detail/<int:pk>/transition/", views.WorkflowTransitionView.as_view(), name="transition"),
    path("detail/<int:pk>/history/", views.ProspectHistoryView.as_view(), name="history"),

    # Digital Folder (documents)
    path("detail/<int:pk>/documents/v2/list/", views.prospect_documents_list_v2, name="documents_list_v2"),
    path("detail/<int:pk>/documents/upload/", views.prospect_documents_upload, name="documents_upload"),
    path("detail/<int:pk>/documents/delete/", views.prospect_documents_delete, name="documents_delete"),
    path("detail/<int:pk>/documents/<int:doc_pk>/download/", views.prospect_document_download, name="document_download"),
    path("detail/<int:pk>/documents/<int:doc_pk>/notes/add/", views.prospect_document_add_note, name="document_note_add"),
    path("detail/<int:pk>/documents/<int:doc_pk>/notes/<int:note_pk>/delete/", views.prospect_document_delete_note, name="document_note_delete"),
    # Dedicated Digital Folder V2 page
    path("detail/<int:pk>/documents/v2/", views.ProspectDocumentsPageV2View.as_view(), name="documents_page_v2"),

    # Navigation flow: type → state → county → list
    path("browse/<ptype:prospect_type>/", views.StateSelectView.as_view(), name="state_select"),
    path("browse/all/", views.ProspectListView.as_view(), name="list_all"),
    path("browse/<ptype:prospect_type>/all/", views.ProspectListView.as_view(), name="list_by_type"),
    path("browse/<ptype:prospect_type>/<str:state>/", views.CountySelectView.as_view(), name="county_select"),
    path("browse/<ptype:prospect_type>/<str:state>/<slug:county>/", views.ProspectListView.as_view(), name="list"),
]
