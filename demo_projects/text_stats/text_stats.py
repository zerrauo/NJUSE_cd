"""Small text-statistics helpers used for the coding-agent demo."""


def average_word_length(text: str) -> float:
    """Return the average length of whitespace-separated words.

    An empty or whitespace-only string has an average length of 0.0.
    """
    words = text.split()
    if not words:
        return 0.0
    return sum(len(word) for word in words) / len(words)
