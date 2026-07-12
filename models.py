# models.py
from dataclasses import dataclass, field
from typing import List, Set, Optional, Dict

@dataclass
class FAQ:
    id: int
    slug: str
    keywords: List[str]
    answer: str
    normalized_keywords: List[str] = field(default_factory=list)
    lemmas: List[str] = field(default_factory=list)
    topics: Set[str] = field(default_factory=set)

@dataclass
class Candidate:
    id: Optional[int]
    slug: Optional[str]
    score: float
    base_score: float
    topic_bonus: int
    keyword: str

@dataclass
class SearchDebug:
    tokens: List[str]
    lemmas: List[str]
    topics: List[str]
    candidates: List[Dict]

@dataclass
class SearchResult:
    id: Optional[int] = None
    slug: Optional[str] = None
    answer: Optional[str] = None
    score: float = -1
    base_score: float = 0
    topic_bonus: int = 0
    keyword: str = ''
    topics: Set[str] = field(default_factory=set)
    is_exact: bool = False
    candidates: List[Candidate] = field(default_factory=list)
    debug: Optional[SearchDebug] = None
    engine_version: str = "2.0.0"
