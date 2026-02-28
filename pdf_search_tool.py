"""
PDF Search Tool
---------------
Search across all PDFs in a folder (including subfolders) for any keyword.
Works with both native-text PDFs and scanned image PDFs (via OCR).

HOW TO USE:
  1. Run this script: python pdf_search_tool.py
  2. Click "Browse" to select your Google Drive folder (or any local folder)
  3. Click "Index PDFs" to scan and extract text (do this once; index is saved)
  4. Type a keyword in the search box and press Enter or click "Search"
  5. Click any result to see a larger preview of the surrounding text
"""

import os
import sys
import json
import re
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path
import time

# ── dependency check ─────────────────────────────────────────────────────────

MISSING = []

try:
    import fitz  # PyMuPDF
except ImportError:
    MISSING.append("PyMuPDF")

try:
    import pytesseract
    from PIL import Image
    import pdf2image
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

if MISSING:
    print("=" * 60)
    print("MISSING REQUIRED PACKAGES.")
    print("Please run:  pip install " + " ".join(MISSING))
    print("=" * 60)
    sys.exit(1)

# ── constants ─────────────────────────────────────────────────────────────────

INDEX_FILENAME = ".pdf_search_index.json"
CONTEXT_CHARS  = 200          # characters shown around each match
APP_TITLE      = "PDF Search Tool"
APP_WIDTH      = 900
APP_HEIGHT     = 680
ACCENT         = "#1a73e8"    # Google-blue accent colour
BG             = "#f8f9fa"
CARD_BG        = "#ffffff"

# ── PDF extraction helpers ────────────────────────────────────────────────────

def _extract_page_text_native(page) -> str:
    """Return text from a PyMuPDF page object using embedded text."""
    return page.get_text("text")


def _extract_page_text_ocr(pdf_path: str, page_number: int) -> str:
    """Render a PDF page to an image and run Tesseract OCR on it."""
    if not HAS_OCR:
        return ""
    try:
        images = pdf2image.convert_from_path(
            pdf_path,
            first_page=page_number,
            last_page=page_number,
            dpi=200,
        )
        if images:
            return pytesseract.image_to_string(images[0])
    except Exception:
        pass
    return ""


def extract_pdf_pages(pdf_path: str, use_ocr: bool = True) -> list[dict]:
    """
    Extract text from every page of a PDF.

    Returns a list of dicts:
        {"page": int (1-based), "text": str}
    """
    results = []
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        return [{"page": 1, "text": f"[Could not open file: {e}]"}]

    for i, page in enumerate(doc, start=1):
        text = _extract_page_text_native(page)
        # If the page has very little native text, try OCR
        if use_ocr and len(text.strip()) < 20:
            text = _extract_page_text_ocr(pdf_path, i)
        results.append({"page": i, "text": text})

    doc.close()
    return results


# ── indexing ──────────────────────────────────────────────────────────────────

def find_pdfs(root_folder: str) -> list[str]:
    """Recursively find every .pdf file under root_folder."""
    pdfs = []
    for dirpath, _dirs, files in os.walk(root_folder):
        for filename in files:
            if filename.lower().endswith(".pdf"):
                pdfs.append(os.path.join(dirpath, filename))
    return sorted(pdfs)


def build_index(
    root_folder: str,
    use_ocr: bool,
    progress_callback=None,
    cancel_flag=None,
) -> dict:
    """
    Build a search index for all PDFs under root_folder.

    Index format:
        {
            "root": str,
            "files": {
                "<relative_path>": [
                    {"page": int, "text": str},
                    ...
                ]
            }
        }
    """
    pdfs = find_pdfs(root_folder)
    index = {"root": root_folder, "files": {}}
    total = len(pdfs)

    for idx, pdf_path in enumerate(pdfs):
        if cancel_flag and cancel_flag():
            break

        rel_path = os.path.relpath(pdf_path, root_folder)
        if progress_callback:
            progress_callback(idx, total, rel_path)

        pages = extract_pdf_pages(pdf_path, use_ocr=use_ocr)
        index["files"][rel_path] = pages

    if progress_callback:
        progress_callback(total, total, "Done")

    return index


def save_index(index: dict, root_folder: str):
    path = os.path.join(root_folder, INDEX_FILENAME)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)


def load_index(root_folder: str) -> dict | None:
    path = os.path.join(root_folder, INDEX_FILENAME)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def index_is_stale(index: dict, root_folder: str) -> bool:
    """Return True if PDFs on disk don't match what the index recorded."""
    current_pdfs = {
        os.path.relpath(p, root_folder) for p in find_pdfs(root_folder)
    }
    indexed_pdfs = set(index.get("files", {}).keys())
    return current_pdfs != indexed_pdfs


# ── search ────────────────────────────────────────────────────────────────────

def search_index(
    index: dict,
    query: str,
    case_sensitive: bool = False,
    whole_words: bool = False,
) -> list[dict]:
    """
    Search the index for query.

    Returns a list of match dicts:
        {
            "file":    str  (relative path),
            "page":    int,
            "context": str  (surrounding text snippet),
            "count":   int  (matches on that page),
        }
    """
    flags = 0 if case_sensitive else re.IGNORECASE

    if whole_words:
        pattern = re.compile(r"\b" + re.escape(query) + r"\b", flags)
    else:
        pattern = re.compile(re.escape(query), flags)

    results = []
    for rel_path, pages in index.get("files", {}).items():
        for page_info in pages:
            text = page_info.get("text", "")
            matches = list(pattern.finditer(text))
            if not matches:
                continue

            # Build a context snippet around the first match
            m = matches[0]
            start = max(0, m.start() - CONTEXT_CHARS // 2)
            end   = min(len(text), m.end() + CONTEXT_CHARS // 2)
            snippet = text[start:end].strip()
            # Replace newlines so snippet is compact in the list
            snippet = re.sub(r"\s+", " ", snippet)

            results.append(
                {
                    "file":    rel_path,
                    "page":    page_info["page"],
                    "context": snippet,
                    "count":   len(matches),
                }
            )

    # Sort: most matches first, then alphabetically
    results.sort(key=lambda r: (-r["count"], r["file"], r["page"]))
    return results


# ── GUI ───────────────────────────────────────────────────────────────────────

class ToolTip:
    """Simple tooltip widget."""
    def __init__(self, widget, text):
        self.widget = widget
        self.text   = text
        self.tip    = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, _event=None):
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(
            tw, text=self.text, background="#fffce0",
            relief="solid", borderwidth=1, font=("Segoe UI", 9),
            wraplength=260, justify="left", padx=6, pady=4,
        ).pack()

    def hide(self, _event=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class PDFSearchApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry(f"{APP_WIDTH}x{APP_HEIGHT}")
        self.minsize(700, 500)
        self.configure(bg=BG)

        self._index: dict | None = None
        self._cancel_indexing    = False
        self._index_thread: threading.Thread | None = None

        self._build_ui()
        self._center_window()

    # ── window helpers ────────────────────────────────────────────────────────

    def _center_window(self):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x  = (sw - APP_WIDTH)  // 2
        y  = (sh - APP_HEIGHT) // 2
        self.geometry(f"{APP_WIDTH}x{APP_HEIGHT}+{x}+{y}")

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # ── header strip
        hdr = tk.Frame(self, bg=ACCENT, height=52)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(
            hdr, text="📄  PDF Search Tool", bg=ACCENT, fg="white",
            font=("Segoe UI", 16, "bold"),
        ).pack(side="left", padx=18, pady=10)

        if not HAS_OCR:
            tk.Label(
                hdr,
                text="⚠ OCR unavailable (install pytesseract + pdf2image for scanned PDFs)",
                bg=ACCENT, fg="#ffe082", font=("Segoe UI", 9),
            ).pack(side="right", padx=12)

        # ── main body
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=12)

        self._build_folder_section(body)
        self._build_index_section(body)
        ttk.Separator(body, orient="horizontal").pack(fill="x", pady=10)
        self._build_search_section(body)
        self._build_results_section(body)
        self._build_statusbar()

    def _build_folder_section(self, parent):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(0, 6))

        tk.Label(
            row, text="PDF Folder:", bg=BG,
            font=("Segoe UI", 10, "bold"), width=12, anchor="w",
        ).pack(side="left")

        self._folder_var = tk.StringVar()
        folder_entry = tk.Entry(
            row, textvariable=self._folder_var,
            font=("Segoe UI", 10), relief="solid",
            state="readonly", readonlybackground="white",
        )
        folder_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        browse_btn = tk.Button(
            row, text="Browse…", command=self._browse_folder,
            bg=ACCENT, fg="white", font=("Segoe UI", 10, "bold"),
            relief="flat", padx=14, pady=4, cursor="hand2",
            activebackground="#1558b0", activeforeground="white",
        )
        browse_btn.pack(side="left")
        ToolTip(
            browse_btn,
            "Select the top-level folder that contains your PDFs.\n"
            "If you use Google Drive for Desktop, this will be inside "
            "your 'Google Drive' folder on your computer."
        )

    def _build_index_section(self, parent):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(0, 4))

        self._ocr_var = tk.BooleanVar(value=HAS_OCR)
        ocr_cb = tk.Checkbutton(
            row, text="Use OCR for scanned PDFs",
            variable=self._ocr_var, bg=BG,
            font=("Segoe UI", 10),
            state="normal" if HAS_OCR else "disabled",
        )
        ocr_cb.pack(side="left")
        ToolTip(
            ocr_cb,
            "When enabled, pages with no machine-readable text are processed "
            "through OCR (Tesseract), which reads images of text.\n"
            "Requires: pytesseract, pdf2image, and Tesseract installed."
        )

        self._index_btn = tk.Button(
            row, text="⚙  Index PDFs", command=self._start_indexing,
            bg="#34a853", fg="white", font=("Segoe UI", 10, "bold"),
            relief="flat", padx=14, pady=4, cursor="hand2",
            activebackground="#277040", activeforeground="white",
        )
        self._index_btn.pack(side="right")
        ToolTip(
            self._index_btn,
            "Scan all PDFs in the selected folder and extract their text.\n"
            "This only needs to be done once (or when you add new PDFs).\n"
            "The index is saved in the folder for faster future use."
        )

        self._cancel_btn = tk.Button(
            row, text="✕  Cancel", command=self._cancel_indexing_fn,
            bg="#ea4335", fg="white", font=("Segoe UI", 10),
            relief="flat", padx=10, pady=4, cursor="hand2",
            state="disabled",
            activebackground="#b31412", activeforeground="white",
        )
        self._cancel_btn.pack(side="right", padx=(0, 8))

        # Progress bar + label
        prog_row = tk.Frame(parent, bg=BG)
        prog_row.pack(fill="x", pady=(2, 0))

        self._prog_label = tk.Label(
            prog_row, text="", bg=BG,
            font=("Segoe UI", 9), fg="#5f6368", anchor="w",
        )
        self._prog_label.pack(fill="x")

        self._progressbar = ttk.Progressbar(
            prog_row, mode="determinate", length=200,
        )
        self._progressbar.pack(fill="x", pady=(2, 0))
        self._progressbar.pack_forget()  # hidden until indexing starts

    def _build_search_section(self, parent):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(0, 8))

        tk.Label(
            row, text="Search:", bg=BG,
            font=("Segoe UI", 10, "bold"), width=12, anchor="w",
        ).pack(side="left")

        self._query_var = tk.StringVar()
        self._search_entry = tk.Entry(
            row, textvariable=self._query_var,
            font=("Segoe UI", 12), relief="solid",
        )
        self._search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._search_entry.bind("<Return>", lambda _e: self._do_search())

        search_btn = tk.Button(
            row, text="🔍  Search", command=self._do_search,
            bg=ACCENT, fg="white", font=("Segoe UI", 10, "bold"),
            relief="flat", padx=14, pady=4, cursor="hand2",
            activebackground="#1558b0", activeforeground="white",
        )
        search_btn.pack(side="left")

        # Options row
        opts = tk.Frame(parent, bg=BG)
        opts.pack(fill="x", pady=(0, 4))
        tk.Label(opts, text="", bg=BG, width=12).pack(side="left")  # spacer

        self._case_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            opts, text="Case sensitive", variable=self._case_var,
            bg=BG, font=("Segoe UI", 9),
        ).pack(side="left", padx=(0, 16))

        self._words_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            opts, text="Whole words only", variable=self._words_var,
            bg=BG, font=("Segoe UI", 9),
        ).pack(side="left")

    def _build_results_section(self, parent):
        # Count label
        self._result_count_var = tk.StringVar(value="No search yet.")
        tk.Label(
            parent, textvariable=self._result_count_var,
            bg=BG, font=("Segoe UI", 9, "bold"), fg="#5f6368", anchor="w",
        ).pack(fill="x")

        # Paned window: list on top, detail pane below
        paned = tk.PanedWindow(parent, orient="vertical", bg=BG, sashwidth=6)
        paned.pack(fill="both", expand=True, pady=(4, 0))

        # Results list (Treeview)
        list_frame = tk.Frame(paned, bg=BG)
        paned.add(list_frame, minsize=120)

        cols = ("file", "page", "matches", "context")
        self._tree = ttk.Treeview(
            list_frame, columns=cols, show="headings",
            selectmode="browse",
        )
        self._tree.heading("file",    text="File")
        self._tree.heading("page",    text="Page")
        self._tree.heading("matches", text="Hits")
        self._tree.heading("context", text="Context preview")

        self._tree.column("file",    width=220, stretch=True)
        self._tree.column("page",    width=55,  stretch=False)
        self._tree.column("matches", width=45,  stretch=False)
        self._tree.column("context", width=500, stretch=True)

        vsb = ttk.Scrollbar(list_frame, orient="vertical",   command=self._tree.yview)
        hsb = ttk.Scrollbar(list_frame, orient="horizontal",  command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        self._tree.bind("<<TreeviewSelect>>", self._on_result_select)

        # Detail / context pane
        detail_frame = tk.Frame(paned, bg=CARD_BG, relief="solid", bd=1)
        paned.add(detail_frame, minsize=80)

        tk.Label(
            detail_frame, text="Context Preview",
            bg=CARD_BG, font=("Segoe UI", 9, "bold"), fg="#5f6368", anchor="w",
        ).pack(fill="x", padx=8, pady=(4, 0))

        self._detail_text = scrolledtext.ScrolledText(
            detail_frame, wrap="word", font=("Segoe UI", 10),
            bg=CARD_BG, relief="flat", state="disabled",
            height=6,
        )
        self._detail_text.pack(fill="both", expand=True, padx=8, pady=4)

        # Tag for highlighting matches
        self._detail_text.tag_configure(
            "highlight", background="#fbbc04", foreground="black",
        )

    def _build_statusbar(self):
        bar = tk.Frame(self, bg="#e8eaed", height=26)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        self._status_var = tk.StringVar(value="Ready.  Select a folder to begin.")
        tk.Label(
            bar, textvariable=self._status_var,
            bg="#e8eaed", font=("Segoe UI", 9), fg="#5f6368", anchor="w",
        ).pack(side="left", padx=10)

    # ── folder browsing ───────────────────────────────────────────────────────

    def _browse_folder(self):
        folder = filedialog.askdirectory(title="Select your PDF folder")
        if not folder:
            return
        self._folder_var.set(folder)
        self._index = None
        self._tree.delete(*self._tree.get_children())
        self._result_count_var.set("No search yet.")
        self._set_status(f"Folder selected: {folder}")

        # Try to load existing index
        existing = load_index(folder)
        if existing:
            stale = index_is_stale(existing, folder)
            file_count = len(existing.get("files", {}))
            if stale:
                self._set_status(
                    f"Found existing index ({file_count} files) but PDFs have changed. "
                    "Click 'Index PDFs' to rebuild."
                )
                self._prog_label.config(
                    text="⚠ Index is outdated — click 'Index PDFs' to refresh."
                )
            else:
                self._index = existing
                self._set_status(
                    f"Loaded saved index: {file_count} PDFs ready to search."
                )
                self._prog_label.config(
                    text=f"✔ Index loaded ({file_count} PDFs). Ready to search."
                )

    # ── indexing ──────────────────────────────────────────────────────────────

    def _start_indexing(self):
        folder = self._folder_var.get().strip()
        if not folder:
            messagebox.showwarning(APP_TITLE, "Please select a folder first.")
            return
        if not os.path.isdir(folder):
            messagebox.showerror(APP_TITLE, "The selected path is not a valid folder.")
            return

        pdf_count = len(find_pdfs(folder))
        if pdf_count == 0:
            messagebox.showinfo(APP_TITLE, "No PDF files found in that folder.")
            return

        self._cancel_indexing = False
        self._index_btn.config(state="disabled")
        self._cancel_btn.config(state="normal")
        self._progressbar.pack(fill="x", pady=(2, 0))
        self._progressbar["value"] = 0

        use_ocr = self._ocr_var.get()

        def progress_cb(done, total, current_file):
            pct = int(done / max(total, 1) * 100)
            self._progressbar["value"] = pct
            short = Path(current_file).name if current_file != "Done" else "Done"
            self._prog_label.config(
                text=f"Processing {done}/{total}: {short}"
            )
            self._set_status(f"Indexing… {done}/{total} files processed.")
            self.update_idletasks()

        def run():
            try:
                index = build_index(
                    folder,
                    use_ocr=use_ocr,
                    progress_callback=progress_cb,
                    cancel_flag=lambda: self._cancel_indexing,
                )
                if not self._cancel_indexing:
                    save_index(index, folder)
                    self._index = index
                    file_count = len(index.get("files", {}))
                    self.after(0, lambda: self._on_index_complete(file_count, cancelled=False))
                else:
                    self.after(0, lambda: self._on_index_complete(0, cancelled=True))
            except Exception as e:
                self.after(0, lambda: self._on_index_error(str(e)))

        self._index_thread = threading.Thread(target=run, daemon=True)
        self._index_thread.start()

    def _cancel_indexing_fn(self):
        self._cancel_indexing = True
        self._cancel_btn.config(state="disabled")
        self._set_status("Cancelling…")

    def _on_index_complete(self, file_count: int, cancelled: bool):
        self._index_btn.config(state="normal")
        self._cancel_btn.config(state="disabled")
        if cancelled:
            self._prog_label.config(text="Indexing cancelled.")
            self._set_status("Indexing cancelled.")
        else:
            self._prog_label.config(
                text=f"✔ Indexed {file_count} PDFs successfully. Ready to search."
            )
            self._set_status(f"Index built: {file_count} PDFs ready to search.")
            self._progressbar["value"] = 100

    def _on_index_error(self, error_msg: str):
        self._index_btn.config(state="normal")
        self._cancel_btn.config(state="disabled")
        self._prog_label.config(text="✘ Error during indexing.")
        self._set_status(f"Error: {error_msg}")
        messagebox.showerror(APP_TITLE, f"An error occurred during indexing:\n\n{error_msg}")

    # ── search ────────────────────────────────────────────────────────────────

    def _do_search(self):
        if self._index is None:
            messagebox.showwarning(
                APP_TITLE,
                "No index loaded.\n\nPlease select a folder and click 'Index PDFs' first."
            )
            return

        query = self._query_var.get().strip()
        if not query:
            messagebox.showwarning(APP_TITLE, "Please enter a search term.")
            return

        self._set_status(f"Searching for: {query!r}…")
        self._tree.delete(*self._tree.get_children())
        self._clear_detail()

        results = search_index(
            self._index, query,
            case_sensitive=self._case_var.get(),
            whole_words=self._words_var.get(),
        )

        if not results:
            self._result_count_var.set(f'No matches found for "{query}".')
            self._set_status("Search complete — no matches.")
            return

        # Populate the tree
        for r in results:
            self._tree.insert(
                "", "end",
                values=(r["file"], r["page"], r["count"], r["context"]),
                tags=("result",),
            )
            self._tree.tag_configure("result", background=CARD_BG)

        self._result_count_var.set(
            f'{len(results)} match{"es" if len(results) != 1 else ""} '
            f'for "{query}" — click a row to see full context.'
        )
        self._set_status(
            f"Found {len(results)} matching page(s). Click a row for details."
        )
        # Store query for highlighting
        self._last_query = query

    # ── result selection ──────────────────────────────────────────────────────

    def _on_result_select(self, _event=None):
        sel = self._tree.selection()
        if not sel:
            return
        values = self._tree.item(sel[0], "values")
        if not values:
            return

        rel_path, page_str, _count, _ctx = values
        page = int(page_str)

        # Find full text for this page in the index
        pages = self._index.get("files", {}).get(rel_path, [])
        page_text = next(
            (p["text"] for p in pages if p["page"] == page), ""
        )

        query = getattr(self, "_last_query", "")

        self._detail_text.config(state="normal")
        self._detail_text.delete("1.0", "end")

        header = f"File:  {rel_path}\nPage:  {page}\n{'─'*60}\n"
        self._detail_text.insert("end", header)

        # Insert page text and highlight all matches
        text_start = self._detail_text.index("end")
        self._detail_text.insert("end", page_text)

        if query:
            flags = 0 if self._case_var.get() else re.IGNORECASE
            pattern = re.compile(re.escape(query), flags)
            for m in pattern.finditer(page_text):
                start = f"{text_start} + {m.start()} chars"
                end   = f"{text_start} + {m.end()} chars"
                self._detail_text.tag_add("highlight", start, end)

        self._detail_text.config(state="disabled")
        self._detail_text.see("1.0")

    def _clear_detail(self):
        self._detail_text.config(state="normal")
        self._detail_text.delete("1.0", "end")
        self._detail_text.config(state="disabled")

    # ── status bar ────────────────────────────────────────────────────────────

    def _set_status(self, text: str):
        self._status_var.set(text)
        self.update_idletasks()


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    # Style tweaks
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure("Treeview",
                    rowheight=28,
                    font=("Segoe UI", 10))
    style.configure("Treeview.Heading",
                    font=("Segoe UI", 10, "bold"),
                    background="#e8eaed")
    style.map("Treeview",
              background=[("selected", "#d2e3fc")],
              foreground=[("selected", "black")])
    style.configure("TProgressbar",
                    troughcolor="#e8eaed",
                    background=ACCENT)

    app = PDFSearchApp()
    app.mainloop()


if __name__ == "__main__":
    main()
