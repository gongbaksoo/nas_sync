# Design Ref: §3.12 — 형태소 분석(Kiwi), 문장 분리(KSS)


class KoreanProcessor:
    def __init__(self):
        self._kiwi = None
        self._kss = None

    def _ensure_kiwi(self):
        if self._kiwi is None:
            from kiwipiepy import Kiwi
            self._kiwi = Kiwi()

    def _ensure_kss(self):
        if self._kss is None:
            import kss
            self._kss = kss

    def split_sentences(self, text: str) -> list[str]:
        """KSS로 한국어 문장 분리"""
        self._ensure_kss()
        try:
            return self._kss.split_sentences(text)
        except Exception:
            return [s.strip() for s in text.split("\n") if s.strip()]

    def extract_nouns(self, text: str) -> list[str]:
        """Kiwi로 핵심 명사 추출 (검색 쿼리 확장용)"""
        self._ensure_kiwi()
        tokens = self._kiwi.tokenize(text)
        return [t.form for t in tokens if t.tag.startswith("NN")]

    def normalize_for_search(self, text: str) -> str:
        """검색용 텍스트 정규화 (형태소 분석 + 핵심어 추출)"""
        nouns = self.extract_nouns(text)
        return " ".join(nouns)
