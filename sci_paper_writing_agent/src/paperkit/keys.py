"""Answers typed at a prompt, whatever the keyboard layout, and without crashing on bytes the terminal garbled."""
from __future__ import annotations

RUSSIAN = str.maketrans("йцукенгшщзфывапролдячсмить", "qwertyuiopasdfghjklzxcvbnm")
YES = ("н", "д", "да")          # "н" is the Y key on the Russian layout; "да" is yes


def latin(answer: str) -> str:
    """The same keys read as Latin letters, so a menu letter typed on the Russian layout still works."""
    return answer.translate(RUSSIAN)


def is_yes(answer: str) -> bool:
    answer = answer.strip().lower()
    return answer.startswith("y") or answer in YES


def read(ask, prompt: str, out=print, tries: int = 5) -> str:
    """One answer from `ask`. If the terminal hands over bytes that are not text, the question is asked again.

    That happens when a non-Latin letter is typed and then deleted: the terminal removes only half of the
    letter, and the half that is left cannot be read as text.
    """
    for _ in range(tries):
        try:
            return ask(prompt)
        except UnicodeDecodeError:
            out("That could not be read: a deleted non-Latin letter left a stray byte behind. Please type it again.")
    raise EOFError("no readable answer")
