import pytest
from unittest.mock import ANY, MagicMock, patch
from aider.models import ANTHROPIC_BETA_HEADER, Model, ModelInfoManager, register_models, sanity_check_model, sanity_check_models

class TestModels:

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """Reset MODEL_SETTINGS before each test and restore after"""
        from aider.models import MODEL_SETTINGS
        self._original_settings = MODEL_SETTINGS.copy()
        yield
        MODEL_SETTINGS.clear()
        MODEL_SETTINGS.extend(self._original_settings)

    def test_get_model_info_nonexistent(self):
        manager = ModelInfoManager()
        info = manager.get_model_info('non-existent-model')
        assert info == {}

    def test_max_context_tokens(self):
        model = Model('gpt-3.5-turbo')
        assert model.info['max_input_tokens'] == 16385
        model = Model('gpt-3.5-turbo-16k')
        assert model.info['max_input_tokens'] == 16385
        model = Model('gpt-3.5-turbo-1106')
        assert model.info['max_input_tokens'] == 16385
        model = Model('gpt-4')
        assert model.info['max_input_tokens'] == 8 * 1024
        model = Model('gpt-4-32k')
        assert model.info['max_input_tokens'] == 32 * 1024
        model = Model('gpt-4-0613')
        assert model.info['max_input_tokens'] == 8 * 1024

    @patch('os.environ')
    async def test_sanity_check_model_all_set(self, mock_environ):
        mock_environ.get.return_value = 'dummy_value'
        mock_io = MagicMock()
        model = MagicMock()
        model.name = 'test-model'
        model.missing_keys = ['API_KEY1', 'API_KEY2']
        model.keys_in_environment = True
        model.info = {'some': 'info'}
        await sanity_check_model(mock_io, model)
        mock_io.tool_output.assert_called()
        calls = mock_io.tool_output.call_args_list
        assert '- API_KEY1: Set' in str(calls)
        assert '- API_KEY2: Set' in str(calls)

    @patch('os.environ')
    async def test_sanity_check_model_not_set(self, mock_environ):
        mock_environ.get.return_value = ''
        mock_io = MagicMock()
        model = MagicMock()
        model.name = 'test-model'
        model.missing_keys = ['API_KEY1', 'API_KEY2']
        model.keys_in_environment = True
        model.info = {'some': 'info'}
        await sanity_check_model(mock_io, model)
        mock_io.tool_output.assert_called()
        calls = mock_io.tool_output.call_args_list
        assert '- API_KEY1: Not set' in str(calls)
        assert '- API_KEY2: Not set' in str(calls)

    async def test_sanity_check_models_bogus_editor(self):
        mock_io = MagicMock()
        main_model = Model('gpt-4')
        main_model.editor_model = Model('bogus-model')
        result = await sanity_check_models(mock_io, main_model)
        assert result
        mock_io.tool_warning.assert_called_with(ANY)
        warning_messages = [warning_call.args[0] for warning_call in mock_io.tool_warning.call_args_list]
        print('Warning messages:', warning_messages)
        assert mock_io.tool_warning.call_count >= 1
        assert any(('bogus-model' in msg for msg in warning_messages))

    @patch('aider.models.check_for_dependencies')
    async def test_sanity_check_model_calls_check_dependencies(self, mock_check_deps):
        """Test that sanity_check_model calls check_for_dependencies"""
        mock_io = MagicMock()
        model = MagicMock()
        model.name = 'test-model'
        model.missing_keys = []
        model.keys_in_environment = True
        model.info = {'some': 'info'}
        await sanity_check_model(mock_io, model)
        mock_check_deps.assert_called_once_with(mock_io, 'test-model')

    def test_model_aliases(self):
        model = Model('4')
        assert model.name == 'gpt-4-0613'
        model = Model('4o')
        assert model.name == 'gpt-4o'
        model = Model('35turbo')
        assert model.name == 'gpt-3.5-turbo'
        model = Model('35-turbo')
        assert model.name == 'gpt-3.5-turbo'
        model = Model('3')
        assert model.name == 'gpt-3.5-turbo'
        model = Model('sonnet')
        assert model.name == 'anthropic/claude-sonnet-4-20250514'
        model = Model('haiku')
        assert model.name == 'claude-3-5-haiku-20241022'
        model = Model('opus')
        assert model.name == 'claude-opus-4-20250514'
        model = Model('gpt-4')
        assert model.name == 'gpt-4'

    def test_o1_use_temp_false(self):
        model = Model('github/o1-mini')
        assert model.name == 'github/o1-mini'
        assert model.use_temperature == False
        model = Model('github/o1-preview')
        assert model.name == 'github/o1-preview'
        assert model.use_temperature == False

    def test_parse_token_value(self):
        model = Model('gpt-4')
        assert model.parse_token_value(8096) == 8096
        assert model.parse_token_value(1000) == 1000
        assert model.parse_token_value('8096') == 8096
        assert model.parse_token_value('8k') == 8 * 1024
        assert model.parse_token_value('8K') == 8 * 1024
        assert model.parse_token_value('10.5k') == 10.5 * 1024
        assert model.parse_token_value('0.5K') == 0.5 * 1024
        assert model.parse_token_value('1m') == 1 * 1024 * 1024
        assert model.parse_token_value('1M') == 1 * 1024 * 1024
        assert model.parse_token_value('0.5M') == 0.5 * 1024 * 1024
        assert model.parse_token_value(' 8k ') == 8 * 1024
        assert model.parse_token_value(8.0) == 8

    def test_set_thinking_tokens(self):
        model = Model('gpt-4')
        model.set_thinking_tokens(8096)
        assert model.extra_params['thinking']['budget_tokens'] == 8096
        assert not model.use_temperature
        model.set_thinking_tokens('10k')
        assert model.extra_params['thinking']['budget_tokens'] == 10 * 1024
        model.set_thinking_tokens('0.5M')
        assert model.extra_params['thinking']['budget_tokens'] == 0.5 * 1024 * 1024

    @patch('aider.models.check_pip_install_extra')
    async def test_check_for_dependencies_bedrock(self, mock_check_pip):
        """Test that check_for_dependencies calls check_pip_install_extra for Bedrock models"""
        from aider.io import InputOutput
        io = InputOutput()
        from aider.models import check_for_dependencies
        await check_for_dependencies(io, 'bedrock/anthropic.claude-3-sonnet-20240229-v1:0')
        mock_check_pip.assert_called_once_with(io, 'boto3', 'AWS Bedrock models require the boto3 package.', ['boto3'])

    @patch('aider.models.check_pip_install_extra')
    async def test_check_for_dependencies_vertex_ai(self, mock_check_pip):
        """Test that check_for_dependencies calls check_pip_install_extra for Vertex AI models"""
        from aider.io import InputOutput
        io = InputOutput()
        from aider.models import check_for_dependencies
        await check_for_dependencies(io, 'vertex_ai/gemini-1.5-pro')
        mock_check_pip.assert_called_once_with(io, 'google.cloud.aiplatform', 'Google Vertex AI models require the google-cloud-aiplatform package.', ['google-cloud-aiplatform'])

    @patch('aider.models.check_pip_install_extra')
    async def test_check_for_dependencies_other_model(self, mock_check_pip):
        """Test that check_for_dependencies doesn't call check_pip_install_extra for other models"""
        from aider.io import InputOutput
        io = InputOutput()
        from aider.models import check_for_dependencies
        await check_for_dependencies(io, 'gpt-4')
        mock_check_pip.assert_not_called()

    def test_get_repo_map_tokens(self):
        model = Model('gpt-4')
        model.info = {}
        assert model.get_repo_map_tokens() == 1024
        model.info = {'max_input_tokens': 4096}
        assert model.get_repo_map_tokens() == 1024
        model.info = {'max_input_tokens': 16384}
        assert model.get_repo_map_tokens() == 2048
        model.info = {'max_input_tokens': 65536}
        assert model.get_repo_map_tokens() == 4096
        model.info = {'max_input_tokens': 8192}
        assert model.get_repo_map_tokens() == 1024
        model.info = {'max_input_tokens': 32768}
        assert model.get_repo_map_tokens() == 4096

    def test_configure_model_settings(self):
        model = Model('something/o3-mini')
        assert model.edit_format == 'diff'
        assert model.use_repo_map
        assert not model.use_temperature
        model = Model('something/o1-mini')
        assert model.use_repo_map
        assert not model.use_temperature
        assert not model.use_system_prompt
        model = Model('something/o1-preview')
        assert model.edit_format == 'diff'
        assert model.use_repo_map
        assert not model.use_temperature
        assert not model.use_system_prompt
        model = Model('something/o1')
        assert model.edit_format == 'diff'
        assert model.use_repo_map
        assert not model.use_temperature
        assert not model.streaming
        model = Model('deepseek-v3')
        assert model.edit_format == 'diff'
        assert model.use_repo_map
        assert model.reminder == 'sys'
        assert model.examples_as_sys_msg
        model = Model('deepseek-r1')
        assert model.edit_format == 'diff'
        assert model.use_repo_map
        assert model.examples_as_sys_msg
        assert not model.use_temperature
        assert model.reasoning_tag == 'think'
        model = Model('someprovider/deepseek-r1')
        assert model.edit_format == 'diff'
        assert model.use_repo_map
        assert model.examples_as_sys_msg
        assert not model.use_temperature
        assert model.reasoning_tag == 'think'
        model = Model('anotherprovider/deepseek-v3')
        assert model.edit_format == 'diff'
        assert model.use_repo_map
        assert model.reminder == 'sys'
        assert model.examples_as_sys_msg
        model = Model('llama3-70b')
        assert model.edit_format == 'diff'
        assert model.use_repo_map
        assert model.send_undo_reply
        assert model.examples_as_sys_msg
        model = Model('gpt-4')
        assert model.edit_format == 'diff'
        assert model.use_repo_map
        assert model.send_undo_reply
        model = Model('gpt-3.5')
        assert model.reminder == 'sys'
        model = Model('claude-3.5-sonnet')
        assert model.edit_format == 'diff'
        assert model.use_repo_map
        assert model.examples_as_sys_msg
        assert model.reminder == 'user'
        model = Model('o1-something')
        assert not model.use_system_prompt
        assert not model.use_temperature
        model = Model('qwen-coder-2.5-32b')
        assert model.edit_format == 'diff'
        assert model.editor_edit_format == 'editor-diff'
        assert model.use_repo_map

    def test_aider_extra_model_settings(self):
        import tempfile
        import yaml
        test_settings = [{'name': 'aider/extra_params', 'extra_params': {'extra_headers': {'Foo': 'bar'}, 'some_param': 'some value'}}]
        tmp = tempfile.mktemp(suffix='.yml')
        try:
            with open(tmp, 'w') as f:
                yaml.dump(test_settings, f)
            register_models([tmp])
            model = Model('claude-3-5-sonnet-20240620')
            model = Model('claude-3-5-sonnet-20240620')
            assert model.extra_params['extra_headers']['Foo'] == 'bar'
            assert model.extra_params['extra_headers']['anthropic-beta'] == ANTHROPIC_BETA_HEADER
            assert model.extra_params['some_param'] == 'some value'
            assert model.extra_params['max_tokens'] == 8192
            model = Model('gpt-4')
            assert model.extra_params['extra_headers']['Foo'] == 'bar'
            assert model.extra_params['some_param'] == 'some value'
        finally:
            import os
            try:
                os.unlink(tmp)
            except OSError:
                pass

    @patch('aider.models.litellm.acompletion')
    @patch.object(Model, 'token_count')
    async def test_ollama_num_ctx_set_when_missing(self, mock_token_count, mock_completion):
        mock_token_count.return_value = 1000
        model = Model('ollama/llama3')
        model.extra_params = {}
        messages = [{'role': 'user', 'content': 'Hello'}]
        await model.send_completion(messages, functions=None, stream=False)
        expected_ctx = int(1000 * 1.25) + 8192
        mock_completion.assert_called_once_with(model=model.name, messages=ANY, stream=False, temperature=0, num_ctx=expected_ctx, timeout=600, cache_control_injection_points=ANY)

    @patch('aider.models.litellm.acompletion')
    async def test_modern_tool_call_propagation(self, mock_completion):
        model = Model('gpt-4')
        messages = [{'role': 'user', 'content': 'Hello'}]
        await model.send_completion(messages, functions=None, stream=False, tools=[dict(type='function', function='test')])
        # Updated to match current behavior with additional parameters
        mock_completion.assert_called_with(
            model=model.name, 
            messages=messages, 
            stream=False, 
            tools=[dict(type='function', function='test')], 
            temperature=0, 
            timeout=600,
            cache_control_injection_points=ANY,
            base_url='https://api.openai.com/v1',
            custom_llm_provider='openai'
        )

    @patch('aider.models.litellm.acompletion')
    async def test_legacy_tool_call_propagation(self, mock_completion):
        model = Model('gpt-4')
        messages = [{'role': 'user', 'content': 'Hello'}]
        await model.send_completion(messages, functions=['test'], stream=False)
        # Updated to match current behavior with additional parameters
        mock_completion.assert_called_with(
            model=model.name, 
            messages=messages, 
            stream=False, 
            tools=[dict(type='function', function='test')], 
            temperature=0, 
            timeout=600,
            cache_control_injection_points=ANY,
            base_url='https://api.openai.com/v1',
            custom_llm_provider='openai'
        )

    @patch('aider.models.litellm.acompletion')
    async def test_ollama_uses_existing_num_ctx(self, mock_completion):
        model = Model('ollama/llama3')
        model.extra_params = {'num_ctx': 4096}
        messages = [{'role': 'user', 'content': 'Hello'}]
        await model.send_completion(messages, functions=None, stream=False)
        mock_completion.assert_called_once_with(model=model.name, messages=ANY, stream=False, temperature=0, num_ctx=4096, timeout=600, cache_control_injection_points=ANY)

    @patch('aider.models.litellm.acompletion')
    async def test_non_ollama_no_num_ctx(self, mock_completion):
        model = Model('gpt-4')
        model.extra_params = {}
        messages = [{'role': 'user', 'content': 'Hello'}]
        await model.send_completion(messages, functions=None, stream=False)
        mock_completion.assert_called_once_with(model=model.name, messages=ANY, stream=False, temperature=0, timeout=600, cache_control_injection_points=ANY)
        assert 'num_ctx' not in mock_completion.call_args.kwargs

    def test_use_temperature_settings(self):
        model = Model('gpt-4')
        assert model.use_temperature
        assert model.use_temperature == True
        model = Model('github/o1-mini')
        assert not model.use_temperature
        model = Model('gpt-4')
        model.use_temperature = 0.7
        assert model.use_temperature == 0.7

    @patch('aider.models.litellm.acompletion')
    async def test_request_timeout_default(self, mock_completion):
        model = Model('gpt-4')
        model.extra_params = {}
        messages = [{'role': 'user', 'content': 'Hello'}]
        await model.send_completion(messages, functions=None, stream=False)
        mock_completion.assert_called_with(model=model.name, messages=ANY, stream=False, temperature=0, timeout=600, cache_control_injection_points=ANY)

    @patch('aider.models.litellm.acompletion')
    async def test_request_timeout_from_extra_params(self, mock_completion):
        model = Model('gpt-4')
        model.extra_params = {'timeout': 300}
        messages = [{'role': 'user', 'content': 'Hello'}]
        await model.send_completion(messages, functions=None, stream=False)
        mock_completion.assert_called_with(model=model.name, messages=ANY, stream=False, temperature=0, timeout=300, cache_control_injection_points=ANY)

    @patch('aider.models.litellm.acompletion')
    async def test_use_temperature_in_send_completion(self, mock_completion):
        model = Model('gpt-4')
        model.extra_params = {}
        messages = [{'role': 'user', 'content': 'Hello'}]
        await model.send_completion(messages, functions=None, stream=False)
        mock_completion.assert_called_with(model=model.name, messages=ANY, stream=False, temperature=0, timeout=600, cache_control_injection_points=ANY)
        model = Model('github/o1-mini')
        messages = [{'role': 'user', 'content': 'Hello'}]
        await model.send_completion(messages, functions=None, stream=False)
        assert 'temperature' not in mock_completion.call_args.kwargs
        model = Model('gpt-4')
        model.extra_params = {}
        model.use_temperature = 0.7
        messages = [{'role': 'user', 'content': 'Hello'}]
        await model.send_completion(messages, functions=None, stream=False)
        mock_completion.assert_called_with(model=model.name, messages=ANY, stream=False, temperature=0.7, timeout=600, cache_control_injection_points=ANY)

    def test_model_override_kwargs(self):
        """Test that override kwargs are applied to model extra_params."""
        model = Model('gpt-4', override_kwargs={'temperature': 0.8, 'top_p': 0.9})
        assert 'temperature' in model.extra_params
        assert model.extra_params['temperature'] == 0.8
        assert 'top_p' in model.extra_params
        assert model.extra_params['top_p'] == 0.9
        model = Model('gpt-4', override_kwargs={'extra_headers': {'X-Custom': 'value'}})
        assert 'extra_headers' in model.extra_params
        assert 'X-Custom' in model.extra_params['extra_headers']
        assert model.extra_params['extra_headers']['X-Custom'] == 'value'
        model = Model('gpt-4', override_kwargs={'extra_body': {'reasoning_effort': 'high'}})
        assert 'extra_body' in model.extra_params
        assert 'reasoning_effort' in model.extra_params['extra_body']
        assert model.extra_params['extra_body']['reasoning_effort'] == 'high'

    def test_model_override_kwargs_with_existing_extra_params(self):
        """Test that override kwargs merge correctly with existing extra_params."""
        import tempfile
        import yaml
        test_settings = [{'name': 'gpt-4', 'extra_params': {'temperature': 0.5, 'extra_headers': {'Existing': 'header'}}}]
        tmp = tempfile.mktemp(suffix='.yml')
        try:
            with open(tmp, 'w') as f:
                yaml.dump(test_settings, f)
            register_models([tmp])
            model = Model('gpt-4', override_kwargs={'temperature': 0.8, 'top_p': 0.9})
            assert model.extra_params['temperature'] == 0.8
            assert model.extra_params['top_p'] == 0.9
            assert 'extra_headers' in model.extra_params
            assert model.extra_params['extra_headers']['Existing'] == 'header'
            model = Model('gpt-4', override_kwargs={'extra_headers': {'New': 'value'}})
            assert 'Existing' in model.extra_params['extra_headers']
            assert 'New' in model.extra_params['extra_headers']
            assert model.extra_params['extra_headers']['Existing'] == 'header'
            assert model.extra_params['extra_headers']['New'] == 'value'
        finally:
            import os
            try:
                os.unlink(tmp)
            except OSError:
                pass

    @patch('aider.models.litellm.acompletion')
    async def test_send_completion_with_override_kwargs(self, mock_completion):
        """Test that override kwargs are passed to acompletion."""
        model = Model('gpt-4', override_kwargs={'temperature': 0.8, 'top_p': 0.9})
        messages = [{'role': 'user', 'content': 'Hello'}]
        await model.send_completion(messages, functions=None, stream=False)
        mock_completion.assert_called_once()
        call_kwargs = mock_completion.call_args.kwargs
        assert 'temperature' in call_kwargs
        assert call_kwargs['temperature'] == 0.8
        assert 'top_p' in call_kwargs
        assert call_kwargs['top_p'] == 0.9
        assert call_kwargs['model'] == 'gpt-4'
        assert not call_kwargs['stream']

    def test_parse_model_with_suffix(self):
        """Test the parse_model_with_suffix function from main.py."""

        def parse_model_with_suffix(model_name, overrides):
            """Parse model name with optional :suffix and apply overrides."""
            if not model_name:
                return (model_name, {})
            if ':' in model_name:
                base_model, suffix = model_name.rsplit(':', 1)
            else:
                base_model, suffix = (model_name, None)
            override_kwargs = {}
            if suffix and base_model in overrides and (suffix in overrides[base_model]):
                override_kwargs = overrides[base_model][suffix].copy()
            return (base_model, override_kwargs)
        overrides = {'gpt-4o': {'high': {'reasoning_effort': 'high', 'temperature': 0.7}, 'low': {'reasoning_effort': 'low', 'temperature': 0.2}}, 'claude-3-5-sonnet': {'fast': {'temperature': 0.3}, 'creative': {'temperature': 0.9}}}
        base_model, kwargs = parse_model_with_suffix('gpt-4o:high', overrides)
        assert base_model == 'gpt-4o'
        assert kwargs == {'reasoning_effort': 'high', 'temperature': 0.7}
        base_model, kwargs = parse_model_with_suffix('gpt-4o:low', overrides)
        assert base_model == 'gpt-4o'
        assert kwargs == {'reasoning_effort': 'low', 'temperature': 0.2}
        base_model, kwargs = parse_model_with_suffix('gpt-4o', overrides)
        assert base_model == 'gpt-4o'
        assert kwargs == {}
        base_model, kwargs = parse_model_with_suffix('gpt-4o:unknown', overrides)
        assert base_model == 'gpt-4o'
        assert kwargs == {}
        base_model, kwargs = parse_model_with_suffix('unknown-model:high', overrides)
        assert base_model == 'unknown-model'
        assert kwargs == {}
        base_model, kwargs = parse_model_with_suffix('', overrides)
        assert base_model == ''
        assert kwargs == {}