import os
import unittest
from unittest.mock import patch

import requests

import llm_client


class LLMClientTests(unittest.TestCase):
    def setUp(self):
        self.env_patch = patch.dict(os.environ, {}, clear=True)
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()

    @patch('llm_client.requests.post')
    def test_ollama_generate_text(self, mock_post):
        os.environ['LLM_PROVIDER'] = 'ollama'
        os.environ['OLLAMA_HOST'] = 'http://localhost:11434'
        os.environ['OLLAMA_MODEL'] = 'qwen3:8b'

        mock_response = unittest.mock.Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {'response': 'GPT-4o'}
        mock_post.return_value = mock_response

        result = llm_client.generate_text('Normalize this model', max_tokens=20)

        self.assertEqual(result, 'GPT-4o')
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], 'http://localhost:11434/api/generate')
        self.assertEqual(kwargs['json']['model'], 'qwen3:8b')
        self.assertEqual(kwargs['json']['prompt'], 'Normalize this model')
        self.assertEqual(kwargs['json']['options']['num_predict'], 20)

    @patch('llm_client.requests.post')
    def test_xai_generate_text(self, mock_post):
        os.environ['LLM_PROVIDER'] = 'xai'
        os.environ['XAI_API_KEY'] = 'test-key'
        os.environ['XAI_MODEL'] = 'grok-4.20-0309-non-reasoning'
        os.environ['XAI_API_BASE'] = 'https://api.x.ai/v1'

        mock_response = unittest.mock.Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            'choices': [{'message': {'content': 'MODEL_RELEASE'}}]
        }
        mock_post.return_value = mock_response

        result = llm_client.generate_text('Classify this item', max_tokens=20)

        self.assertEqual(result, 'MODEL_RELEASE')
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], 'https://api.x.ai/v1/chat/completions')
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer test-key')
        self.assertEqual(kwargs['json']['model'], 'grok-4.20-0309-non-reasoning')
        self.assertEqual(kwargs['json']['messages'][0]['content'], 'Classify this item')

    def test_xai_requires_api_key(self):
        os.environ['LLM_PROVIDER'] = 'xai'

        with self.assertRaises(llm_client.LLMConfigurationError):
            llm_client.validate_llm_config()

    @patch('llm_client.time.sleep')
    @patch('llm_client.requests.post')
    def test_retries_on_rate_limit(self, mock_post, mock_sleep):
        os.environ['LLM_PROVIDER'] = 'xai'
        os.environ['XAI_API_KEY'] = 'test-key'

        rate_limited = unittest.mock.Mock(status_code=429)
        rate_limited.raise_for_status.side_effect = requests.HTTPError(response=rate_limited)

        success = unittest.mock.Mock()
        success.raise_for_status.return_value = None
        success.json.return_value = {'choices': [{'message': {'content': 'ok'}}]}

        mock_post.side_effect = [rate_limited, success]

        result = llm_client.generate_text('retry me')

        self.assertEqual(result, 'ok')
        self.assertEqual(mock_post.call_count, 2)
        mock_sleep.assert_called_once_with(1)

    @patch('llm_client.time.sleep')
    @patch('llm_client.requests.post')
    def test_returns_none_after_persistent_failure(self, mock_post, mock_sleep):
        os.environ['LLM_PROVIDER'] = 'ollama'

        failing = unittest.mock.Mock(status_code=500)
        failing.raise_for_status.side_effect = requests.HTTPError(response=failing)
        mock_post.return_value = failing

        result = llm_client.generate_text('fail me')

        self.assertIsNone(result)
        self.assertEqual(mock_post.call_count, 3)


if __name__ == '__main__':
    unittest.main()