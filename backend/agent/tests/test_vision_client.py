"""Issue 392: the Anthropic client for panorama reading, and that only live runs switch vision on."""
from types import SimpleNamespace

from backend.agent import live
from backend.agent.vision_client import Usage, enable_vision, make_ask_model, make_get_bytes


class FakeClient:
    def __init__(self):
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(content=[SimpleNamespace(text='{"ok": 1}')],
                               usage=SimpleNamespace(input_tokens=1000, output_tokens=100))


def test_ask_model_sends_images_then_prompt_and_counts_usage():
    client, usage = FakeClient(), Usage()
    ask = make_ask_model(client, usage, model="m")
    assert ask([b"\xff\xd8abc", b"\x89PNGxyz"], "read this") == '{"ok": 1}'
    content = client.calls[0]["messages"][0]["content"]
    assert [c["type"] for c in content] == ["image", "image", "text"]
    assert content[0]["source"]["media_type"] == "image/jpeg" and content[1]["source"]["media_type"] == "image/png"
    assert (usage.calls, usage.input_tokens, usage.output_tokens) == (1, 1000, 100) and usage.cost_usd > 0


def test_enable_vision_needs_a_key_and_a_door_that_can_take_it(monkeypatch):
    seen = {}
    door = SimpleNamespace(set_vision=lambda **kw: seen.update(kw))
    data = SimpleNamespace(get_asset=lambda p: b"")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert enable_vision(door, data) is False and not seen
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-a-key")
    monkeypatch.setattr("backend.agent.vision_client.make_ask_model", lambda **kw: "ask")
    assert enable_vision(door, data) is True and seen["get_bytes"]("data/cache/s/x.json") == b""
    assert enable_vision(SimpleNamespace(), data) is False


def test_only_live_runs_switch_vision_on(monkeypatch):
    calls = []
    monkeypatch.setattr("backend.agent.vision_client.enable_vision", lambda a, d, usage=None: calls.append(a) or True)
    doors = SimpleNamespace(degraded=None, analysis="A", data="D")
    assert live.enable_real_vision(doors) is True and calls == ["A"]
    monkeypatch.setenv("AGENT_VISION", "0")
    assert live.enable_real_vision(doors) is False
    monkeypatch.delenv("AGENT_VISION")
    assert live.enable_real_vision(SimpleNamespace(degraded="broken", analysis="A", data="D")) is False


def test_get_bytes_uses_get_pano_faces_for_panorama_paths_once_per_pano_and_get_asset_otherwise():
    fetched = []
    data = SimpleNamespace(get_asset=lambda p: b"asset:" + p.encode(),
                           get_pano_faces=lambda sid, pano, d: fetched.append((sid, pano, d)) or [bytes([i]) for i in range(6)])
    get = make_get_bytes(data)
    assert get("data/cache/SID1/panos/pA/face0.jpg") == b"\x00"
    assert get("data/cache/SID1/panos/pA/face3.jpg") == b"\x03"
    assert get("data/cache/SID1/defurnished/panos/pA/face1.jpg") == b"\x01"
    assert fetched == [("SID1", "pA", False), ("SID1", "pA", True)]
    assert get("data/cache/SID1/bundle.json") == b"asset:data/cache/SID1/bundle.json"
    old = make_get_bytes(SimpleNamespace(get_asset=lambda p: b"a"))
    assert old("data/cache/S/panos/p/face0.jpg") == b"a"


def test_defurnished_paths_fall_back_to_the_furnished_faces_when_the_data_layer_has_none():
    def fetch(sid, pano, defurnished):
        if defurnished:
            raise LookupError("not fetched")
        return [bytes([i]) for i in range(6)]
    get = make_get_bytes(SimpleNamespace(get_asset=lambda p: b"", get_pano_faces=fetch))
    assert get("data/cache/S/defurnished/panos/p/face2.jpg") == b"\x02"
