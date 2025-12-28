import json
import math
import sys
import types
from pathlib import Path

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

if "numpy" not in sys.modules:
    numpy_module = types.ModuleType("numpy")
    numpy_module.ndarray = object
    numpy_module.array = lambda *a, **k: None
    numpy_module.dot = lambda *a, **k: 0.0
    numpy_module.linalg = types.SimpleNamespace(norm=lambda *a, **k: 1.0)
    sys.modules["numpy"] = numpy_module

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

import aider.models as models_module
from aider.commands.model import ModelCommand
from aider.models import ModelInfoManager
from aider.helpers.model_providers import ModelProviderManager, _JSONOpenAIProvider


class DummyResponse:
    """Minimal stand-in for requests.Response used in tests."""

    def __init__(self, json_data):
        self.status_code = 200
        self._json_data = json_data

    def json(self):
        return self._json_data

    def raise_for_status(self):
        return None


def _load_openai_fixture():
    return {
        "data": [
            {
                "id": "zai-org/GLM-4.6",
                "object": "model",
                "created": 1723500000,
                "owned_by": "openai",
                "max_input_tokens": 131072,
                "max_output_tokens": 131072,
                "max_tokens": 131072,
                "context_length": 131072,
                "context_window": 131072,
                "top_provider_context_length": 131072,
                "pricing": {
                    "prompt": "0.00000055",
                    "completion": "0.00000219",
                },
            },
            {
                "id": "zai-org/GLM-4.6:extended",
                "object": "model",
                "created": 1723500001,
                "owned_by": "openai",
                "max_tokens": 65536,
                "pricing": {
                    "prompt": "0.00000060",
                    "completion": "0.00000250",
                },
            },
        ]
    }


def _test_provider_config():
    return {
        "openai": {
            "api_base": "https://api.openai.com/v1",
            "models_url": "https://api.openai.com/v1/models",
            "api_key_env": ["OPENAI_API_KEY"],
            "base_url_env": ["OPENAI_API_BASE"],
            "default_headers": {},
        }
    }


def test_provider_manager_get_model_info_from_cache(monkeypatch, tmp_path):
    """ModelProviderManager should hydrate from cached payloads."""

    payload = _load_openai_fixture()

    def _fail_request(*args, **kwargs):  # pragma: no cover - should never be called
        raise AssertionError("Network request should not be made when cache is valid")

    monkeypatch.setattr("requests.get", _fail_request)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))

    manager = ModelProviderManager(provider_configs=_test_provider_config())
    manager.cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = manager._get_cache_file("openai")
    cache_file.write_text(json.dumps(payload))

    info = manager.get_model_info("openai/zai-org/GLM-4.6:extended")

    assert info["max_input_tokens"] == 131072
    assert info["max_output_tokens"] == 131072
    assert info["max_tokens"] == 131072
    assert info["input_cost_per_token"] == 0.00000055
    assert info["output_cost_per_token"] == 0.00000219
    assert info["litellm_provider"] == "openai"
    assert manager._cache_loaded["openai"]


def test_provider_manager_models_endpoint_fetch(monkeypatch, tmp_path):
    """ModelProviderManager should fetch and cache the /models payload when missing."""

    payload = _load_openai_fixture()
    call_args = []

    def _recording_request(url, *, headers=None, timeout=None, verify=None):
        call_args.append((url, headers, timeout, verify))
        return DummyResponse(payload)

    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr("requests.get", _recording_request)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    provider_config = _test_provider_config()
    manager = ModelProviderManager(provider_configs=provider_config)
    manager.set_verify_ssl(False)

    info = manager.get_model_info("openai/zai-org/GLM-4.6:extended")

    expected_url = provider_config["openai"]["models_url"]
    assert call_args == [
        (
            expected_url,
            {"Authorization": "Bearer test-key"},
            10,
            False,
        )
    ]
    assert info["max_input_tokens"] == 131072
    assert info["max_output_tokens"] == 131072
    assert info["max_tokens"] == 131072
    assert info["input_cost_per_token"] == 0.00000055
    assert info["output_cost_per_token"] == 0.00000219


def test_provider_static_models_used_without_api_key(monkeypatch, tmp_path):
    payload = _load_openai_fixture()
    provider_config = _test_provider_config()
    provider_config["openai"]["static_models"] = payload["data"]

    def _fail_request(*args, **kwargs):  # pragma: no cover - should not run
        raise AssertionError("Network request should not be attempted without API key")

    monkeypatch.setattr("requests.get", _fail_request)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))

    manager = ModelProviderManager(provider_configs=provider_config)
    info = manager.get_model_info("openai/zai-org/GLM-4.6")

    assert info["litellm_provider"] == "openai"
    assert info["max_tokens"] == 131072


def test_provider_models_price_strings(monkeypatch, tmp_path):
    payload = {
        "data": [
            {
                "id": "demo/model",
                "max_input_tokens": 4096,
                "pricing": {"prompt": "$0.00000055", "completion": "$0.00000219"},
            }
        ]
    }

    provider_config = _test_provider_config()
    provider_config["openai"]["static_models"] = payload["data"]

    def _fail_request(*args, **kwargs):  # pragma: no cover - should not run
        raise AssertionError("Network fetch should be skipped when static models exist")

    monkeypatch.setattr("requests.get", _fail_request)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))

    manager = ModelProviderManager(provider_configs=provider_config)
    info = manager.get_model_info("openai/demo/model")

    assert math.isclose(info["input_cost_per_token"], 0.00000055)
    assert math.isclose(info["output_cost_per_token"], 0.00000219)


def test_model_info_manager_uses_provider_manager(monkeypatch):
    """ModelInfoManager should delegate to ModelProviderManager for openai-like models."""

    monkeypatch.setattr(
        models_module,
        "litellm",
        types.SimpleNamespace(_lazy_module=None, get_model_info=lambda *a, **k: {}),
    )

    stub_info = {
        "max_input_tokens": 1024,
        "max_tokens": 1024,
        "max_output_tokens": 1024,
        "input_cost_per_token": 0.0001,
        "output_cost_per_token": 0.0002,
        "litellm_provider": "openai",
    }

    monkeypatch.setattr(
        "aider.helpers.model_providers.ModelProviderManager.get_model_info",
        lambda self, model: stub_info,
    )

    mim = ModelInfoManager()
    info = mim.get_model_info("openai/demo/model")

    assert info == stub_info


def test_provider_manager_listing(monkeypatch, tmp_path):
    payload = _load_openai_fixture()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    manager = ModelProviderManager(provider_configs=_test_provider_config())
    manager.cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = manager._get_cache_file("openai")
    cache_file.write_text(json.dumps(payload))

    listings = manager.get_models_for_listing()

    assert "zai-org/GLM-4.6" in listings
    assert listings["zai-org/GLM-4.6"]["litellm_provider"] == "openai"
    assert listings["zai-org/GLM-4.6"]["mode"] == "chat"


def test_chat_model_names_include_openai_provider_models(monkeypatch, tmp_path):
    payload = _load_openai_fixture()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))

    import aider.models as models_module

    models_module.litellm = types.SimpleNamespace(model_cost={}, _lazy_module=None)
    models_module.model_info_manager = models_module.ModelInfoManager()
    models_module.model_info_manager.provider_manager = ModelProviderManager(
        provider_configs=_test_provider_config()
    )
    manager = models_module.model_info_manager.provider_manager
    manager.cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = manager._get_cache_file("openai")
    cache_file.write_text(json.dumps(payload))

    names = models_module.get_chat_model_names()

    assert "openai/zai-org/GLM-4.6" in names


def test_model_command_completions_include_openai_provider_models(monkeypatch, tmp_path):
    payload = _load_openai_fixture()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))

    import aider.models as models_module

    models_module.litellm = types.SimpleNamespace(model_cost={}, _lazy_module=None)
    models_module.model_info_manager = models_module.ModelInfoManager()
    models_module.model_info_manager.provider_manager = ModelProviderManager(
        provider_configs=_test_provider_config()
    )
    manager = models_module.model_info_manager.provider_manager
    manager.cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = manager._get_cache_file("openai")
    cache_file.write_text(json.dumps(payload))

    completions = ModelCommand.get_completions(io=None, coder=None, args="")

    assert "openai/zai-org/GLM-4.6" in completions


def test_model_disables_streaming_for_non_streaming_providers(monkeypatch):
    provider_configs = {
        "synthetic": {
            "api_base": "https://api.synthetic.new/openai/v1",
            "api_key_env": ["SYNTHETIC_API_KEY"],
            "supports_stream": False,
        }
    }

    provider_manager = ModelProviderManager(provider_configs=provider_configs)
    fake_info = {
        "max_input_tokens": 4096,
        "max_tokens": 4096,
        "max_output_tokens": 4096,
        "litellm_provider": "synthetic",
    }

    fake_model_info_manager = types.SimpleNamespace(
        get_model_info=lambda model: fake_info,
        provider_manager=provider_manager,
    )

    monkeypatch.setenv("SYNTHETIC_API_KEY", "test-key")
    monkeypatch.setattr(models_module, "model_info_manager", fake_model_info_manager)
    monkeypatch.setattr(
        models_module,
        "litellm",
        types.SimpleNamespace(
            encode=lambda *a, **k: [],
            token_counter=lambda *a, **k: 0,
            validate_environment=lambda model: {"keys_in_environment": True, "missing_keys": []},
        ),
    )

    model = models_module.Model("synthetic/deepseek-ai/DeepSeek-V3.1")

    assert model.streaming is False
    assert model.extra_params["custom_llm_provider"] == "synthetic"


def test_json_provider_hf_namespace_normalization():
    provider = object.__new__(_JSONOpenAIProvider)
    provider.slug = "synthetic"
    provider.config = {"hf_namespace": True}

    rewritten = provider._normalize_model_name("synthetic/deepseek-ai/DeepSeek-V3.1")
    assert rewritten == "hf:deepseek-ai/DeepSeek-V3.1"

    unchanged = provider._normalize_model_name("hf:deepseek-ai/DeepSeek-V3.1")
    assert unchanged == "hf:deepseek-ai/DeepSeek-V3.1"
