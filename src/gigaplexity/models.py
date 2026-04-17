"""Data models for GigaChat API requests and responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SearchMode(str, Enum):
    """Available search modes."""

    ASK = "ask"
    RESEARCH = "research"
    REASON = "reason"


class FileCategory(str, Enum):
    """Attachment category — server only allows files of one category per request."""

    DOC = "DOC"
    IMAGE = "IMAGE"
    AUDIO = "AUDIO"


# Extension → (otr fileType, category)
_EXT_MAP: dict[str, tuple[str, FileCategory]] = {}

_DOC_TYPES: dict[str, list[str]] = {
    "PDF": ["pdf"],
    "WORD": ["doc", "docx", "html"],
    "PPTX": ["pptx", "ppt"],
    "SPREADSHEET": ["xlsx", "xls", "ods"],
    "EPUB": ["epub"],
    "TEXT": [
        "txt", "csv", "log", "md", "json", "xml", "yaml", "yml",
        "py", "js", "ts", "java", "c", "cpp", "cxx", "c++", "h", "hpp",
        "cs", "go", "rs", "rb", "php", "swift", "kt", "kts", "scala", "sc",
        "r", "jl", "lua", "pl", "pm", "sh", "bash", "zsh", "fish",
        "ps1", "bat", "cmd", "sql", "css", "scss", "sass", "less",
        "jsx", "tsx", "vue", "svelte", "hs", "ex", "exs", "clj",
        "groovy", "vb", "vbs", "fs", "lisp", "lsp", "tcsh", "mm",
        "ini", "toml", "cfg", "conf", "env", "dockerfile",
        "makefile", "cmake", "gradle",
    ],
}

_IMAGE_EXTS = ["jpg", "jpeg", "jpe", "png", "webp", "heic", "heif", "bmp"]
_AUDIO_EXTS = ["mp3", "aac", "m4a", "opus", "wav", "ogg"]

for _ftype, _exts in _DOC_TYPES.items():
    for _ext in _exts:
        _EXT_MAP[_ext] = (_ftype, FileCategory.DOC)
for _ext in _IMAGE_EXTS:
    _EXT_MAP[_ext] = ("IMAGE", FileCategory.IMAGE)
for _ext in _AUDIO_EXTS:
    _EXT_MAP[_ext] = ("AUDIO", FileCategory.AUDIO)


def resolve_file_type(extension: str) -> tuple[str, FileCategory]:
    """Return (otr_file_type, category) for a file extension.

    Raises ValueError for unsupported extensions.
    """
    ext = extension.lower().lstrip(".")
    if ext not in _EXT_MAP:
        raise ValueError(
            f"Unsupported file extension: .{ext}. "
            f"Supported: documents, images ({', '.join(_IMAGE_EXTS)}), "
            f"audio ({', '.join(_AUDIO_EXTS)})"
        )
    return _EXT_MAP[ext]


@dataclass
class AttachmentInfo:
    """Uploaded attachment metadata for inclusion in request payload."""

    hash: str
    key: str
    category: FileCategory
    audio_duration: float | None = None

    def to_payload(self) -> dict:
        """Serialize for the sessions/request ``files`` array."""
        return {
            "hash": self.hash,
            "path": self.key,
            "source": "ATTACHMENTS",
            "audio": {"duration": self.audio_duration} if self.audio_duration is not None else None,
        }


# Agent UUIDs for each mode
AGENT_IDS: dict[SearchMode, str] = {
    SearchMode.ASK: "019a5d95-ab99-7c86-a31c-610dad03b054",
    SearchMode.RESEARCH: "9384a8fd-39e0-4da9-9bc4-da143487449f",
    SearchMode.REASON: "7101c625-42ab-45fe-b168-323970c12eba",
}

# Model names for each mode
MODEL_NAMES: dict[SearchMode, str | None] = {
    SearchMode.ASK: None,  # Server defaults to GigaChat-3-Ultra
    SearchMode.RESEARCH: "GigaChat-3-Ultra",
    SearchMode.REASON: "GigaChat-2-Reasoning",
}


@dataclass
class Citation:
    """A source citation from search results."""

    key: str
    title: str
    url: str
    type: str = "FOOTNOTE"


@dataclass
class ReasoningStep:
    """A reasoning step from the reason mode."""

    type: str
    value: str


@dataclass
class SearchResult:
    """Aggregated search result."""

    text: str
    citations: list[Citation] = field(default_factory=list)
    reasoning_steps: list[ReasoningStep] = field(default_factory=list)
    research_log: str = ""
    model: str = ""
    mode: SearchMode = SearchMode.ASK
    session_id: str = ""
    message_id: str = ""

    def format_markdown(self) -> str:
        """Format the result as markdown with citations."""
        parts: list[str] = []

        if self.reasoning_steps:
            parts.append("<details><summary>Reasoning</summary>\n")
            for step in self.reasoning_steps:
                parts.append(step.value)
            parts.append("\n</details>\n")

        if self.research_log:
            parts.append("<details><summary>Research Log</summary>\n")
            parts.append(self.research_log)
            parts.append("\n</details>\n")

        parts.append(self.text)

        if self.citations:
            parts.append("\n\n---\n**Sources:**\n")
            for c in self.citations:
                parts.append(f"[{c.key}] [{c.title}]({c.url})")

        return "\n".join(parts)


def build_request_payload(
    query: str,
    mode: SearchMode,
    session_id: str,
    *,
    domains: list[str] | None = None,
    extended_research: bool = False,
    tone: str = "",
    attachments: list[AttachmentInfo] | None = None,
) -> dict:
    """Build the JSON payload for the sessions/request endpoint."""
    payload: dict = {
        "text": query,
        "agent": AGENT_IDS[mode],
        "sessionId": session_id,
        "featureFlags": [],
    }

    model = MODEL_NAMES[mode]
    if model:
        payload["model"] = model

    if mode == SearchMode.RESEARCH:
        payload["aiAgent"] = {
            "queryDomains": domains or [],
            "extendedResearch": extended_research,
            "tone": tone,
        }

    if attachments:
        payload["files"] = [a.to_payload() for a in attachments]

    return payload
