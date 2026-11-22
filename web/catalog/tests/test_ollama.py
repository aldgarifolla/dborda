"""Планировщик на локальной модели: ответы Ollama подменены, сеть и PostgreSQL не нужны."""
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings

from catalog.assistant import answer, ollama
from catalog.models import AssistantAudit

from .test_districts import DISTRICTS, SCOPE

PROVIDER = 'catalog.assistant.ollama.OllamaPlanner'


def tool_msg(*calls):
    return {'role': 'assistant', 'content': '',
            'tool_calls': [{'function': {'name': n, 'arguments': a}} for n, a in calls]}


class CleanArgsTests(SimpleTestCase):
    def test_extra_and_empty_keys_dropped(self):
        self.assertEqual(ollama._clean_args('district_supply',
                                            {'district': 'ОКР-ВОС', 'category': '', 'foo': 1, 'only_deficit': 'true'}),
                         {'district': 'ОКР-ВОС', 'only_deficit': True})

    def test_unknown_tool_gets_no_args(self):
        self.assertEqual(ollama._clean_args('run_sql', {'sql': 'select 1'}), {})

    def test_json_string_arguments(self):
        self.assertEqual(ollama._clean_args('district_summary', '{"district": "ОКР-АСТ"}'), {'district': 'ОКР-АСТ'})


@override_settings(ASSISTANT_PROVIDER=PROVIDER)
@patch('catalog.assistant.engine.repo.list_districts', return_value=DISTRICTS)
@patch('catalog.assistant.tools.repo.list_districts', return_value=DISTRICTS)
@patch('catalog.assistant.tools.repo.compare', return_value=[
    {'district_code': 'ОКР-ЮГ', 'short_name': 'Округ «Юг»', 'side': 'свои', 'value': 10905},
    {'district_code': 'ОКР-ВОС', 'short_name': 'Округ «Восток»', 'side': 'свои', 'value': 8444}])
class OllamaEngineTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('example_viewer', password='StrongDemo123!')

    @patch.object(ollama.OllamaPlanner, '_chat')
    def test_model_picks_tool_and_writes_answer(self, chat, *_):
        chat.side_effect = [tool_msg(('compare_districts', {'metric': 'personnel'})),
                            {'role': 'assistant', 'content': 'Больше всего людей в Округ «Юг» — 10905.'}]
        result = answer(self.user, SCOPE, 'где больше всего людей?')
        self.assertTrue(result['mode'].startswith('ИИ'))
        self.assertEqual(result['text'], 'Больше всего людей в Округ «Юг» — 10905.')
        self.assertEqual(result['calls'][0]['tool'], 'compare_districts')
        self.assertIn('10905', chat.call_args_list[1].args[0][1]['content'])   # таблица ушла модели
        self.assertEqual(AssistantAudit.objects.get().mode, result['mode'])

    @patch.object(ollama.OllamaPlanner, '_chat')
    def test_foreign_district_is_refused_by_tool(self, chat, *_):
        chat.side_effect = [tool_msg(('district_summary', {'district': 'ОКР-ЗАП'}))]
        result = answer(self.user, SCOPE, 'численность Запада')
        self.assertFalse(result['ok'])
        self.assertEqual(result['tables'], [])
        self.assertIn('недоступен', result['text'])

    @patch.object(ollama.OllamaPlanner, '_chat')
    def test_small_talk_without_tools(self, chat, *_):
        chat.side_effect = [{'role': 'assistant', 'content': 'Здравствуйте! Спросите про округа.'}]
        result = answer(self.user, SCOPE, 'привет')
        self.assertEqual(result['text'], 'Здравствуйте! Спросите про округа.')
        self.assertEqual(chat.call_count, 1)

    @patch.object(ollama.OllamaPlanner, '_chat', side_effect=ollama.ModelUnavailable('connection refused'))
    def test_falls_back_to_keywords_when_model_down(self, chat, *_):
        result = answer(self.user, SCOPE, 'сравни округа по численности')
        self.assertEqual(result['mode'], 'ключевые слова')
        self.assertEqual(result['calls'][0]['tool'], 'compare_districts')

    @patch.object(ollama.OllamaPlanner, '_chat')
    def test_answer_step_failure_keeps_tables(self, chat, *_):
        chat.side_effect = [tool_msg(('compare_districts', {'metric': 'personnel'})),
                            ollama.ModelUnavailable('timeout')]
        result = answer(self.user, SCOPE, 'сравни численность')
        self.assertEqual(len(result['tables']), 1)
        self.assertIn('Найдено по вашему вопросу', result['text'])


class MentionedDistrictsTests(SimpleTestCase):
    def test_kazakh_names(self):
        districts = DISTRICTS + [{'district_code': 'ОКР-ЗАП', 'short_name': 'Округ «Запад»'}]
        self.assertEqual(ollama.mentioned_districts('Батыста қанша адам бар?', districts), ['ОКР-ЗАП'])
        self.assertEqual(ollama.mentioned_districts('Шығыста қанша танк бар?', districts), ['ОКР-ВОС'])
        self.assertEqual(ollama.mentioned_districts('Оңтүстікте қанша адам?', districts), ['ОКР-ЮГ'])

    def test_russian_forms(self):
        self.assertEqual(ollama.mentioned_districts('Сколько людей на Востоке?', DISTRICTS), ['ОКР-ВОС'])


class ToolTotalsTests(SimpleTestCase):
    @patch('catalog.assistant.tools.repo.compare', return_value=[
        {'district_code': 'ОКР-ЮГ', 'short_name': 'Округ «Юг»', 'value': 10905},
        {'district_code': 'ОКР-АСТ', 'short_name': 'Округ «Астана»', 'value': 8092},
        {'district_code': 'ОКР-ВОС', 'short_name': 'Округ «Восток»', 'value': 8444}])
    def test_compare_note_has_max_and_min(self, compare):
        from catalog.assistant import tools
        note = tools.run('compare_districts', {'metric': 'personnel'}, SCOPE)['note']
        self.assertIn('Больше всего: Округ «Юг» — 10905', note)
        self.assertIn('Меньше всего: Округ «Астана» — 8092', note)

    @patch('catalog.assistant.tools.repo.formations', return_value=[
        {'formation_code': 'ВОС-1', 'formation_name': 'А', 'formation_type': 'x', 'battalions': 3, 'companies': 9, 'platoons': 27, 'squads': 81},
        {'formation_code': 'ВОС-2', 'formation_name': 'Б', 'formation_type': 'x', 'battalions': 3, 'companies': 9, 'platoons': 27, 'squads': 81}])
    def test_formations_total_row(self, formations):
        from catalog.assistant import tools
        last = tools.run('district_formations', {'district': 'ОКР-ВОС'}, SCOPE)['rows'][-1]
        self.assertEqual(last[1], 'Итого по округу')
        self.assertEqual(last[3:], [6, 18, 54, 162])


class UnitCodeTests(SimpleTestCase):
    def test_battalion_follows_company_number(self):
        from catalog.assistant.tools import normalize_unit_code as n
        self.assertEqual(n('ВОС-1.Б2.Р8'), 'ВОС-1.Б3.Р8')
        self.assertEqual(n('вос-1.р8.в2'), 'ВОС-1.Б3.Р8.В2')
        self.assertEqual(n('ЮГ-4.Б1.Р1.В3.О2'), 'ЮГ-4.Б1.Р1.В3.О2')
        self.assertEqual(n('ВОС-1'), 'ВОС-1')

    def test_code_from_numbers(self):
        from catalog.assistant.tools import unit_code_from_numbers as f
        self.assertEqual(f('ВОС-1', company=8), 'ВОС-1.Б3.Р8')
        self.assertEqual(f('ВОС-1', battalion=3, company=2), 'ВОС-1.Б3.Р8')
        self.assertEqual(f('ЮГ-4', battalion=1, company=1, platoon=3), 'ЮГ-4.Б1.Р1.В3')
        self.assertEqual(f('ВОС-1', squad=2), 'ВОС-1.Б1.Р1.В1.О2')
        self.assertEqual(f('ЗАП-3'), 'ЗАП-3')


@override_settings(ASSISTANT_PROVIDER=PROVIDER)
class ForeignScriptTests(SimpleTestCase):
    TABLE = [{'title': 'T', 'headers': ['a'], 'rows': [[1]], 'note': ''}]

    @patch.object(ollama.OllamaPlanner, '_chat')
    def test_chinese_answer_is_retried(self, chat):
        chat.side_effect = [{'content': '机械化步兵班'}, {'content': 'В отделении 1 БМП-2.'}]
        self.assertEqual(ollama.OllamaPlanner().compose('Сколько БМП?', self.TABLE), 'В отделении 1 БМП-2.')

    @patch.object(ollama.OllamaPlanner, '_chat', return_value={'content': '机械化步兵班'})
    def test_persistent_chinese_falls_back(self, chat):
        self.assertIn('Найдено по вашему вопросу', ollama.OllamaPlanner().compose('Сколько БМП?', self.TABLE))

    def test_brigade_unit_codes_kept(self):
        from catalog.assistant.tools import normalize_unit_code as n
        self.assertEqual(n('вос-1.рр'), 'ВОС-1.РР')
        self.assertEqual(n('ВОС-1.Б1.МБ.В2'), 'ВОС-1.Б1.МБ.В2')

    @patch('catalog.assistant.tools.repo.get_formation', return_value={'formation_code': 'ВОС-1', 'formation_name': 'Б',
                                                                       'personnel': 1, 'officers': 1, 'sergeants': 0,
                                                                       'soldiers': 0, 'equipment_units': 0})
    @patch('catalog.assistant.tools.repo.subunits', return_value=[{'subunit_code': 'ВОС-1.У', 'subunit_name': 'управление бригады'}])
    @patch('catalog.assistant.tools.repo.unit_staff', return_value=[])
    @patch('catalog.assistant.tools.repo.unit_equipment', return_value=[])
    def test_unit_suffix_joined_with_formation(self, *_):
        from catalog.assistant import tools
        table = tools.run('unit_composition', {'formation': 'ВОС-1', 'unit': 'У'}, SCOPE)
        self.assertIn('ВОС-1.У', table['title'])

    @patch('catalog.assistant.tools.repo.get_formation', return_value={'formation_code': 'ВОС-1', 'formation_name': 'Б',
                                                                       'personnel': 1, 'officers': 1, 'sergeants': 0,
                                                                       'soldiers': 0, 'equipment_units': 0})
    @patch('catalog.assistant.tools.repo.unit_staff', return_value=[])
    @patch('catalog.assistant.tools.repo.unit_equipment', return_value=[
        {'item_sname': '120-мм 2С12 Сани', 'item_name': '120-мм буксируемый минометный комплекс 2С12 Сани',
         'category': 'Ракетно-артиллерийское вооружение', 'qty': 6, 'unit_measure': 'шт.'},
        {'item_sname': 'БМП-2', 'item_name': 'Боевая машина пехоты БМП-2', 'category': 'Бронетанковое', 'qty': 30, 'unit_measure': 'шт.'}])
    def test_search_narrows_rows(self, *_):
        from catalog.assistant import tools
        rows = tools.run('unit_composition', {'formation': 'ВОС-1', 'search': 'миномётов'}, SCOPE)['rows']
        self.assertEqual(len(rows), 6)
        self.assertIn('2С12', rows[-1][0])

    @patch('catalog.assistant.tools.repo.subunits', return_value=[
        {'subunit_code': 'ЮГ-1.Б1.ГВ', 'subunit_name': 'гранатомётный взвод'},
        {'subunit_code': 'ЮГ-1.Б2.ГВ', 'subunit_name': 'гранатомётный взвод'},
        {'subunit_code': 'ЮГ-1.Б2.ГВ.О1', 'subunit_name': '1-е отделение'},
        {'subunit_code': 'ЮГ-1.РР', 'subunit_name': 'разведывательная рота'}])
    def test_find_unit_by_name(self, _):
        from catalog.assistant.tools import find_unit_by_name as f
        self.assertEqual(f(SCOPE, 'ЮГ-1', 'гранатомётный взвод', 2), 'ЮГ-1.Б2.ГВ')
        self.assertEqual(f(SCOPE, 'ЮГ-1', 'гранатометного взвода'), 'ЮГ-1.Б1.ГВ')
        self.assertEqual(f(SCOPE, 'ЮГ-1', 'разведывательной роты'), 'ЮГ-1.РР')
        self.assertIsNone(f(SCOPE, 'ЮГ-1', 'танковый полк'))


class OpenAICompatTests(SimpleTestCase):
    @patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'})
    @patch('catalog.assistant.openai_compat.urllib.request.urlopen')
    def test_tool_call_arguments_are_parsed(self, urlopen):
        import io
        from catalog.assistant.openai_compat import OpenAICompatPlanner
        payload = {'choices': [{'message': {'content': None, 'tool_calls': [
            {'id': 'c1', 'type': 'function', 'function': {'name': 'district_summary',
                                                          'arguments': '{"district": "ОКР-ЮГ", "extra": 1}'}}]}}]}
        urlopen.return_value.__enter__.return_value = io.BytesIO(json.dumps(payload).encode())
        planner = OpenAICompatPlanner('groq', 'some-model')
        self.assertEqual(planner.plan('Сколько людей на Юге?', DISTRICTS), [('district_summary', {'district': 'ОКР-ЮГ'})])
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, 'https://api.groq.com/openai/v1/chat/completions')
        self.assertEqual(request.headers['Authorization'], 'Bearer test-key')

    @patch.dict('os.environ', {}, clear=True)
    def test_missing_key_is_reported(self):
        from catalog.assistant.openai_compat import OpenAICompatPlanner
        with self.assertRaises(ollama.ModelUnavailable):
            OpenAICompatPlanner('gemini', 'gemini-x')


class ClaudePlannerTests(SimpleTestCase):
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('catalog.assistant.claude.anthropic.Anthropic')
    def test_tool_use_blocks_become_calls(self, client_cls):
        from types import SimpleNamespace as NS
        from catalog.assistant.claude import ClaudePlanner
        response = NS(stop_reason='tool_use',
                      content=[NS(type='thinking'), NS(type='tool_use', name='district_summary', input={'district': 'ОКР-ЗАП'})],
                      usage=NS(input_tokens=3000, output_tokens=60, cache_creation_input_tokens=0, cache_read_input_tokens=0))
        client_cls.return_value.messages.create.return_value = response
        planner = ClaudePlanner()
        self.assertEqual(planner.plan('Батыста қанша адам бар?', DISTRICTS + [{'district_code': 'ОКР-ЗАП', 'short_name': 'Округ «Запад»', 'hq_city': 'Атырау'}]),
                         [('district_summary', {'district': 'ОКР-ЗАП'})])
        kwargs = client_cls.return_value.messages.create.call_args.kwargs
        self.assertEqual(kwargs['model'], 'claude-haiku-5-5')
        self.assertEqual(kwargs['output_config'], {'effort': 'low'})
        self.assertEqual(kwargs['system'][0]['cache_control'], {'type': 'ephemeral'})
        self.assertIn('ОКР-ЗАП', kwargs['messages'][0]['content'])         # подсказка про казахское «Батыс»
        self.assertAlmostEqual(planner.cost(), (3000 * 0.10 + 60 * 0.50) / 1_000_000)

    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('catalog.assistant.claude.anthropic.Anthropic')
    def test_refusal_is_model_unavailable(self, client_cls):
        from types import SimpleNamespace as NS
        from catalog.assistant.claude import ClaudePlanner
        client_cls.return_value.messages.create.return_value = NS(
            stop_reason='refusal', content=[], usage=NS(input_tokens=1, output_tokens=0))
        with self.assertRaises(ollama.ModelUnavailable):
            ClaudePlanner()._chat([{'role': 'system', 'content': 's'}, {'role': 'user', 'content': 'q'}], True)

    @patch.dict('os.environ', {}, clear=True)
    def test_missing_key(self):
        from catalog.assistant.claude import ClaudePlanner
        with self.assertRaises(ollama.ModelUnavailable):
            ClaudePlanner()


class KazakhAnswerTests(SimpleTestCase):
    @patch.object(ollama.OllamaPlanner, '_chat', return_value={'content': 'Батыс округінде 2987 адам бар.'})
    def test_kazakh_question_asks_for_kazakh_answer(self, chat):
        ollama.OllamaPlanner().compose('Батыста қанша адам бар?', [{'title': 'T', 'headers': ['a'], 'rows': [[1]], 'note': ''}])
        self.assertIn('на казахском языке', chat.call_args.args[0][0]['content'])

    @patch.object(ollama.OllamaPlanner, '_chat', return_value={'content': 'В округе 2987 человек.'})
    def test_russian_question_has_no_kazakh_hint(self, chat):
        ollama.OllamaPlanner().compose('Сколько людей на Западе?', [{'title': 'T', 'headers': ['a'], 'rows': [[1]], 'note': ''}])
        self.assertNotIn('на казахском языке', chat.call_args.args[0][0]['content'])

    @patch.object(ollama.OllamaPlanner, '_chat')
    def test_russian_answer_to_kazakh_question_is_retried(self, chat):
        chat.side_effect = [{'content': 'В округе 2987 человек.'}, {'content': 'Округте 2987 адам бар.'}]
        text = ollama.OllamaPlanner().compose('Шығыс округінде қанша адам бар?', [{'title': 'T', 'headers': ['a'], 'rows': [[1]], 'note': ''}])
        self.assertEqual(text, 'Округте 2987 адам бар.')
        self.assertEqual(chat.call_args.args[0][-1], {'role': 'user', 'content': 'Перепиши этот ответ на казахском языке.'})

    @patch.object(ollama.OllamaPlanner, '_chat', return_value={'content': 'В округе 2987 человек.'})
    def test_russian_kept_if_kazakh_retry_fails(self, chat):
        text = ollama.OllamaPlanner().compose('Шығыс округінде қанша адам бар?', [{'title': 'T', 'headers': ['a'], 'rows': [[1]], 'note': ''}])
        self.assertEqual(text, 'В округе 2987 человек.')


class EnglishAnswerTests(SimpleTestCase):
    TABLE = [{'title': 'T', 'headers': ['a'], 'rows': [[1]], 'note': ''}]

    def test_language_detection(self):
        self.assertEqual(ollama.language('How many tanks does brigade YUG-3 have?'), 'en')
        self.assertEqual(ollama.language('Brigade ВОС-1 has 54 Т-72Б tanks.'), 'en')
        self.assertEqual(ollama.language('Сколько танков в ЮГ-3?'), 'ru')
        self.assertEqual(ollama.language('Сколько БМП-2 в ВОС-1?'), 'ru')
        self.assertEqual(ollama.language('Шығыс округінде қанша адам бар?'), 'kk')

    @patch.object(ollama.OllamaPlanner, '_chat', return_value={'content': 'The South district has 4061 people.'})
    def test_english_question_gets_english_answer(self, chat):
        text = ollama.OllamaPlanner().compose('How many people are in the South district?', self.TABLE)
        self.assertEqual(text, 'The South district has 4061 people.')
        self.assertIn('in English', chat.call_args.args[0][0]['content'])
        self.assertEqual(chat.call_count, 1)

    @patch.object(ollama.OllamaPlanner, '_chat')
    def test_russian_answer_to_english_question_is_retried(self, chat):
        chat.side_effect = [{'content': 'В округе 4061 человек.'}, {'content': 'The district has 4061 people.'}]
        text = ollama.OllamaPlanner().compose('How many people are in the South district?', self.TABLE)
        self.assertEqual(text, 'The district has 4061 people.')
        self.assertEqual(chat.call_args.args[0][-1], {'role': 'user', 'content': 'Rewrite this answer in English.'})

    @patch.object(ollama.OllamaPlanner, '_chat')
    def test_english_answer_to_russian_question_is_retried(self, chat):
        chat.side_effect = [{'content': 'The district has 4061 people.'}, {'content': 'В округе 4061 человек.'}]
        self.assertEqual(ollama.OllamaPlanner().compose('Сколько людей на Юге?', self.TABLE), 'В округе 4061 человек.')

    def test_english_district_names(self):
        self.assertEqual(ollama.mentioned_districts('How many people in the East?', DISTRICTS), ['ОКР-ВОС'])
        self.assertEqual(ollama.mentioned_districts('What is the least supplied item?', DISTRICTS), [])

    def test_latin_codes_become_cyrillic(self):
        from catalog.assistant import tools
        self.assertEqual(tools.cyrillic_codes('YUG-3'), 'ЮГ-3')
        self.assertEqual(tools.cyrillic_codes('vos-1.Б1'), 'ВОС-1.Б1')
        self.assertEqual(tools.cyrillic_codes('OKR-AST'), 'ОКР-АСТ')
        self.assertEqual(tools.cyrillic_codes('ВОС-1'), 'ВОС-1')


class SearchTotalTests(SimpleTestCase):
    def test_sum_of_matching_items(self):
        from catalog.assistant import tools
        rows = [{'k': 'Образец: Т-72Б — Танк Т-72Б', 'v': '54 шт.'}, {'k': 'Образец: Т-72К — Танк командирский Т-72К', 'v': '8 шт.'},
                {'k': 'Образец: РПГ-7 — Противотанковый гранатомёт', 'v': '9 шт.'}]
        self.assertEqual(tools.search_total('танк', rows), 'Всего (танк): 62 шт. (54 + 8).')

    def test_single_item_has_no_total(self):
        from catalog.assistant import tools
        self.assertEqual(tools.search_total('миномет', [{'k': 'Образец: 2С12 — Миномёт', 'v': '6 шт.'}]), '')


class StripMetaTests(SimpleTestCase):
    def test_language_remark_removed(self):
        self.assertEqual(ollama.strip_meta('Вопрос на русском, поэтому отвечаю по-русски. В бригаде 62 танка.'),
                         'В бригаде 62 танка.')
        self.assertEqual(ollama.strip_meta('Вопрос на казахском, поэтому отвечаю на казахском.\n\nРотада 30 адам бар.'),
                         'Ротада 30 адам бар.')

    def test_echoed_question_removed(self):
        text = 'Вопрос на казахском: «Батыста қанша адам бар?» — «Сколько людей?»\n\nОтвет: в округе 2987 человек.'
        self.assertEqual(ollama.strip_meta(text), 'в округе 2987 человек.')

    def test_plain_answer_kept(self):
        for text in ('В округе «Юг» 4061 человек.', 'The South district has 4,061 people.',
                     'Ответить не могу: к округу «Юг» нет доступа.'):
            self.assertEqual(ollama.strip_meta(text), text)

    @patch.object(ollama.OllamaPlanner, '_chat')
    def test_echo_then_russian_is_retried_in_kazakh(self, chat):
        chat.side_effect = [{'content': 'Вопрос: «Батыста қанша адам бар?»\nОтвет: в округе 2987 человек.'},
                            {'content': 'Батыс округінде 2987 адам бар.'}]
        text = ollama.OllamaPlanner().compose('Батыста қанша адам бар?', [{'title': 'T', 'headers': ['a'], 'rows': [[1]], 'note': ''}])
        self.assertEqual(text, 'Батыс округінде 2987 адам бар.')


class DirectAnswerLanguageTests(SimpleTestCase):
    @patch.object(ollama.OllamaPlanner, '_chat', return_value={'content': 'You have no access to the South district.'})
    def test_russian_direct_answer_to_english_question_is_rewritten(self, chat):
        planner = ollama.OllamaPlanner()
        planner.direct_text = 'У вас нет доступа к округу «Юг».'
        self.assertEqual(planner.compose('How many people are in the South district?', []),
                         'You have no access to the South district.')

    @patch.object(ollama.OllamaPlanner, '_chat')
    def test_matching_direct_answer_kept(self, chat):
        planner = ollama.OllamaPlanner()
        planner.direct_text = 'У вас нет доступа к округу «Юг».'
        self.assertEqual(planner.compose('Сколько людей на Юге?', []), 'У вас нет доступа к округу «Юг».')
        chat.assert_not_called()


class QuotedQuestionTests(SimpleTestCase):
    def test_answer_phrase_is_not_meta(self):
        text = 'Разница составляет 1074 человека. Ответ на вопрос: на 1074 человека.'
        self.assertIsNone(ollama.META_SENTENCE.search(text))
        self.assertEqual(ollama.strip_meta(text), text)

    @patch.object(ollama.OllamaPlanner, '_chat')
    def test_quoted_kazakh_question_does_not_count(self, chat):
        chat.side_effect = [{'content': 'Вопрос на казахском: «Батыста қанша адам бар?» Ответ по округу «Запад»: 2987 человек.'},
                            {'content': 'Батыс округінде 2987 адам бар.'}]
        text = ollama.OllamaPlanner().compose('Батыста қанша адам бар?', [{'title': 'T', 'headers': ['a'], 'rows': [[1]], 'note': ''}])
        self.assertEqual(text, 'Батыс округінде 2987 адам бар.')


class MixedLanguageTests(SimpleTestCase):
    def test_russian_answer_with_kazakh_names_is_russian(self):
        self.assertEqual(ollama.language('Шығыс округінде («Восток») числено 2987 адам. Из них 358 офицеров, '
                                         '689 сержантов и 1940 солдат.'), 'ru')

    def test_kazakh_answers(self):
        for text in ('Батыс округінде 2987 адам бар.',
                     'ВОС-1 бригадасының 8-ші танк ротасында барлығы 30 адам бар. Оның ішінде 4 офицер, 6 сержант және 20 солдат.',
                     'Ең нашар көрсеткіш «Горючее и смазочные материалы» санатында: 68,8 %.'):
            self.assertEqual(ollama.language(text), 'kk', text)

    def test_translation_remark_removed(self):
        self.assertEqual(ollama.strip_meta('Бұл жауапты қазақ тіліне аударамын. Батыс округінде 2987 адам бар.'),
                         'Батыс округінде 2987 адам бар.')


class AuditLengthTests(TestCase):
    def test_long_mode_and_question_fit_audit_fields(self):
        from catalog.assistant import engine
        user = get_user_model().objects.create_user('audit_len', password='x' * 12)

        class LongPlanner:
            mode = 'ИИ · claude-haiku-5-5 (Anthropic, облако)'

            def plan(self, question, districts):
                return []

            def compose(self, question, results):
                return 'Ответ.'

        with patch('catalog.assistant.engine.repo.list_districts', return_value=DISTRICTS):
            engine.answer(user, SCOPE, 'В' * 600, planner=LongPlanner())
        row = AssistantAudit.objects.get(user=user)
        self.assertEqual(len(row.mode), 40)
        self.assertEqual(len(row.question), 500)
