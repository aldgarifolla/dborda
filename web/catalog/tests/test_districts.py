"""Округа: коды округов в помощнике и отрисовка всех страниц (repository подменён, PostgreSQL не нужен)."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from catalog.assistant import tools
from catalog.assistant.planner import KeywordPlanner
from catalog.models import AssistantChat, UserRole

SCOPE = {'ОКР-АСТ', 'ОКР-ВОС', 'ОКР-ЮГ'}
DISTRICTS = [
    {'district_code': 'ОКР-АСТ', 'short_name': 'Округ «Астана»', 'full_name': 'учебный округ «Астана»',
     'hq_city': 'Караганда', 'side': 'свои', 'zone_note': 'г. Астана, Акмолинская область', 'origin': 'derived',
     'confidence': 'B', 'formations': 3, 'personnel_total': 8092, 'equipment_items': 140, 'equipment_units': 10708,
     'supply_pct': 82.9},
    {'district_code': 'ОКР-ВОС', 'short_name': 'Округ «Восток»', 'full_name': 'учебный округ «Восток»',
     'hq_city': 'Семей', 'side': 'свои', 'zone_note': 'Павлодарская область', 'origin': 'derived',
     'confidence': 'B', 'formations': 3, 'personnel_total': 8444, 'equipment_items': 140, 'equipment_units': 11166,
     'supply_pct': 76.4},
    {'district_code': 'ОКР-ЮГ', 'short_name': 'Округ «Юг»', 'full_name': 'учебный округ «Юг»',
     'hq_city': 'Тараз', 'side': 'свои', 'zone_note': 'г. Алматы', 'origin': 'derived',
     'confidence': 'B', 'formations': 4, 'personnel_total': 10905, 'equipment_items': 140, 'equipment_units': 14426,
     'supply_pct': 85.9},
]
EQUIP = [{'item_sname': 'БМП-2', 'item_name': 'Боевая машина пехоты', 'category': 'Бронетанковое вооружение и техника',
          'qty': 120, 'unit_measure': 'шт.', 'origin': 'generated', 'confidence': 'C'}]
FORMATION = {'formation_code': 'АСТ-1', 'district_code': 'ОКР-АСТ', 'district_name': 'Округ «Астана»',
             'formation_name': 'Условное соединение АСТ-1', 'formation_type': 'механизированная бригада (условная)',
             'scale': 1.0, 'origin': 'generated', 'battalions': 1, 'companies': 1, 'platoons': 1, 'squads': 2}
SUBUNITS = [
    {'subunit_code': 'АСТ-1.У', 'parent_code': None, 'level': 'управление', 'level_rank': 1,
     'subunit_name': 'управление бригады', 'confidence': 'C'},
    {'subunit_code': 'АСТ-1.Б1', 'parent_code': None, 'level': 'батальон', 'level_rank': 1,
     'subunit_name': '1-й механизированный батальон', 'confidence': 'C'},
    {'subunit_code': 'АСТ-1.Б1.Р1', 'parent_code': 'АСТ-1.Б1', 'level': 'рота', 'level_rank': 2,
     'subunit_name': '1-я механизированная рота', 'confidence': 'C'},
    {'subunit_code': 'АСТ-1.Б1.Р1.В1', 'parent_code': 'АСТ-1.Б1.Р1', 'level': 'взвод', 'level_rank': 3,
     'subunit_name': '1-й взвод', 'confidence': 'C'},
    {'subunit_code': 'АСТ-1.Б1.Р1.В1.О1', 'parent_code': 'АСТ-1.Б1.Р1.В1', 'level': 'отделение', 'level_rank': 4,
     'subunit_name': '1-е отделение', 'confidence': 'C'},
    {'subunit_code': 'АСТ-1.Б1.Р1.В1.О2', 'parent_code': 'АСТ-1.Б1.Р1.В1', 'level': 'отделение', 'level_rank': 4,
     'subunit_name': '2-е отделение', 'confidence': 'C'},
]
STAFF = [{'position_name': 'Командир отделения (командир БМП)', 'rank_name': 'сержант третьего класса',
          'category': 'сержанты', 'qty': 1, 'source_code': 'W_MSO', 'source_title': 'Мотострелковое отделение',
          'source_url': 'https://ru.wikipedia.org/wiki/Мотострелковое_отделение', 'confidence': 'B'}]
SUPPLY = [{'item_sname': 'АИ-92', 'item_name': 'Бензин', 'category': 'Горючее и смазочные материалы', 'norm_qty': 1000,
           'stock_qty': 800, 'deficit': 200, 'provision_pct': 80.0, 'unit_measure': 'л', 'origin': 'generated',
           'confidence': 'C'}]


class DistrictCodeTests(TestCase):
    def test_tool_accepts_code_in_any_case(self):
        self.assertEqual(tools._district(SCOPE, 'окр-аст'), 'ОКР-АСТ')
        self.assertEqual(tools._district(SCOPE, 'Окр-Юг'), 'ОКР-ЮГ')

    def test_tool_rejects_district_outside_scope(self):
        with self.assertRaises(tools.ToolError):
            tools._district(SCOPE, 'ОКР-ЗАП')

    def test_planner_finds_district_by_name_forms(self):
        p = KeywordPlanner()
        self.assertEqual(p._districts('численность астаны', DISTRICTS), ['ОКР-АСТ'])
        self.assertEqual(p._districts('дефицит запасов на востоке', DISTRICTS), ['ОКР-ВОС'])
        self.assertEqual(p._districts('состав округа «юг»', DISTRICTS), ['ОКР-ЮГ'])
        self.assertEqual(p._districts('что на юге', DISTRICTS), ['ОКР-ЮГ'])

    def test_planner_no_false_match_on_similar_word(self):
        west = [{'district_code': 'ОКР-ЗАП', 'short_name': 'Округ «Запад»'}]
        self.assertEqual(KeywordPlanner()._districts('дефицит запасов', west), [])
        self.assertEqual(KeywordPlanner()._districts('техника на западе', west), ['ОКР-ЗАП'])

    def test_planner_says_when_it_substitutes_the_only_district(self):
        p = KeywordPlanner()
        calls = p.plan('Дефицит запасов на Востоке', DISTRICTS[:1])
        self.assertEqual(calls[0][1]['district'], 'ОКР-АСТ')
        self.assertIn('не распознан или вам недоступен', p.compose('q', [{'title': 'Запасы — ОКР-АСТ'}]))


@patch.multiple('catalog.repository', allowed_codes=lambda user: SCOPE,
                list_districts=lambda scope: DISTRICTS,
                get_district=lambda code, scope: next((d for d in DISTRICTS if d['district_code'] == code), None),
                totals=lambda scope: {'districts': 3, 'formations': 10, 'personnel': 27441, 'equipment_units': 36300},
                compare=lambda scope, metric: [{'district_code': d['district_code'], 'short_name': d['short_name'],
                                                'value': d['personnel_total']} for d in DISTRICTS],
                regions=lambda code, scope: [{'region_name': 'Акмолинская область', 'region_kind': 'область', 'confidence': 'A',
                                              'basis': 'указ № 354, п. 2', 'as_of': '2012–2018', 'source_title': 'Указ № 354',
                                              'source_url': 'https://zakon.uchet.kz/rus/docs/U1200000354'}],
                formations=lambda code, scope: [{'formation_code': 'АСТ-1', 'formation_name': 'Условное соединение АСТ-1',
                                                 'formation_type': 'механизированная бригада (условная)', 'scale': 1.0,
                                                 'origin': 'generated', 'battalions': 3, 'companies': 9, 'platoons': 27,
                                                 'squads': 81}],
                get_formation=lambda fcode, scope: FORMATION if fcode == 'АСТ-1' else None,
                subunits=lambda fcode, scope: SUBUNITS,
                unit_staff=lambda code, scope, own_only=False: STAFF,
                unit_people=lambda code, scope, page=1, term='', **kw: ([], 0),
                unit_equipment=lambda code, scope: [{'item_sname': 'БМП-2', 'item_name': 'Боевая машина пехоты',
                                                     'category': 'Бронетанковое', 'qty': 1, 'unit_measure': 'шт.',
                                                     'sources': 'W_MSO', 'confidence': 'B'}],
                norm_sources=lambda: [{'source_code': 'W_MSO', 'title': 'Мотострелковое отделение',
                                       'url': 'https://ru.wikipedia.org/wiki/Мотострелковое_отделение', 'confidence': 'B'}],
                strength=lambda code, scope: [{'category': 'офицеры', 'personnel': 856, 'origin': 'generated', 'confidence': 'C'}],
                equipment_categories=lambda code, scope: [{'category': 'Бронетанковое вооружение и техника', 'items': 1, 'units': 120}],
                equipment=lambda code, scope, **kw: (EQUIP, 1),
                supply_categories=lambda code, scope: [{'category': 'Горючее и смазочные материалы', 'items': 1,
                                                        'deficit_items': 1, 'provision_pct': 80.0}],
                supply=lambda code, scope, **kw: (SUPPLY, 1),
                item_catalog=lambda term='', page=1: ([{'item_sname': 'БМП-2', 'item_name': 'Боевая машина пехоты',
                                                        'category': 'Бронетанковое', 'unit_measure': 'шт.'}], 1),
                get_item=lambda sname: {'item_sname': sname, 'item_name': 'Боевая машина пехоты', 'category': 'Бронетанковое',
                                        'manufacturer_country': 'СССР/Россия', 'unit_measure': 'шт.'},
                item_specs=lambda sname: [{'param_name': 'Экипаж (расчёт)', 'value_num': 3, 'value_text': None, 'unit': 'чел.',
                                           'confidence': 'A', 'source_code': 'X', 'source_name': 'Wikipedia', 'note': ''}],
                item_holders=lambda sname, scope: [{'district_code': 'ОКР-АСТ', 'short_name': 'Округ «Астана»', 'qty': 120,
                                                    'unit_measure': 'шт.'}])
class DistrictPagesTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username='page_viewer', password='StrongDemo123!')
        UserRole.objects.create(user=user, role='viewer')
        self.client.force_login(user)

    def get_ok(self, url, *needles):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, url)
        text = response.content.decode()
        for n in needles:
            self.assertIn(n, text, url)
        return text

    def test_dashboard(self):
        self.get_ok(reverse('dashboard'), 'Округ «Астана»', 'Караганда')

    def test_district_list(self):
        for metric in ('personnel', 'equipment', 'supply', 'formations', 'bogus'):
            self.get_ok(reverse('district_list') + f'?metric={metric}', 'bar-fill', 'Тараз')

    def test_district_tabs(self):
        url = reverse('district_detail', kwargs={'code': 'ОКР-АСТ'})
        self.get_ok(url, 'Акмолинская область', 'Условное соединение АСТ-1', 'офицеры')
        self.get_ok(url + '?tab=equipment&category=Бронетанковое вооружение и техника', 'БМП-2')
        self.get_ok(url + '?tab=supply&deficit=1', 'АИ-92', 'Только дефицит')

    def test_items_and_item_card(self):
        self.get_ok(reverse('items') + '?q=бмп', 'БМП-2')
        self.get_ok(reverse('item_detail', kwargs={'sname': 'БМП-2'}), 'Экипаж (расчёт)', 'Округ «Астана»')

    def test_district_lists_formation_with_subunit_counts(self):
        self.get_ok(reverse('district_detail', kwargs={'code': 'ОКР-АСТ'}), 'Отделений', '>81<',
                    reverse('formation_detail', kwargs={'code': 'ОКР-АСТ', 'fcode': 'АСТ-1'}))

    def test_old_rgk_links_redirect_to_new_codes(self):
        response = self.client.get('/districts/РгК-ВОС/?tab=supply')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.url, reverse('district_detail', kwargs={'code': 'ОКР-ВОС'}) + '?tab=supply')
        response = self.client.get('/districts/РгК-АСТ/formations/АСТ-1/')
        self.assertEqual(response.url, reverse('formation_detail', kwargs={'code': 'ОКР-АСТ', 'fcode': 'АСТ-1'}))

    def test_drill_down_brigade_to_squad(self):
        def url(scode=None):
            if scode is None:
                return reverse('formation_detail', kwargs={'code': 'ОКР-АСТ', 'fcode': 'АСТ-1'})
            return reverse('subunit_detail', kwargs={'code': 'ОКР-АСТ', 'fcode': 'АСТ-1', 'scode': scode})
        page = self.get_ok(url(), '1-й механизированный батальон', url('АСТ-1.Б1'))
        self.assertNotIn('1-я механизированная рота', page)          # бригада показывает только батальоны
        page = self.get_ok(url('АСТ-1.Б1'), '1-я механизированная рота', url('АСТ-1.Б1.Р1'))
        self.assertNotIn('1-й взвод', page)
        self.get_ok(url('АСТ-1.Б1.Р1'), '1-й взвод', url('АСТ-1.Б1.Р1.В1'), '1-й механизированный батальон')
        self.get_ok(url('АСТ-1.Б1.Р1.В1'), '1-е отделение', '2-е отделение', url('АСТ-1.Б1.Р1.В1.О2'))
        page = self.get_ok(url('АСТ-1.Б1.Р1.В1.О2'), '2-е отделение', '1-я механизированная рота', 'Личный состав')
        self.assertNotIn('?tab=summary', page)                      # у отделения сразу личный состав, без сводки

    def test_unit_tabs(self):
        base = reverse('subunit_detail', kwargs={'code': 'ОКР-АСТ', 'fcode': 'АСТ-1', 'scode': 'АСТ-1.Б1.Р1.В1.О2'})
        self.get_ok(base + '?tab=staff', 'Командир отделения (командир БМП)', 'сержант третьего класса', 'W_MSO')
        self.get_ok(base + '?tab=equipment', 'БМП-2', 'Боевая машина пехоты')
        brigade = reverse('formation_detail', kwargs={'code': 'ОКР-АСТ', 'fcode': 'АСТ-1'})
        self.get_ok(brigade, 'Откуда данные', 'Мотострелковое отделение')
        self.get_ok(brigade + '?tab=staff', 'Командир отделения (командир БМП)')

    def test_unit_composition_tool(self):
        table = tools.run('unit_composition', {'unit': 'аст-1.б1.р1.в1.о2'}, SCOPE)
        self.assertIn('2-е отделение', table['title'])
        self.assertIn(['Образец: БМП-2 — Боевая машина пехоты', '1 шт.'], table['rows'])
        with self.assertRaises(tools.ToolError):
            tools.run('unit_composition', {'unit': 'АСТ-1.Б9'}, SCOPE)

    def test_unknown_subunit_is_404(self):
        response = self.client.get(reverse('subunit_detail', kwargs={'code': 'ОКР-АСТ', 'fcode': 'АСТ-1', 'scode': 'АСТ-1.Б9'}))
        self.assertEqual(response.status_code, 404)

    def test_formation_of_other_district_is_404(self):
        response = self.client.get(reverse('formation_detail', kwargs={'code': 'ОКР-ВОС', 'fcode': 'АСТ-1'}))
        self.assertEqual(response.status_code, 404)

    def test_formation_structure_tool(self):
        from catalog.repository import subunit_tree
        self.assertEqual(len(subunit_tree(SUBUNITS)[1]['children'][0]['children'][0]['children']), 2)
        table = tools.run('formation_structure', {'formation': 'аст-1'}, SCOPE)
        self.assertEqual(table['rows'][1], ['1-й механизированный батальон (АСТ-1.Б1)', 'батальон', None, 1, 2])
        with self.assertRaises(tools.ToolError):
            tools.run('formation_structure', {'formation': 'ЗАП-1'}, SCOPE)

    def test_assistant_page_and_question(self):
        self.get_ok(reverse('assistant'), 'Округ «Юг»', 'Новый чат')
        response = self.client.post(reverse('assistant'), {'question': 'сравни округа по численности'})
        self.assertRedirects(response, reverse('assistant_chat', args=[AssistantChat.objects.get().pk]))
        self.get_ok(response.url, 'Сравнение округов', '8092', 'сравни округа по численности')
