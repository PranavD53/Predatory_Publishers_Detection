const exportBtn = document.getElementById("exportCsv");

function exportTableToCsv() {
  const rows = Array.from(document.querySelectorAll(".lux-table tr"));
  if (!rows.length) return;

  const csv = rows
    .map((row) =>
      Array.from(row.querySelectorAll("th,td"))
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

