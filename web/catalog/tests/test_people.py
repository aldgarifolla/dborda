"""Личный состав: вкладка «Личный состав», карточка человека и область доступа (repository подменён)."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from catalog import repository as repo
from catalog.models import UserRole

from .test_districts import DISTRICTS, FORMATION, SCOPE, SUBUNITS

PERSON = {'subunit_code': 'АСТ-1.Б1.Р1.В1.О1', 'subunit_name': '1-е механизированное отделение', 'level': 'отделение',
          'formation_code': 'АСТ-1', 'district_code': 'ОКР-АСТ', 'seq': 1, 'seat': 1,
          'position_name': 'Командир отделения (командир БМП)', 'rank_name': 'сержант третьего класса',
          'rank_category': 'сержанты', 'personal_number': 'ЛН-007791', 'full_name': 'Калиев Еркебулан Нуржанович',
          'age': 22, 'birth_date': '2004-05-12', 'service_type': 'по контракту', 'service_start': '2024-01-10',
          'contract_end': '2027-01-10', 'nationality': 'казах', 'birthplace': 'Актюбинская обл.',
          'education': 'общее среднее', 'marital_status': 'холост', 'children': 0, 'height_cm': 178, 'weight_kg': 74,
          'blood_group': '0(I) Rh+', 'fitness_category': 'А (годен)', 'origin': 'reused'}


def people(code, scope, page=1, term='', **kw):
    rows = [PERSON] if not term or term.casefold() in PERSON['full_name'].casefold() else []
    return rows, len(rows)


@patch.multiple('catalog.repository', allowed_codes=lambda user: SCOPE,
                get_district=lambda code, scope: next((d for d in DISTRICTS if d['district_code'] == code), None),
                get_formation=lambda fcode, scope: FORMATION if fcode == 'АСТ-1' else None,
                subunits=lambda fcode, scope: SUBUNITS, unit_people=people,
                get_person=lambda number, scope: PERSON if number == 'ЛН-007791' and 'ОКР-АСТ' in scope else None)
class PeoplePagesTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user('people_viewer', password='StrongDemo123!')
        UserRole.objects.create(user=user, role='viewer')
        self.client.force_login(user)

    def test_people_tab_on_formation_and_subunit(self):
        url = reverse('formation_detail', args=['ОКР-АСТ', 'АСТ-1']) + '?tab=people'
        page = self.client.get(url).content.decode()
        self.assertIn('Калиев Еркебулан Нуржанович', page)
        self.assertIn(reverse('person_detail', args=['ЛН-007791']), page)
        found = self.client.get(url + '&q=калиев').content.decode()
        self.assertIn('Калиев', found)
        self.assertIn('Никого не найдено', self.client.get(url + '&q=иванов').content.decode())

    def test_person_card(self):
        page = self.client.get(reverse('person_detail', args=['ЛН-007791'])).content.decode()
        for text in ('Калиев Еркебулан Нуржанович', 'сержант третьего класса', '0(I) Rh+'):
            self.assertIn(text, page)

    def test_unknown_or_foreign_person_is_404(self):
        self.assertEqual(self.client.get(reverse('person_detail', args=['ЛН-000000'])).status_code, 404)


class PeopleQueryTests(SimpleTestCase):
    def test_no_scope_no_people(self):
        self.assertEqual(repo.unit_people('АСТ-1', set()), ([], 0))
        self.assertIsNone(repo.get_person('ЛН-007791', set()))

    @patch('catalog.repository.select')
    def test_query_is_scoped_and_parameterized(self, select):
        select.side_effect = [[{'n': 1}], [PERSON]]
        rows, total = repo.unit_people('АСТ-1', {'ОКР-АСТ'}, page=1, term="x'; drop")
        self.assertEqual(total, 1)
        sql, args = select.call_args.args
        self.assertIn('district_code = ANY(%s::text[])', sql)
        self.assertNotIn('drop', sql)
        self.assertIn(['ОКР-АСТ'], args)


class YearsFilterTests(SimpleTestCase):
    def test_plural(self):
        from catalog.templatetags.chat import years
        self.assertEqual([years(n) for n in (21, 22, 25, 31, 11, 12, 44)],
                         ['21 год', '22 года', '25 лет', '31 год', '11 лет', '12 лет', '44 года'])


class SquadDefaultTabTests(SimpleTestCase):
    def test_squad_opens_people(self):
        from django.test import RequestFactory
        from catalog.views import unit_tab
        rf = RequestFactory()
        self.assertEqual(unit_tab(rf.get('/'), 'отделение'), 'people')
        self.assertEqual(unit_tab(rf.get('/?tab=summary'), 'отделение'), 'people')
        self.assertEqual(unit_tab(rf.get('/?tab=equipment'), 'отделение'), 'equipment')
        self.assertEqual(unit_tab(rf.get('/'), 'взвод'), 'summary')


class NumFilterTests(SimpleTestCase):
    def test_format(self):
        from decimal import Decimal
        from django.utils import translation
        from catalog.templatetags.fmt import num
        with translation.override('ru'):
            self.assertEqual(num(10049), '10\xa0049')
            self.assertEqual(num(83.4), '83,4')
            self.assertEqual(num(Decimal('1889')), '1\xa0889')
            self.assertEqual(num(7), '7')
        self.assertIsNone(num(None))
        self.assertEqual(num('120 шт.'), '120 шт.')


@patch.multiple('catalog.repository', allowed_codes=lambda user: SCOPE,
                get_district=lambda code, scope: next((d for d in DISTRICTS if d['district_code'] == code), None),
                get_formation=lambda fcode, scope: FORMATION if fcode == 'АСТ-1' else None,
                subunits=lambda fcode, scope: SUBUNITS)
class PeopleFilterTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user('filter_viewer', password='StrongDemo123!')
        UserRole.objects.create(user=user, role='viewer')
        self.client.force_login(user)

    def test_filters_are_passed_and_shown(self):
        calls = []

        def fake(code, scope, page=1, term='', category='', service='', district=''):
            calls.append((code, category, service, district))
            return [PERSON], 1
        with patch('catalog.repository.unit_people', side_effect=fake):
            url = reverse('formation_detail', args=['ОКР-АСТ', 'АСТ-1']) + '?tab=people&cat=офицеры&srv=по+контракту'
            page = self.client.get(url).content.decode()
            self.assertEqual(calls[-1], ('АСТ-1', 'офицеры', 'по контракту', ''))
            self.assertIn('tag tag-on', page)
            self.assertIn('Найдено: 1', page)
            self.client.get(reverse('district_detail', args=['ОКР-АСТ']) + '?tab=people')
            self.assertEqual(calls[-1][3], 'ОКР-АСТ')

    @patch('catalog.repository.select')
    def test_bad_filter_values_ignored(self, select):
        select.side_effect = [[{'n': 0}], []]
        repo.unit_people('АСТ-1', {'ОКР-АСТ'}, category="'; drop", service='x')
        sql = select.call_args_list[0].args[0]
        self.assertNotIn('rank_category', sql)
        self.assertNotIn('service_type', sql)


class SearchWordsTests(SimpleTestCase):
    def test_stems(self):
        self.assertEqual(repo.search_words('командир батальона'), ['команд', 'баталь'])
        self.assertEqual(repo.search_words('ЛН-008307'), ['ЛН-008307'])
        self.assertEqual(repo.search_words('а в'), [])
