document.addEventListener("DOMContentLoaded", () => {
  // 1. Export CSV Handler
  const exportBtn = document.getElementById("exportCsv");

  function exportTableToCsv() {
    const rows = Array.from(document.querySelectorAll(".lux-table tr"));
    if (!rows.length) return;

    const csv = rows
      .map((row) =>
        Array.from(row.querySelectorAll("th,td"))
          // Don't export the Checkbox and Actions columns
          .filter((cell, idx) => {
            const headerRow = row.closest("table").querySelector("thead tr");
            const headerCells = headerRow ? Array.from(headerRow.querySelectorAll("th")) : [];
            const isActions = headerCells[idx] && headerCells[idx].innerText.toLowerCase().includes("action");
            const isCheckbox = idx === 0; // Checkbox is always the first column
            return !isActions && !isCheckbox;
          })
          .map((cell) => {
            const text = cell.innerText.replace(/\s+/g, " ").trim();
            if (text.includes(",") || text.includes('"')) {
              return `"${text.replace(/"/g, '""')}"`;
            }
            return text;
          })
          .join(",")
      )
      .join("\n");

    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "predatory_journal_predictions.csv";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  if (exportBtn) {
    exportBtn.addEventListener("click", exportTableToCsv);
  }

  // 2. Click-to-Copy URL Handler
  const copyButtons = document.querySelectorAll(".copy-url-btn");
  copyButtons.forEach((btn) => {
    btn.addEventListener("click", async () => {
      const urlToCopy = btn.getAttribute("data-url");
      if (!urlToCopy) return;

      try {
        await navigator.clipboard.writeText(urlToCopy);
        
        // Show temporary success state
        const originalText = btn.textContent;
        btn.textContent = "Copied! ✓";
        btn.style.color = "var(--success)";
        btn.style.borderColor = "var(--success)";
        
        setTimeout(() => {
          btn.textContent = originalText;
          btn.style.color = "";
          btn.style.borderColor = "";
        }, 1500);
      } catch (err) {
        console.error("Failed to copy URL to clipboard: ", err);
      }
    });
  });

  // 3. Checkboxes & Bulk Delete Actions Enable/Disable
  const selectAllCheckbox = document.getElementById("selectAll");
  const rowCheckboxes = document.querySelectorAll(".select-row");
  const deleteSelectedBtn = document.getElementById("deleteSelectedBtn");

  const updateBulkDeleteButtonState = () => {
    if (!deleteSelectedBtn) return;
    const checkedCount = Array.from(rowCheckboxes).filter(cb => cb.checked).length;
    
    if (checkedCount > 0) {
      deleteSelectedBtn.removeAttribute("disabled");
      deleteSelectedBtn.style.cursor = "pointer";
      deleteSelectedBtn.style.opacity = "1";
    } else {
      deleteSelectedBtn.setAttribute("disabled", "true");
      deleteSelectedBtn.style.cursor = "not-allowed";
      deleteSelectedBtn.style.opacity = "0.5";
    }
  };

  if (selectAllCheckbox) {
    selectAllCheckbox.addEventListener("change", () => {
      const isChecked = selectAllCheckbox.checked;
      rowCheckboxes.forEach((cb) => {
        cb.checked = isChecked;
      });
      updateBulkDeleteButtonState();
    });
  }

  rowCheckboxes.forEach((cb) => {
    cb.addEventListener("change", () => {
      // Uncheck selectAll if one row is unchecked, check selectAll if all rows are checked
      if (selectAllCheckbox) {
        const allChecked = Array.from(rowCheckboxes).every(cb => cb.checked);
        selectAllCheckbox.checked = allChecked;
      }
      updateBulkDeleteButtonState();
    });
  });

  // Helper to get active view query param
  const getActiveView = () => {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get("view") || "mine";
  };

  // Helper Modal functions
  const openModal = (modalEl) => {
    if (!modalEl) return;
    modalEl.classList.remove("hidden");
    modalEl.offsetHeight; // force reflow
    modalEl.classList.add("active");
  };

  const closeModal = (modalEl) => {
    if (!modalEl) return;
    modalEl.classList.remove("active");
    setTimeout(() => {
      if (!modalEl.classList.contains("active")) {
        modalEl.classList.add("hidden");
      }
    }, 220);
  };

  // 4. Single Row Delete custom Modal Handler
  const deleteRowButtons = document.querySelectorAll(".delete-row-btn");
  const singleDeleteModal = document.getElementById("singleDeleteModal");
  const cancelSingleDeleteBtn = document.getElementById("cancelSingleDeleteBtn");
  const singleDeleteForm = document.getElementById("singleDeleteForm");

  deleteRowButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const predId = btn.getAttribute("data-id");
      if (!predId || !singleDeleteForm) return;

      const activeView = getActiveView();
      singleDeleteForm.setAttribute("action", `/delete-history/${predId}?view=${activeView}`);
      openModal(singleDeleteModal);
    });
  });

  if (cancelSingleDeleteBtn && singleDeleteModal) {
    cancelSingleDeleteBtn.addEventListener("click", () => closeModal(singleDeleteModal));
    singleDeleteModal.addEventListener("click", (e) => {
      if (e.target === singleDeleteModal) closeModal(singleDeleteModal);
    });
  }

  // 5. Bulk Delete Custom Modal Handler
  const bulkDeleteModal = document.getElementById("bulkDeleteModal");
  const cancelBulkDeleteBtn = document.getElementById("cancelBulkDeleteBtn");
  const bulkDeleteIdsInput = document.getElementById("bulkDeleteIdsInput");
  const bulkDeleteMsg = document.getElementById("bulkDeleteMsg");

  if (deleteSelectedBtn) {
    deleteSelectedBtn.addEventListener("click", () => {
      const checkedIds = Array.from(rowCheckboxes)
        .filter(cb => cb.checked)
        .map(cb => cb.value);

      if (!checkedIds.length || !bulkDeleteIdsInput || !bulkDeleteModal) return;

      bulkDeleteIdsInput.value = checkedIds.join(",");
      if (bulkDeleteMsg) {
        bulkDeleteMsg.textContent = `Are you sure you want to permanently delete the ${checkedIds.length} selected scan records? This action cannot be undone.`;
      }
      openModal(bulkDeleteModal);
    });
  }

  if (cancelBulkDeleteBtn && bulkDeleteModal) {
    cancelBulkDeleteBtn.addEventListener("click", () => closeModal(bulkDeleteModal));
    bulkDeleteModal.addEventListener("click", (e) => {
      if (e.target === bulkDeleteModal) closeModal(bulkDeleteModal);
    });
  }

  // 6. Clear History Modal Handler
  const clearHistoryBtn = document.getElementById("clearHistoryBtn");
  const clearHistoryModal = document.getElementById("clearHistoryModal");
  const cancelClearBtn = document.getElementById("cancelClearBtn");
  const clearScopeInput = document.getElementById("clearScopeInput");
  const clearHistoryMsg = document.getElementById("clearHistoryMsg");

  if (clearHistoryBtn && clearHistoryModal && cancelClearBtn && clearScopeInput && clearHistoryMsg) {
    clearHistoryBtn.addEventListener("click", () => {
      const scope = clearHistoryBtn.getAttribute("data-scope") || "user";
      clearScopeInput.value = scope;
      
      if (scope === "all") {
        clearHistoryMsg.textContent = "Are you sure you want to clear the system-wide evaluation history for all users? This action cannot be undone.";
      } else {
        clearHistoryMsg.textContent = "Are you sure you want to clear your entire personal evaluation history? This action cannot be undone.";
      }
      
      openModal(clearHistoryModal);
    });

    cancelClearBtn.addEventListener("click", () => closeModal(clearHistoryModal));
    clearHistoryModal.addEventListener("click", (e) => {
      if (e.target === clearHistoryModal) closeModal(clearHistoryModal);
    });
  }
});
