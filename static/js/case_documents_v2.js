(function () {
  function getCookie(name) {
    const v = document.cookie.match("(^|;)\\s*" + name + "\\s*=\\s*([^;]+)");
    return v ? v.pop() : "";
  }

  function modalInstance(el) {
    if (!el || !window.bootstrap) return null;
    return bootstrap.Modal.getInstance(el) || new bootstrap.Modal(el);
  }

  function cleanupModalBackdropFallback() {
    document.querySelectorAll(".modal-backdrop").forEach((b) => b.remove());
    document.body.classList.remove("modal-open");
  }

  async function hideModalAndWait(el) {
    const inst = modalInstance(el);
    if (!inst || !el) return;
    await new Promise((resolve) => {
      const onHidden = () => {
        el.removeEventListener("hidden.bs.modal", onHidden);
        resolve();
      };
      el.addEventListener("hidden.bs.modal", onHidden);
      inst.hide();
      setTimeout(() => {
        el.removeEventListener("hidden.bs.modal", onHidden);
        resolve();
      }, 1000);
    });
    cleanupModalBackdropFallback();
  }

  async function closeOpenDocumentModals(rootEl) {
    const modalIds = ["#df2ViewNotesModal", "#df2AddNoteModal", "#df2UploaderModal"];
    for (const id of modalIds) {
      const modalEl = rootEl.querySelector(id);
      if (modalEl && modalEl.classList.contains("show")) {
        await hideModalAndWait(modalEl);
      }
    }
    cleanupModalBackdropFallback();
  }

  function init(rootEl) {
    const casePk = rootEl.dataset.casePk;
    if (!casePk) return;

    const endpoints = {
      list: `/cases/${casePk}/documents/list/`,
      upload: `/cases/${casePk}/documents/upload/`,
      bulkDelete: `/cases/${casePk}/documents/delete/`,
      addNote: (docId) => `/cases/${casePk}/documents/${docId}/notes/add/`,
      deleteNote: (docId, noteId) =>
        `/cases/${casePk}/documents/${docId}/notes/${noteId}/delete/`,
    };

    async function loadList() {
      const resp = await fetch(endpoints.list, { credentials: "same-origin" });
      if (!resp.ok) throw new Error("Failed to load documents");
      rootEl.innerHTML = await resp.text();
      bindHandlers();
    }

    async function uploadFiles(files) {
      if (!files || !files.length) return;
      const fd = new FormData();
      files.forEach((f) => fd.append("files", f, f.name));
      const resp = await fetch(endpoints.upload, {
        method: "POST",
        headers: { "X-CSRFToken": getCookie("csrftoken") },
        credentials: "same-origin",
        body: fd,
      });
      if (!resp.ok) {
        const json = await resp.json().catch(() => ({}));
        throw new Error(json.error || "Upload failed");
      }
    }

    async function deleteDocuments(ids) {
      const resp = await fetch(endpoints.bulkDelete, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken"),
        },
        credentials: "same-origin",
        body: JSON.stringify({ ids }),
      });
      if (!resp.ok) throw new Error("Delete failed");
    }

    async function addNote(docId, content) {
      const resp = await fetch(endpoints.addNote(docId), {
        method: "POST",
        headers: { "X-CSRFToken": getCookie("csrftoken") },
        credentials: "same-origin",
        body: new URLSearchParams({ content }),
      });
      if (!resp.ok) {
        const json = await resp.json().catch(() => ({}));
        throw new Error(json.error || "Failed to add note");
      }
    }

    async function deleteNote(docId, noteId) {
      const resp = await fetch(endpoints.deleteNote(docId, noteId), {
        method: "POST",
        headers: { "X-CSRFToken": getCookie("csrftoken") },
        credentials: "same-origin",
      });
      if (!resp.ok) throw new Error("Failed to delete note");
    }

    function bindHandlers() {
      const selectAll = rootEl.querySelector("#df2-select-all");
      const deleteSelectedBtn = rootEl.querySelector("#deleteSelectedDocsBtnV2");
      const openUploaderBtn = rootEl.querySelector("#df2-open-uploader-modal");
      const uploaderModalEl = rootEl.querySelector("#df2UploaderModal");
      const uploaderZone = rootEl.querySelector("#df2-modal-uploader");
      const uploaderInput = rootEl.querySelector("#df2-modal-file-input");
      const viewNotesModalEl = rootEl.querySelector("#df2ViewNotesModal");
      const viewNotesBodyEl = rootEl.querySelector("#df2-view-notes-body");
      const addNoteModalEl = rootEl.querySelector("#df2AddNoteModal");
      const addNoteTextarea = rootEl.querySelector("#df2-note-textarea");

      function selectedDocIds() {
        return Array.from(
          rootEl.querySelectorAll(".df2-select-doc:checked")
        ).map((el) => el.dataset.id);
      }

      function refreshSelectionState() {
        const selected = selectedDocIds();
        if (deleteSelectedBtn) deleteSelectedBtn.disabled = selected.length === 0;
        if (selectAll) {
          const total = rootEl.querySelectorAll(".df2-select-doc").length;
          selectAll.checked = total > 0 && selected.length === total;
        }
      }

      selectAll?.addEventListener("change", (e) => {
        rootEl.querySelectorAll(".df2-select-doc").forEach((cb) => {
          cb.checked = e.target.checked;
        });
        refreshSelectionState();
      });

      openUploaderBtn?.addEventListener("click", () =>
        modalInstance(uploaderModalEl)?.show()
      );

      uploaderZone?.addEventListener("dragover", (e) => {
        e.preventDefault();
        uploaderZone.classList.add("border-primary");
      });
      uploaderZone?.addEventListener("dragleave", () =>
        uploaderZone.classList.remove("border-primary")
      );
      uploaderZone?.addEventListener("drop", async (e) => {
        e.preventDefault();
        uploaderZone.classList.remove("border-primary");
        const files = Array.from(e.dataTransfer.files || []);
        if (!files.length) return;
        try {
          await uploadFiles(files);
          await hideModalAndWait(uploaderModalEl);
          await loadList();
        } catch (err) {
          alert(err.message);
        }
      });

      rootEl
        .querySelector("#df2-modal-drop-instructions")
        ?.addEventListener("click", (e) => {
          if (e.target.closest("label") || e.target.closest("input")) return;
          uploaderInput?.click();
        });

      uploaderInput?.addEventListener("change", async (e) => {
        const files = Array.from(e.target.files || []);
        if (!files.length) return;
        try {
          await uploadFiles(files);
          uploaderInput.value = "";
          await hideModalAndWait(uploaderModalEl);
          await loadList();
        } catch (err) {
          alert(err.message);
        }
      });

      // Re-register delegated change listener
      if (rootEl._df2OnRootChange) {
        rootEl.removeEventListener("change", rootEl._df2OnRootChange);
      }
      rootEl._df2OnRootChange = (e) => {
        if (e.target.matches(".df2-select-doc")) refreshSelectionState();
      };
      rootEl.addEventListener("change", rootEl._df2OnRootChange);

      // Re-register delegated click listener
      if (rootEl._df2OnRootClick) {
        rootEl.removeEventListener("click", rootEl._df2OnRootClick);
      }
      rootEl._df2OnRootClick = async (e) => {
        if (e.target.closest(".df2-delete-single")) {
          const id = e.target.closest(".df2-delete-single").dataset.id;
          if (!confirm("Delete this file?")) return;
          try {
            await deleteDocuments([id]);
            await loadList();
          } catch (err) {
            alert(err.message);
          }
          return;
        }

        if (e.target.closest("#deleteSelectedDocsBtnV2")) {
          const ids = selectedDocIds();
          if (!ids.length) return;
          if (!confirm(`Delete ${ids.length} selected file(s)?`)) return;
          try {
            await deleteDocuments(ids);
            await loadList();
          } catch (err) {
            alert(err.message);
          }
          return;
        }

        if (e.target.closest(".df2-view-notes")) {
          const docId = e.target.closest(".df2-view-notes").dataset.id;
          const tpl = rootEl.querySelector(`#df2-notes-template-${docId}`);
          if (viewNotesBodyEl)
            viewNotesBodyEl.innerHTML = tpl
              ? tpl.innerHTML
              : '<div class="text-muted small">No notes found.</div>';
          if (viewNotesModalEl) viewNotesModalEl.dataset.docId = docId;
          modalInstance(viewNotesModalEl)?.show();
          return;
        }

        if (e.target.closest(".df2-open-add-note")) {
          const docId = e.target.closest(".df2-open-add-note").dataset.id;
          if (!docId || !addNoteModalEl) return;
          addNoteModalEl.dataset.docId = docId;
          if (addNoteTextarea) addNoteTextarea.value = "";
          modalInstance(addNoteModalEl)?.show();
          return;
        }

        if (e.target.closest("#df2-open-add-note")) {
          const docId = viewNotesModalEl?.dataset.docId;
          if (!docId || !addNoteModalEl) return;
          addNoteModalEl.dataset.docId = docId;
          if (addNoteTextarea) addNoteTextarea.value = "";
          await hideModalAndWait(viewNotesModalEl);
          modalInstance(addNoteModalEl)?.show();
          return;
        }

        if (e.target.closest("#df2-save-note")) {
          const docId = addNoteModalEl?.dataset.docId;
          const content = (addNoteTextarea?.value || "").trim();
          if (!content) {
            alert("Enter note content");
            return;
          }
          try {
            await addNote(docId, content);
            await hideModalAndWait(addNoteModalEl);
            await loadList();
          } catch (err) {
            alert(err.message);
          }
          return;
        }

        if (e.target.closest(".df2-delete-note")) {
          const btn = e.target.closest(".df2-delete-note");
          const noteId = btn.dataset.noteId;
          const docId = btn.dataset.docId;
          if (!confirm("Delete this note?")) return;
          try {
            await deleteNote(docId, noteId);
            await closeOpenDocumentModals(rootEl);
            await loadList();
          } catch (err) {
            alert(err.message);
          }
        }
      };
      rootEl.addEventListener("click", rootEl._df2OnRootClick);

      refreshSelectionState();
    }

    loadList().catch((err) => {
      rootEl.innerHTML = `<div class="text-danger p-3">Failed to load documents: ${err.message}</div>`;
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    const rootEl = document.getElementById("caseDocumentsRootV2");
    if (rootEl) init(rootEl);
  });
})();
