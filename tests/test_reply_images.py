import base64
import io
import json
import socket
import unittest
from unittest.mock import patch

from PIL import Image
from companion.core import Answer, ReplyImage, UserError
from companion.reply_images import (decode_image, download_image, extract_images, generate_image,
                                    normalize_image, public_image_target, resolve_images)


def png():
    result = io.BytesIO()
    Image.new('RGB', (64, 48), '#9bc4d1').save(result, 'PNG')
    return result.getvalue()


def addresses(ip):
    return [(socket.AF_INET6 if ':' in ip else socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 443))]


class ReplyImageTests(unittest.TestCase):
    def test_markdown_images_are_bounded_and_never_executed(self):
        text, images = extract_images('任务说明 ![图](https://example.org/a.png) ' * 5 +
                                      '![无效](file:///tmp/private.png)')
        self.assertEqual(len(images), 1)
        self.assertIsNone(images[0].png)
        self.assertEqual(images[0].url, 'https://example.org/a.png')
        self.assertIn('任务说明', text)
        self.assertIn('file:///tmp/private.png', text)

    def test_private_mixed_and_non_https_addresses_rejected(self):
        for url in ['http://example.org/a.png', 'https://u:p@example.org/a', 'https://example.org:8443/a',
                    'https://example.org/a#fragment', 'https://example.org/a\r\nX: y']:
            with self.subTest(url=url), self.assertRaises(UserError):
                public_image_target(url, resolver=lambda *a, **k: addresses('8.8.8.8'))
        for ip in ['127.0.0.1', '10.0.0.1', '169.254.169.254', '192.168.1.1', '::1', 'fc00::1', '::ffff:127.0.0.1']:
            with self.subTest(ip=ip), self.assertRaises(UserError):
                public_image_target('https://example.org/a', resolver=lambda *a, **k: addresses(ip))
        with self.assertRaises(UserError):
            public_image_target('https://example.org/a', resolver=lambda *a, **k: addresses('8.8.8.8') + addresses('127.0.0.1'))

    def test_redirect_revalidates_without_forwarding_credentials(self):
        requests = []
        class Connection:
            def __init__(self, *args): pass
            def request(self, method, path, headers): requests.append((method, path, headers))
            def getresponse(self):
                class Response:
                    status = 302
                    def getheader(self, name, default=None): return 'https://localhost/private.png'
                return Response()
            def close(self): pass
        def resolver(host, *args, **kwargs):
            return addresses('127.0.0.1' if host == 'localhost' else '8.8.8.8')
        with self.assertRaises(UserError):
            download_image('https://example.org/picture', resolver=resolver, connection_factory=Connection)
        self.assertEqual(len(requests), 1)
        self.assertEqual(set(requests[0][2]), {'User-Agent', 'Accept'})

    def test_image_decoder_rejects_svg_and_preserves_no_metadata(self):
        self.assertTrue(normalize_image(png()).startswith(b'\x89PNG'))
        for raw in [b'<svg/>', b'', b'x' * 8_000_001]:
            with self.assertRaises(UserError): normalize_image(raw)
        with self.assertRaises(UserError): decode_image('not base64')
        image = Image.open(io.BytesIO(normalize_image(png())))
        self.assertEqual(image.info, {})

    def test_failed_picture_does_not_lose_answer(self):
        answer = Answer('文字回答', images=[ReplyImage(None, 'caption', 'https://example.org/a')])
        def fail(url): raise UserError('图片不可用')
        self.assertIs(resolve_images(answer, downloader=fail), answer)
        self.assertEqual(answer.text, '文字回答')
        self.assertIsNone(answer.images[0].png)
        self.assertIn('Image not loaded', answer.warnings[0])

    def test_openai_image_request_is_explicit_and_has_no_search_or_key_in_body(self):
        requests = []
        def transport(req, timeout):
            requests.append(req)
            return io.BytesIO(json.dumps({'data': [{'b64_json': base64.b64encode(png()).decode()}]}).encode())
        result = generate_image('OpenAI', 'fixture-key', 'gpt-image-2.5-flare', '画一张任务流程示意图', transport=transport)
        self.assertTrue(result.images[0].generated)
        request = requests[0]
        self.assertEqual(request.full_url, 'https://api.openai.com/v1/images/generations')
        self.assertEqual(request.get_header('Authorization'), 'Bearer fixture-key')
        body = json.loads(request.data)
        self.assertEqual(body['n'], 1)
        self.assertNotIn('fixture-key', str(body))
        self.assertNotIn('tools', body)
        self.assertEqual(len(requests), 1)

    def test_gemini_interactions_only_displays_model_output(self):
        encoded = base64.b64encode(png()).decode()
        data = {'steps': [
            {'type': 'thought', 'content': [{'type': 'text', 'text': 'private thought'}, {'type': 'image', 'data': encoded}]},
            {'type': 'model_output', 'content': [{'type': 'text', 'text': '示意图'}, {'type': 'image', 'data': encoded}]}]}
        requests = []
        def transport(req, timeout):
            requests.append(req)
            return io.BytesIO(json.dumps(data).encode())
        result = generate_image('Gemini', 'fixture-key', 'gemini-nano-banana-2.1', '画任务流程', transport=transport)
        self.assertEqual(result.text, '示意图')
        self.assertEqual(len(result.images), 1)
        self.assertEqual(requests[0].get_header('X-goog-api-key'), 'fixture-key')
        self.assertIsNone(requests[0].get_header('Authorization'))
        self.assertFalse(json.loads(requests[0].data)['store'])
        self.assertEqual(requests[0].full_url, 'https://generativelanguage.googleapis.com/v1beta/interactions')

    def test_unsupported_and_empty_generation_never_retries(self):
        with self.assertRaises(UserError):
            generate_image('Claude', 'fixture', 'model', 'p', transport=lambda *a, **k: self.fail('network forbidden'))
        with self.assertRaisesRegex(UserError, 'returned no image'):
            generate_image('OpenAI', 'fixture', 'model', 'p', transport=lambda *a, **k: io.BytesIO(b'{"data": []}'))
