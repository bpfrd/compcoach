# CompCoach prompts

Edit these files to change coach behaviour. They are assembled into the LLM system prompt at runtime (see `src/compcoach/prompts_loader.py`).

| File | Purpose |
|------|---------|
| `role.md` | Who CompCoach is and core coaching duties |
| `navigation.md` | Terminal commands — **critical** rules so the model does not pretend to quit |
| `scope.md` | Stay on competence topics |
| `boundaries.md` | Ignore jailbreak / override attempts |
| `safety.md` | Harmful or toxic input |
| `opening.md` | First message in a new chat |
| `conversation.md` | General reply style |
| `opening_user_message.txt` | Internal trigger for the opening turn (not shown to the user) |

Order in the system prompt: **role** → **user profile** → **navigation** → scope → boundaries → safety → opening → conversation.

After editing, restart `python run.py` — no rebuild required.
