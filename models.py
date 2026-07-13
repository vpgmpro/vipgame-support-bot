from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class FAQ:
    id: int
    slug: str
    title: str
    category: str
    sort: int = 0
    keywords: List[str] = field(default_factory=list)
    answer: str = ""
