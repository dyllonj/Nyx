class HarnessError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        hint: str | None = None,
        details: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.details = details


class DependencyError(HarnessError):
    pass


def format_error(err: HarnessError) -> str:
    lines = [f"[{err.code}] {err.message}"]
    if err.hint:
        lines.append(f"Hint: {err.hint}")
    if err.details:
        lines.append(f"Details: {err.details}")
    return "\n".join(lines)
