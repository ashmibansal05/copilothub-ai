import re
from collections import Counter

_SENTENCES = re.compile(r"(?<=[.!?])\s+|\n{2,}")
_WORDS = re.compile(r"[a-z0-9]{3,}")
_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were", "will", "not",
    "you", "your", "have", "has", "had", "but", "all", "can", "its", "their", "they", "which",
    "also", "into", "than", "then", "there", "these", "those", "such", "been", "being",
}


def extractive_summary(text: str, max_sentences: int = 5) -> list[str]:
    """Pick the most informative existing sentences (no language model involved).

    A sentence scores higher when it uses words that appear often in the document;
    the score is divided by the square root of its length so long sentences do not
    win automatically. The chosen sentences are returned in their original order."""
    sentences = [s.strip() for s in _SENTENCES.split(text) if len(s.strip()) >= 30]
    if len(sentences) <= max_sentences:
        return sentences

    def words(sentence: str) -> list[str]:
        return [w for w in _WORDS.findall(sentence.lower()) if w not in _STOPWORDS]

    frequency = Counter(w for s in sentences for w in words(s))
    scored = []
    for index, sentence in enumerate(sentences):
        tokens = words(sentence)
        score = sum(frequency[w] for w in tokens) / (len(tokens) ** 0.5) if tokens else 0.0
        scored.append((score, index))
    best = sorted(scored, reverse=True)[:max_sentences]
    return [sentences[i] for _, i in sorted(best, key=lambda pair: pair[1])]