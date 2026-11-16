"""Simple local chat interface for importing sources and searching Narrow."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

from narrow.ingest import ingest_source
from narrow.rag import KnowledgeBase
from narrow.assistant import LocalAssistant


class NarrowGUI:
    """Chat-first desktop UI; all retrieval remains local to the machine."""

    BG = "#111111"
    PANEL = "#181818"
    PANEL_2 = "#202020"
    TEXT = "#f2f2f2"
    MUTED = "#9a9a9a"
    ACCENT = "#8b6cff"

    def __init__(self, window: tk.Tk) -> None:
        self.window = window
        self.window.title("Narrow")
        self.window.geometry("1100x720")
        self.window.minsize(780, 560)
        self.root_path = Path("kb")
        self.model_path = Path("models/bge-small-en-v1.5")
        self.kb: KnowledgeBase | None = None
        self.assistant = LocalAssistant()
        self.sources: list[str] = []
        self._thinking_start: str | None = None
        self._build()

    def _build(self) -> None:
        self.window.configure(bg=self.BG)
        shell = tk.Frame(self.window, bg=self.BG)
        shell.pack(fill="both", expand=True)
        self._build_sidebar(shell)
        self._build_chat(shell)

    def _build_sidebar(self, shell: tk.Frame) -> None:
        sidebar = tk.Frame(shell, bg=self.PANEL, width=235)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        tk.Label(sidebar, text="◈  NARROW", bg=self.PANEL, fg=self.TEXT, font=("Segoe UI", 15, "bold")).pack(
            anchor="w", padx=18, pady=(22, 28)
        )
        self._side_button(sidebar, "+  New chat", self.new_chat)
        self._side_button(sidebar, "⌕  Search knowledge", self.focus_composer)
        tk.Label(sidebar, text="SOURCES", bg=self.PANEL, fg=self.MUTED, font=("Segoe UI", 9, "bold")).pack(
            anchor="w", padx=18, pady=(28, 8)
        )
        self.source_list = tk.Listbox(
            sidebar, bg=self.PANEL, fg=self.MUTED, selectbackground="#2c2c2c", selectforeground=self.TEXT,
            borderwidth=0, highlightthickness=0, font=("Segoe UI", 9),
        )
        self.source_list.pack(fill="both", expand=True, padx=12)
        tk.Label(sidebar, text="Local-only evidence workspace", bg=self.PANEL, fg=self.MUTED, font=("Segoe UI", 8)).pack(
            anchor="w", padx=18, pady=18
        )

    def _side_button(self, parent: tk.Frame, label: str, command: Callable[[], None]) -> None:
        tk.Button(
            parent, text=label, command=command, anchor="w", bg=self.PANEL, fg=self.TEXT,
            activebackground="#2c2c2c", activeforeground=self.TEXT, relief="flat", borderwidth=0,
            font=("Segoe UI", 10), padx=18, pady=9,
        ).pack(fill="x", padx=6, pady=1)

    def _build_chat(self, shell: tk.Frame) -> None:
        main = tk.Frame(shell, bg=self.BG)
        main.pack(side="left", fill="both", expand=True)
        header = tk.Frame(main, bg=self.BG)
        header.pack(fill="x", padx=28, pady=(18, 0))
        tk.Label(header, text="Narrow", bg=self.BG, fg=self.TEXT, font=("Segoe UI", 13, "bold")).pack(side="left")
        tk.Label(header, text="  Local evidence assistant", bg=self.BG, fg=self.MUTED, font=("Segoe UI", 10)).pack(side="left")

        conversation_frame = tk.Frame(main, bg=self.BG)
        conversation_frame.pack(fill="both", expand=True, padx=28, pady=(8, 0))
        self.conversation = tk.Text(
            conversation_frame, wrap="word", state="disabled", bg=self.BG, fg=self.TEXT,
            insertbackground=self.TEXT, borderwidth=0, highlightthickness=0, font=("Segoe UI", 11), padx=14, pady=12,
        )
        self.conversation.pack(side="left", fill="both", expand=True)
        scrollbar = tk.Scrollbar(
            conversation_frame, command=self.conversation.yview, bg=self.PANEL,
            troughcolor=self.BG, activebackground="#444444", highlightthickness=0,
        )
        scrollbar.pack(side="right", fill="y")
        self.conversation.configure(yscrollcommand=scrollbar.set)
        self.conversation.tag_configure("welcome", foreground=self.TEXT, font=("Segoe UI", 22, "bold"), spacing3=12)
        self.conversation.tag_configure("user", foreground="#c9bcff", font=("Segoe UI", 11, "bold"), spacing1=12)
        self.conversation.tag_configure("assistant", foreground=self.TEXT, font=("Segoe UI", 11), spacing1=8)
        self.conversation.tag_configure("muted", foreground="#9a9a9a", font=("Segoe UI", 9), spacing1=6)
        self._append("Ready to explore your files?", "welcome")
        self._append("Add documents with +, then ask a question below. Narrow searches your local knowledge base.", "muted")

        composer = tk.Frame(main, bg=self.BG)
        composer.pack(fill="x", padx=52, pady=(8, 24))
        box = tk.Frame(composer, bg=self.PANEL_2, highlightbackground="#333333", highlightthickness=1)
        box.pack(fill="x")
        self.message = tk.Text(box, height=3, wrap="word", bg=self.PANEL_2, fg=self.TEXT, insertbackground=self.TEXT,
                               borderwidth=0, highlightthickness=0, font=("Segoe UI", 11), padx=14, pady=10)
        self.message.pack(side="left", fill="both", expand=True)
        self.message.bind("<Control-Return>", lambda _event: self.send())
        controls = tk.Frame(box, bg=self.PANEL_2)
        controls.pack(side="right", fill="y", padx=8, pady=8)
        tk.Button(controls, text="＋", command=self.choose_files, bg=self.PANEL_2, fg=self.TEXT, activebackground="#333333",
                  activeforeground=self.TEXT, relief="flat", borderwidth=0, font=("Segoe UI", 14)).pack(side="left")
        tk.Button(controls, text="Send  ↑", command=self.send, bg=self.ACCENT, fg="white", activebackground="#7358d8",
                  activeforeground="white", relief="flat", borderwidth=0, padx=12, pady=8, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(6, 0))
        tk.Label(composer, text="＋ adds files  •  Ctrl+Enter sends  •  paste a public URL as a message", bg=self.BG, fg=self.MUTED,
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(6, 0))

    def _append(self, text: str, tag: str = "assistant") -> str:
        self.conversation.configure(state="normal")
        start = self.conversation.index("end-1c")
        self.conversation.insert("end", text + "\n\n", tag)
        self.conversation.configure(state="disabled")
        self.conversation.see("end")
        return start

    def _replace_thinking(self, text: str, tag: str = "assistant") -> None:
        if self._thinking_start is None:
            self._append(text, tag)
            return
        self.conversation.configure(state="normal")
        start = self._thinking_start
        end = f"{start}+{len('Thinkingâ€¦')}c"
        self.conversation.delete(start, end)
        self.conversation.insert(start, text, tag)
        self.conversation.configure(state="disabled")
        self.conversation.see("end")
        self._thinking_start = None

    def _background(self, work: Callable[[], Any], success: Callable[[Any], None]) -> None:
        def runner() -> None:
            try:
                result = work()
            except Exception as exc:
                self.window.after(0, lambda: self._error(str(exc)))
            else:
                self.window.after(0, lambda: success(result))
        threading.Thread(target=runner, daemon=True).start()

    def _error(self, message: str) -> None:
        self._append(f"I couldn't complete that: {message}", "muted")
        messagebox.showerror("Narrow", message, parent=self.window)

    def new_chat(self) -> None:
        self.conversation.configure(state="normal")
        self.conversation.delete("1.0", "end")
        self.conversation.configure(state="disabled")
        self._append("New local chat", "welcome")
        self._append("Ask about the sources in your knowledge base.", "muted")

    def focus_composer(self) -> None:
        self.message.focus_set()

    def choose_files(self) -> None:
        paths = filedialog.askopenfilenames(title="Add sources to Narrow", filetypes=[("All files", "*.*")])
        if not paths:
            return
        self._append(f"You added {len(paths)} source(s).", "user")
        self._background(lambda: [ingest_source(path, root=self.root_path) for path in paths], self._imported)

    def _imported(self, destinations: list[Path]) -> None:
        self.kb = None
        for destination in destinations:
            self.sources.append(destination.name)
            self.source_list.insert("end", destination.name)
        self._append(f"Added {len(destinations)} source(s). I can now search their extracted context.", "assistant")

    def send(self) -> None:
        query = self.message.get("1.0", "end").strip()
        if not query:
            return
        self.message.delete("1.0", "end")
        self._append(query, "user")
        quick_reply = self.assistant.quick_reply(query)
        if quick_reply:
            self._append(quick_reply, "assistant")
            self.assistant._remember(query, quick_reply)
            return
        if query.startswith(("http://", "https://")) and " " not in query:
            self._background(lambda: ingest_source(query, root=self.root_path), self._import_url_done)
            return
        if self.assistant.is_casual(query):
            self._thinking_start = self.conversation.index("end-1c")
            self._append("Thinking…", "muted")
            self._background(lambda: self.assistant.chat(query), self._show_answer)
        else:
            self._append("Searching your local sources…", "muted")
            self._background(lambda: self._answer(query), self._show_answer)

    def _import_url_done(self, destination: Path) -> None:
        self.kb = None
        self.sources.append(destination.name)
        self.source_list.insert("end", destination.name)
        self._append("Imported the article locally. Ask me a question about it.", "assistant")

    def _search(self, query: str) -> dict[str, Any]:
        if self.kb is None:
            self.kb = KnowledgeBase(root=self.root_path, model_path=self.model_path)
        return self.kb.search(query)

    def _answer(self, query: str) -> dict[str, Any]:
        return self.assistant.answer(query, self._search(query))

    def _show_answer(self, result: dict[str, Any]) -> None:
        self._replace_thinking(result["answer"], "assistant")
        if result.get("model_error"):
            self._append(
                "Start Ollama locally and make sure LLM_MODEL is installed for conversational answers. "
                f"Technical detail: {result['model_error']}",
                "muted",
            )
            return
        passages = result.get("passages", [])
        if result.get("abstain"):
            return
        parts = [f"Sources used ({len(passages)}):"]
        for index, passage in enumerate(passages, start=1):
            parts.append(f"[E{index}] {passage['id']}  score {passage['score']:.3f}")
        self._append("\n".join(parts), "muted")

    def _show_sources(self, result: dict[str, Any]) -> None:
        passages = result.get("passages", [])
        if result.get("abstain"):
            self._append("I don't have strong enough evidence in the local sources to answer that.", "assistant")
            return
        parts = [f"I found {len(passages)} relevant passage(s):"]
        for index, passage in enumerate(passages, start=1):
            parts.extend([f"\n{index}. {passage['id']}  •  evidence score {passage['score']:.3f}", passage["text"]])
        self._append("\n".join(parts), "assistant")


def main() -> None:
    window = tk.Tk()
    NarrowGUI(window)
    window.mainloop()


if __name__ == "__main__":
    main()
