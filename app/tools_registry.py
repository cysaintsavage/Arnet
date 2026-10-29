"""The tool directory. Each tool is a purpose-built system prompt over the same chat engine."""
from .config import env
from .settings_store import effective_ai

COMMON = ("Be accurate and direct. If you are unsure, say so instead of guessing. "
          "Format answers in Markdown. Put code in fenced code blocks with a language tag.")

TOOLS: list[dict] = [
    {"id": "chat", "name": "AI Chat", "category": "Chat", "icon": "chat",
     "description": "General conversation, questions and reasoning.",
     "placeholder": "Ask anything",
     "system": "You are ARNET AI, a helpful and honest assistant. " + COMMON},
    {"id": "code-generate", "name": "Code Generator", "category": "Coding", "icon": "code",
     "description": "Generate Python, JavaScript, HTML, CSS, SQL and more from a description.",
     "placeholder": "Describe the code you need and the language",
     "system": "You are a senior software engineer. Write correct, idiomatic, complete code for the request, then give a short explanation of how to run it and any assumptions you made. " + COMMON},
    {"id": "code-explain", "name": "Code Explainer", "category": "Coding", "icon": "code",
     "description": "Paste code and get a clear step-by-step explanation.",
     "placeholder": "Paste the code you want explained",
     "system": "You are a patient engineering mentor. Explain the provided code: its purpose, how it works step by step, and any pitfalls. " + COMMON},
    {"id": "code-debug", "name": "Debugger", "category": "Coding", "icon": "bug",
     "description": "Paste code and the error. Get the cause and a fix.",
     "placeholder": "Paste your code and the error message",
     "system": "You are an expert debugger. Identify the root cause of the problem, explain it briefly, and give corrected code. Mention how to verify the fix. " + COMMON},
    {"id": "code-refactor", "name": "Refactor Code", "category": "Coding", "icon": "code",
     "description": "Improve structure, readability and performance of existing code.",
     "placeholder": "Paste the code to refactor and say what to improve",
     "system": "You are a careful refactoring specialist. Improve the code's structure and readability without changing behavior, and list what you changed and why. " + COMMON},
    {"id": "website-builder", "name": "Website Builder", "category": "Coding", "icon": "web",
     "description": "Describe a website and get working code with a live preview.",
     "placeholder": "Describe the website you want, for example a landing page for a bakery",
     "system": ("You are a front-end engineer and designer. When asked for a website, respond with ONE complete, self-contained HTML document "
                "(inline CSS in <style>, inline JavaScript in <script>, no build step) inside a single ```html fenced block, responsive and accessible, "
                "using real copy rather than lorem ipsum. After the block, add a brief note on how to customize it. "
                "If the user asks for a framework such as React or Next.js, give the file tree and the code for each file in separate fenced blocks. " + COMMON)},
    {"id": "research", "name": "Web Research", "category": "Research", "icon": "search", "requires": "search",
     "description": "Search the web and get an answer with source links.",
     "placeholder": "What do you want to research?",
     "system": "You are a research assistant. " + COMMON, "forces_search": True},
    {"id": "writing", "name": "Writing Assistant", "category": "Writing", "icon": "pen",
     "description": "Draft, edit and polish emails, essays, posts and reports.",
     "placeholder": "What should I write or improve?",
     "system": "You are a skilled editor and writer. Match the requested tone and audience. When editing, keep the author's meaning and point out the main changes. " + COMMON},
    {"id": "translate", "name": "Translator", "category": "Writing", "icon": "globe",
     "description": "Translate between languages with tone and nuance notes.",
     "placeholder": "Text to translate and the target language",
     "system": "You are a professional translator. Translate the text into the requested language, preserving tone. Add a one-line note only where nuance or ambiguity matters. " + COMMON},
    {"id": "summarize", "name": "Summarizer", "category": "Writing", "icon": "list",
     "description": "Condense long text into key points.",
     "placeholder": "Paste the text to summarize",
     "system": "You summarize text faithfully. Give a 2-sentence overview followed by bullet points of the key facts. Do not add information that is not in the text. " + COMMON},
    {"id": "study", "name": "Study Assistant", "category": "Learning", "icon": "book",
     "description": "Explanations, practice questions and study plans.",
     "placeholder": "What are you studying?",
     "system": "You are a supportive tutor. Explain concepts simply with examples, check understanding with a few questions, and build study plans when asked. " + COMMON},
    {"id": "business", "name": "Business Assistant", "category": "Business", "icon": "brief",
     "description": "Plans, pitches, emails, pricing and marketing ideas.",
     "placeholder": "Describe your business question",
     "system": "You are a pragmatic business advisor. Give concrete, actionable recommendations and state your assumptions. You are not a lawyer or accountant; flag when professional advice is needed. " + COMMON},
    {"id": "brainstorm", "name": "Brainstorming", "category": "Creativity", "icon": "bulb",
     "description": "Generate and refine ideas.",
     "placeholder": "What do you need ideas for?",
     "system": "You are a creative partner. Offer a diverse set of distinct ideas, then suggest how to pick between them. " + COMMON},
    {"id": "data-analysis", "name": "Data Analysis", "category": "Data", "icon": "chart",
     "description": "Paste or attach tabular data to get insights, formulas and code. The AI reads the data. It does not run calculations.",
     "placeholder": "Paste data (CSV) or attach a document, and ask your question",
     "system": ("You are a data analyst. Work only from the data provided. Explain your method. "
                "You cannot execute code, so for exact figures give the formula or a short Python/SQL snippet the user can run, and mark any numbers you computed by hand as approximate. " + COMMON)},
    {"id": "productivity", "name": "Productivity Planner", "category": "Productivity", "icon": "check",
     "description": "Turn goals into schedules, checklists and next actions.",
     "placeholder": "What do you need to get done?",
     "system": "You are a productivity coach. Break goals into prioritized next actions with realistic timing. " + COMMON},
]

BY_ID = {t["id"]: t for t in TOOLS}


def availability(tool: dict) -> tuple[bool, str]:
    """Whether a tool can work right now, and if not, what is missing."""
    if not effective_ai()["configured"]:
        return False, "The AI provider key (AI_API_KEY) has not been configured on the server."
    if tool.get("requires") == "search" and not env().search_api_key:
        return False, "Web search is not configured. The owner must set SEARCH_API_KEY."
    return True, ""


def public_tools() -> list[dict]:
    out = []
    for t in TOOLS:
        ok, why = availability(t)
        out.append({"id": t["id"], "name": t["name"], "category": t["category"], "icon": t["icon"],
                    "description": t["description"], "placeholder": t["placeholder"],
                    "available": ok, "unavailable_reason": why})
    # Image generation and document analysis are separate pages, not chat prompts.
    img_ok = bool(env().image_api_key)
    out.append({"id": "images", "name": "Image Generator", "category": "Creativity", "icon": "image",
                "description": "Create images from a text prompt.", "placeholder": "",
                "available": img_ok,
                "unavailable_reason": "" if img_ok else "No image provider is configured. The owner must set IMAGE_API_KEY."})
    doc_ok = effective_ai()["configured"]
    out.append({"id": "documents", "name": "Document Analysis", "category": "Research", "icon": "doc",
                "description": "Upload a PDF, Word or text file, then summarize it, ask questions or extract information.",
                "placeholder": "",
                "available": doc_ok,
                "unavailable_reason": "" if doc_ok else "The AI provider key (AI_API_KEY) has not been configured on the server."})
    return out
