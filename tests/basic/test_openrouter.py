from pathlib import Path
import sys
import types

if "numpy" not in sys.modules:
    numpy_module = types.ModuleType("numpy")
    numpy_module.ndarray = object
    numpy_module.array = lambda *a, **k: None
    numpy_module.dot = lambda *a, **k: 0.0
    numpy_module.linalg = types.SimpleNamespace(norm=lambda *a, **k: 1.0)
    sys.modules["numpy"] = numpy_module

if "PIL" not in sys.modules:
    pil_module = types.ModuleType("PIL")
    image_module = types.ModuleType("PIL.Image")
    image_grab_module = types.ModuleType("PIL.ImageGrab")

    class _DummyImage:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        @property
        def size(self):
            return (1024, 1024)

    def _dummy_open(*args, **kwargs):
        return _DummyImage()

    image_module.open = _dummy_open
    image_grab_module.grab = _dummy_open
    pil_module.Image = image_module
    pil_module.ImageGrab = image_grab_module
    sys.modules["PIL"] = pil_module
    sys.modules["PIL.Image"] = image_module
    sys.modules["PIL.ImageGrab"] = image_grab_module

if "oslex" not in sys.modules:
    oslex_module = types.ModuleType("oslex")
    oslex_module.__all__ = []
    sys.modules["oslex"] = oslex_module

if "rich" not in sys.modules:
    rich_module = types.ModuleType("rich")
    console_module = types.ModuleType("rich.console")

    class _DummyConsole:
        def __init__(self, *args, **kwargs):
            pass

        def status(self, *args, **kwargs):
            return self

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def update(self, *args, **kwargs):
            return None

    console_module.Console = _DummyConsole
    rich_module.console = console_module
    sys.modules["rich"] = rich_module
    sys.modules["rich.console"] = console_module

if "pyperclip" not in sys.modules:
    pyperclip_module = types.ModuleType("pyperclip")

    class _DummyPyperclipException(Exception):
        pass

    pyperclip_module.PyperclipException = _DummyPyperclipException
    pyperclip_module.copy = lambda *args, **kwargs: None
    sys.modules["pyperclip"] = pyperclip_module

if "pexpect" not in sys.modules:
    pexpect_module = types.ModuleType("pexpect")

    class _DummySpawn:
        def __init__(self, *args, **kwargs):
            pass

        def sendline(self, *args, **kwargs):
            return 0

        def close(self, *args, **kwargs):
            return 0

    pexpect_module.spawn = _DummySpawn
    sys.modules["pexpect"] = pexpect_module

if "psutil" not in sys.modules:
    psutil_module = types.ModuleType("psutil")

    class _DummyProcess:
        def __init__(self, *args, **kwargs):
            pass

        def children(self, *args, **kwargs):
            return []

        def terminate(self):
            return None

    psutil_module.Process = _DummyProcess
    sys.modules["psutil"] = psutil_module

if "pypandoc" not in sys.modules:
    pypandoc_module = types.ModuleType("pypandoc")
    pypandoc_module.convert_text = lambda *args, **kwargs: ""
    sys.modules["pypandoc"] = pypandoc_module

from aider.helpers.model_providers import ModelProviderManager
from aider.models import ModelInfoManager
import aider.models as models_module


class DummyResponse:
    """Minimal stand-in for requests.Response used in tests."""

    def __init__(self, json_data):
        self.status_code = 200
        self._json_data = json_data

    def json(self):
        return self._json_data

    def raise_for_status(self):
        return None


def test_openrouter_get_model_info_from_cache(monkeypatch, tmp_path):
    """
    ModelProviderManager should return correct metadata taken from the
    downloaded (and locally cached) models JSON payload.
    """
    payload = {
        "data": [
            {
                "id": "mistralai/mistral-medium-3",
                "context_length": 32768,
                "pricing": {"prompt": "100", "completion": "200"},
                "top_provider": {"context_length": 32768},
            }
        ]
    }

    # Fake out the network call and the HOME directory used for the cache file
    monkeypatch.setattr("requests.get", lambda *a, **k: DummyResponse(payload))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))

    provider_config = {
        "openrouter": {
            "api_base": "https://openrouter.ai/api/v1",
            "models_url": "https://openrouter.ai/api/v1/models",
            "requires_api_key": False,
        }
    }
    manager = ModelProviderManager(provider_configs=provider_config)
    info = manager.get_model_info("openrouter/mistralai/mistral-medium-3")

    assert info["max_input_tokens"] == 32768
    assert info["input_cost_per_token"] == 100.0
    assert info["output_cost_per_token"] == 200.0
    assert info["litellm_provider"] == "openrouter"


def test_model_info_manager_uses_openrouter_manager(monkeypatch):
    """
    ModelInfoManager should delegate to ModelProviderManager when litellm
    provides no data for an OpenRouter-prefixed model.
    """
    # Ensure litellm path returns no info so that fallback logic triggers
    monkeypatch.setattr(
        models_module,
        "litellm",
        types.SimpleNamespace(_lazy_module=None, get_model_info=lambda *a, **k: {}),
    )

    stub_info = {
        "max_input_tokens": 512,
        "max_tokens": 512,
        "max_output_tokens": 512,
        "input_cost_per_token": 100.0,
        "output_cost_per_token": 200.0,
        "litellm_provider": "openrouter",
    }

    # Force ModelProviderManager to return our stub info
    monkeypatch.setattr(
        "aider.helpers.model_providers.ModelProviderManager.get_model_info",
        lambda self, model: stub_info,
    )
    monkeypatch.setattr(
        "aider.helpers.model_providers.ModelProviderManager.supports_provider",
        lambda self, provider: provider == "openrouter",
    )

    mim = ModelInfoManager()
    info = mim.get_model_info("openrouter/fake/model")

    assert info == stub_info
