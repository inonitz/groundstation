"""Mission helpers: step_text, one mission step as text (the chat on screen)."""


def step_text(step):
    """One mission action -> compact 'type k=v k=v' (the chat's command list, the
    review report)."""
    fields = ""
    if not isinstance(step, dict):
        return str(step)

    fields = " ".join(f"{k}={v}" for k, v in step.items() if k != "type")
    return (step.get("type", "?") + " " + fields).strip()
