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

    # Digital Folder page (opens in new tab)
    path("<int:pk>/documents/", views.CaseDocumentsPageView.as_view(), name="documents_page"),

    # Digital Folder AJAX endpoints
    path("<int:pk>/documents/list/", views.case_documents_list_v2, name="documents_list_v2"),
    path("<int:pk>/documents/upload/", views.case_documents_upload, name="documents_upload"),
    path("<int:pk>/documents/delete/", views.case_documents_delete, name="documents_delete"),
    path("<int:pk>/documents/<int:doc_pk>/download/", views.case_document_download, name="document_download"),
    path("<int:pk>/documents/<int:doc_pk>/notes/add/", views.case_document_add_note, name="document_note_add"),
    path("<int:pk>/documents/<int:doc_pk>/notes/<int:note_pk>/delete/", views.case_document_delete_note, name="document_note_delete"),
]
