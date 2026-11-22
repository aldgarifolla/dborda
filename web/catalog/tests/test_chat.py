"""Чаты помощника: создание, продолжение, чужие чаты, переименование, удаление, оформление ответа."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from catalog.assistant import ollama
from catalog.models import AssistantChat, UserRole
from catalog.templatetags.chat import chat_text

from .test_districts import DISTRICTS


def fake_answer(user, scope, question, planner=None, audit=True, history=None):
    fake_answer.history = history
    return {'question': question, 'text': f'Ответ на «{question}»', 'tables': [], 'calls': [],
            'mode': 'ключевые слова', 'ok': True}


@patch('catalog.views.assistant_answer', side_effect=fake_answer)
@patch('catalog.views.repo.list_districts', return_value=DISTRICTS)
@patch('catalog.views.repo.allowed_codes', return_value={'ОКР-АСТ'})
class ChatViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user('chat_user', password='StrongDemo123!')
        self.other = User.objects.create_user('chat_other', password='StrongDemo123!')
        UserRole.objects.create(user=self.user, role='viewer')
        self.client.force_login(self.user)

    def test_first_question_creates_chat_with_title(self, *_):
        response = self.client.post(reverse('assistant'), {'question': 'Сколько людей в округе Юг?'})
        chat = AssistantChat.objects.get(user=self.user)
        self.assertRedirects(response, reverse('assistant_chat', args=[chat.pk]))
        self.assertEqual(chat.title, 'Сколько людей в округе Юг?')
        page = self.client.get(response.url).content.decode()
        self.assertIn('Ответ на «Сколько людей в округе Юг?»', page)
        self.assertIn('nav-chat-row active', page)

    def test_follow_up_gets_history(self, *_):
        self.client.post(reverse('assistant'), {'question': 'Сколько людей в округе Юг?'})
        chat = AssistantChat.objects.get(user=self.user)
        self.client.post(reverse('assistant_chat', args=[chat.pk]), {'question': 'а на Востоке?'})
        self.assertEqual(fake_answer.history, [('Сколько людей в округе Юг?', 'Ответ на «Сколько людей в округе Юг?»')])
        self.assertEqual(chat.messages.count(), 2)
        self.assertEqual(AssistantChat.objects.count(), 1)

    def test_fetch_returns_json_with_message_html(self, *_):
        response = self.client.post(reverse('assistant'), {'question': 'Привет'}, HTTP_X_REQUESTED_WITH='fetch')
        data = response.json()
        self.assertTrue(data['created'])
        self.assertIn('Ответ на «Привет»', data['html'])
        self.assertEqual(data['url'], reverse('assistant_chat', args=[data['chat_id']]))

    def test_empty_question_is_rejected(self, *_):
        response = self.client.post(reverse('assistant'), {'question': '  '}, HTTP_X_REQUESTED_WITH='fetch')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(AssistantChat.objects.exists())

    def test_other_users_chat_is_404(self, *_):
        chat = AssistantChat.objects.create(user=self.other, title='Чужой')
        self.assertEqual(self.client.get(reverse('assistant_chat', args=[chat.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('assistant_chat', args=[chat.pk]), {'question': 'x'}).status_code, 404)
        self.assertEqual(self.client.post(reverse('assistant_delete', args=[chat.pk])).status_code, 404)
        self.assertTrue(AssistantChat.objects.filter(pk=chat.pk).exists())
        self.assertNotIn('Чужой', self.client.get(reverse('assistant')).content.decode())

    def test_rename_and_delete(self, *_):
        chat = AssistantChat.objects.create(user=self.user, title='Старое')
        self.client.post(reverse('assistant_rename', args=[chat.pk]), {'title': '  Новое   название '})
        chat.refresh_from_db()
        self.assertEqual(chat.title, 'Новое название')
        self.assertRedirects(self.client.post(reverse('assistant_delete', args=[chat.pk])), reverse('assistant'))
        self.assertFalse(AssistantChat.objects.filter(pk=chat.pk).exists())

    def test_long_title_is_shortened(self, *_):
        self.client.post(reverse('assistant'), {'question': 'Сколько ' * 20})
        self.assertLessEqual(len(AssistantChat.objects.get().title), 60)


class ChatTextTests(SimpleTestCase):
    def test_bold_list_and_escaping(self):
        html = chat_text('**Итого:** 62 танка\n- Т-72Б — 54\n- Т-72К — 8\n<script>x</script>')
        self.assertIn('<strong>Итого:</strong>', html)
        self.assertIn('<ul><li>Т-72Б — 54</li><li>Т-72К — 8</li></ul>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertNotIn('<script>', html)


class PlannerHistoryTests(SimpleTestCase):
    @patch.object(ollama.OllamaPlanner, '_chat', return_value={'content': 'Здравствуйте', 'tool_calls': []})
    def test_history_goes_before_question(self, chat):
        planner = ollama.OllamaPlanner()
        planner.history = [('Сколько людей в округе Юг?', 'В округе «Юг» 4061 человек.')]
        planner.plan('а на Востоке?', DISTRICTS)
        sent = chat.call_args.args[0]
        self.assertEqual([m['role'] for m in sent], ['system', 'user', 'assistant', 'user'])
        self.assertEqual(sent[1]['content'], 'Сколько людей в округе Юг?')
        self.assertTrue(sent[3]['content'].startswith('а на Востоке?'))

    @patch.object(ollama.OllamaPlanner, '_chat', return_value={'content': 'В округе «Восток» 2987 человек.'})
    def test_history_in_answer_step(self, chat):
        planner = ollama.OllamaPlanner()
        planner.history = [('Сколько людей в округе Юг?', 'В округе «Юг» 4061 человек.')]
        planner.compose('а на Востоке?', [{'title': 'T', 'headers': ['a'], 'rows': [[1]], 'note': ''}])
        content = chat.call_args.args[0][1]['content']
        self.assertIn('Предыдущий вопрос в этом чате (только чтобы понять текущий): Сколько людей в округе Юг?', content)
        self.assertNotIn('4061', content)

    @patch.object(ollama.OllamaPlanner, '_chat', return_value={'content': 'Ок.', 'tool_calls': []})
    def test_no_history_no_extra_messages(self, chat):
        ollama.OllamaPlanner().plan('Сколько людей?', DISTRICTS)
        self.assertEqual(len(chat.call_args.args[0]), 2)


class FollowUpLanguageTests(SimpleTestCase):
    def test_short_kazakh_follow_up_inherits_language(self):
        history = [('Оңтүстік округте қанша адам бар?', 'Оңтүстік округте 4061 адам бар.')]
        self.assertEqual(ollama.question_language('Ал Батыста ше?', history), 'kk')

    def test_russian_follow_up_stays_russian(self):
        history = [('Оңтүстік округте қанша адам бар?', 'Оңтүстік округте 4061 адам бар.')]
        self.assertEqual(ollama.question_language('а на Востоке?', history), 'ru')
        self.assertEqual(ollama.question_language('а в ЮГ-1?', [('Сколько танков в ЮГ-3?', '62')]), 'ru')

    def test_english_follow_up(self):
        self.assertEqual(ollama.question_language('And in the East?', [('Сколько людей на Юге?', '4061')]), 'en')


class AnswerRuleLeakTests(SimpleTestCase):
    def test_answer_rule_line_removed(self):
        text = 'Ответ должен быть на казахском, 1–4 предложения, с указанием округа и единиц.\n\nТанк ОКР-ЗАП бойынша екі түрі бар.'
        self.assertEqual(ollama.strip_meta(text), 'Танк ОКР-ЗАП бойынша екі түрі бар.')


@patch('catalog.views.assistant_answer', side_effect=fake_answer)
@patch('catalog.views.repo.list_districts', return_value=DISTRICTS)
@patch('catalog.views.repo.allowed_codes', return_value={'ОКР-АСТ'})
class ChatTitleTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('title_user', password='StrongDemo123!')
        UserRole.objects.create(user=self.user, role='viewer')
        self.client.force_login(self.user)

    def new_chat(self, question):
        data = self.client.post(reverse('assistant'), {'question': question}, HTTP_X_REQUESTED_WITH='fetch').json()
        self.assertIn('nav-chat-row', data['nav_html'])
        return AssistantChat.objects.get(pk=data['chat_id']), data

    @patch('catalog.views.suggest_title', return_value='Численность Юга')
    def test_model_title_replaces_trimmed_one(self, suggest, *_):
        chat, data = self.new_chat('Скажи пожалуйста, сколько всего людей служит в округе Юг сейчас?')
        self.assertLessEqual(len(chat.title), 40)
        self.assertTrue(chat.title.endswith('…'))
        self.assertEqual(self.client.post(data['title_url']).json()['title'], 'Численность Юга')
        chat.refresh_from_db()
        self.assertEqual(chat.title, 'Численность Юга')

    @patch('catalog.views.suggest_title', return_value='Другое')
    def test_renamed_chat_keeps_users_title(self, suggest, *_):
        chat, data = self.new_chat('Сколько людей в округе Юг?')
        self.client.post(reverse('assistant_rename', args=[chat.pk]), {'title': 'Мой чат'})
        self.assertEqual(self.client.post(data['title_url']).json()['title'], 'Мой чат')
        suggest.assert_not_called()

    @patch('catalog.views.suggest_title', return_value=None)
    def test_no_model_keeps_trimmed_title(self, suggest, *_):
        chat, data = self.new_chat('Сколько людей в округе Юг?')
        self.assertEqual(self.client.post(data['title_url']).json()['title'], 'Сколько людей в округе Юг?')

    def test_rename_via_fetch_and_delete_other_chat_stays_on_current(self, *_):
        first, _ = self.new_chat('Первый')
        second, _ = self.new_chat('Второй')
        self.assertEqual(self.client.post(reverse('assistant_rename', args=[first.pk]), {'title': 'Новое'},
                                          HTTP_X_REQUESTED_WITH='fetch').json()['title'], 'Новое')
        response = self.client.post(reverse('assistant_delete', args=[first.pk]), {'current': str(second.pk)})
        self.assertRedirects(response, reverse('assistant_chat', args=[second.pk]))

    def test_sidebar_has_menu_for_each_chat(self, *_):
        chat, _ = self.new_chat('Первый')
        page = self.client.get(reverse('assistant_chat', args=[chat.pk])).content.decode()
        self.assertIn('nav-chat-row active', page)
        self.assertIn(reverse('assistant_rename', args=[chat.pk]), page)
        self.assertIn(reverse('assistant_delete', args=[chat.pk]), page)


class ChatTitleTrimTests(SimpleTestCase):
    def test_trim_by_word(self):
        from catalog.views import chat_title
        self.assertEqual(chat_title('здравствуй! готов к работе?'), 'здравствуй! готов к работе?')
        title = chat_title('Сколько всего людей служит в учебном округе Юг на сегодняшний день?')
        self.assertLessEqual(len(title), 40)
        self.assertTrue(title.endswith('…'))
        self.assertFalse(title[:-1].endswith(' '))


class ClaudeTitleTests(SimpleTestCase):
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('catalog.assistant.claude.anthropic.Anthropic')
    def test_title_is_cleaned(self, client_cls):
        from types import SimpleNamespace
        from catalog.assistant.claude import ClaudePlanner
        usage = SimpleNamespace(input_tokens=90, output_tokens=6, cache_creation_input_tokens=0, cache_read_input_tokens=0)
        client_cls.return_value.messages.create.return_value = SimpleNamespace(
            stop_reason='end_turn', usage=usage, content=[SimpleNamespace(type='text', text='«Численность Юга».\nлишнее')])
        planner = ClaudePlanner()
        self.assertEqual(planner.title('Сколько людей на Юге?', '4061'), 'Численность Юга')
        kwargs = client_cls.return_value.messages.create.call_args.kwargs
        self.assertEqual(kwargs['thinking'], {'type': 'disabled'})
        self.assertNotIn('tools', kwargs)
