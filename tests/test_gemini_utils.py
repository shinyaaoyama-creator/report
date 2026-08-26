from src.collector.gemini_utils import call_with_retries


class _FakeResponse:
    def __init__(self, text):
        self.text = text


class _FakeModels:
    def __init__(self, outer):
        self._outer = outer

    def generate_content(self, model, contents):
        response = self._outer._responses[self._outer.calls]
        self._outer.calls += 1
        if isinstance(response, Exception):
            raise response
        return response


class _FakeClient:
    def __init__(self, responses):
        self._responses = responses
        self.calls = 0

    @property
    def models(self):
        return _FakeModels(self)


def test_call_with_retries_returns_text_on_success():
    client = _FakeClient([_FakeResponse("hello")])

    result = call_with_retries(client, "gemini-flash-latest", "prompt", max_retries=3)

    assert result == "hello"


def test_call_with_retries_retries_then_succeeds():
    client = _FakeClient([ConnectionError("boom"), _FakeResponse("hello")])

    result = call_with_retries(client, "gemini-flash-latest", "prompt", max_retries=3)

    assert result == "hello"
    assert client.calls == 2


def test_call_with_retries_returns_none_after_exhausting_retries():
    client = _FakeClient([ConnectionError("boom"), ConnectionError("boom"), ConnectionError("boom")])

    result = call_with_retries(client, "gemini-flash-latest", "prompt", max_retries=3)

    assert result is None
    assert client.calls == 3
