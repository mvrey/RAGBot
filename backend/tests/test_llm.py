import pytest

from ragbot.core import LLM


@pytest.fixture
def clean_env(monkeypatch):
    for var in ('LLM_MODEL', 'GOOGLE_API_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY'):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


class TestModelSelection:

    def test_defaults_to_gemini_flash(self, clean_env):
        assert LLM.get_model_name() == 'google-gla:gemini-2.5-flash'

    def test_env_overrides_the_default(self, clean_env):
        clean_env.setenv('LLM_MODEL', 'openai:gpt-4.1-nano')

        assert LLM.get_model_name() == 'openai:gpt-4.1-nano'

    def test_blank_env_falls_back_to_default(self, clean_env):
        clean_env.setenv('LLM_MODEL', '   ')

        assert LLM.get_model_name() == LLM.DEFAULT_MODEL


class TestApiKeyResolution:

    @pytest.mark.parametrize("model,expected", [
        ('google-gla:gemini-3.5-flash', 'GOOGLE_API_KEY'),
        ('google-gla:gemini-3.7-flash', 'GOOGLE_API_KEY'),
        ('google-vertex:gemini-3.5-flash', 'GOOGLE_API_KEY'),
        ('openai:gpt-4.1-nano', 'OPENAI_API_KEY'),
        ('anthropic:claude-sonnet-4-5', 'ANTHROPIC_API_KEY'),
    ])
    def test_prefix_maps_to_credential(self, model, expected):
        assert LLM.required_api_key(model) == expected

    def test_bare_model_name_assumes_openai(self):
        # pydantic-ai treats an unprefixed name as OpenAI.
        assert LLM.required_api_key('gpt-4.1-nano') == 'OPENAI_API_KEY'

    def test_unknown_provider_yields_no_key(self):
        assert LLM.required_api_key('somevendor:some-model') == ''

    def test_missing_key_is_reported_by_name(self, clean_env):
        clean_env.setenv('LLM_MODEL', 'google-gla:gemini-2.5-flash')

        assert LLM.missing_api_key() == 'GOOGLE_API_KEY'

    def test_present_key_reports_nothing(self, clean_env):
        clean_env.setenv('LLM_MODEL', 'google-gla:gemini-2.5-flash')
        clean_env.setenv('GOOGLE_API_KEY', 'test-key')

        assert LLM.missing_api_key() == ''

    def test_switching_provider_changes_the_required_key(self, clean_env):
        # Guards the real failure mode: an OpenAI key set, but Gemini configured.
        clean_env.setenv('OPENAI_API_KEY', 'sk-test')
        clean_env.setenv('LLM_MODEL', 'google-gla:gemini-2.5-flash')

        assert LLM.missing_api_key() == 'GOOGLE_API_KEY'


class TestModelStringResolves:

    def test_pydantic_ai_accepts_the_default_model(self, clean_env):
        # Guards against pinning a pydantic-ai that cannot construct this model at
        # all: a missing key must be the only thing standing in the way.
        from pydantic_ai.models import infer_model
        from pydantic_ai.exceptions import UserError

        clean_env.setenv('LLM_MODEL', LLM.DEFAULT_MODEL)

        with pytest.raises(UserError, match='GOOGLE_API_KEY'):
            infer_model(LLM.DEFAULT_MODEL)

    def test_model_resolves_when_a_key_is_present(self, clean_env):
        from pydantic_ai.models import infer_model

        clean_env.setenv('GOOGLE_API_KEY', 'test-key')
        model = infer_model(LLM.DEFAULT_MODEL)

        assert model.model_name == 'gemini-2.5-flash'
        assert model.system == 'google-gla'
