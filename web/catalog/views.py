from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST
from . import repository as repo
from .assistant import answer as assistant_answer
from .assistant.engine import LIMIT_TEXT, limit_status, suggest_title
from .models import AssistantChat, UnitGrant, UserRole, GrantAudit
from django.core.exceptions import ValidationError
from .services import assign_grant, can_manage, create_user, GrantDenied, set_user_active

TABS = ('summary', 'people', 'equipment', 'supply')
CHAT_LIST_LEN = 40        # чатов в боковом меню
CHAT_CONTEXT = 3          # сколько прошлых обменов чата видит помощник (для уточнений «а на Востоке?»)
CHAT_EXAMPLES = ('Сравни округа по численности', 'Чего больше всего не хватает на Востоке?',
                 'Сколько танков в бригаде ЮГ-3?', 'Шығыс округінде қанша адам бар?',
                 'What is the highway range of the BMP-2?')


def scope_for(request):
    return repo.allowed_codes(request.user)


def get_or_404(code, scope):
    district = repo.get_district(code, scope)
    if not district:
        raise Http404('Округ не найден')
    return district


def pager(page, total):
    page, _ = repo.page_bounds(page)
    pages = max(1, -(-total // repo.PAGE_SIZE))
    page = min(page, pages)
    return {'page': page, 'pages': pages, 'total': total,
            'prev': page - 1 if page > 1 else None, 'next': page + 1 if page < pages else None}


@login_required
def dashboard(request):
    scope = scope_for(request)
    return render(request, 'catalog/dashboard.html', {
        'counts': repo.totals(scope), 'districts': repo.list_districts(scope),
        'role': getattr(getattr(request.user, 'demo_role', None), 'role', 'viewer'),
    })


@login_required
def district_list(request):
    scope = scope_for(request)
    metric = request.GET.get('metric', 'personnel')
    if metric not in repo.METRICS:
        metric = 'personnel'
    rows = repo.compare(scope, metric)
    top = max([r['value'] or 0 for r in rows], default=0)
    for r in rows:
        r['bar'] = round(100 * (r['value'] or 0) / top) if top else 0
    return render(request, 'catalog/districts.html', {
        'districts': repo.list_districts(scope), 'compare': rows, 'metric': metric,
        'metrics': [(k, v[1]) for k, v in repo.METRICS.items()], 'metric_title': repo.METRICS[metric][1],
    })


OLD_CODE_PREFIX = 'РгК-'   # до переименования округа назывались РгК-…; старые ссылки ведут на ОКР-…


def renamed_code(code):
    return 'ОКР-' + code[len(OLD_CODE_PREFIX):] if code.startswith(OLD_CODE_PREFIX) else None


@login_required
def district_detail(request, code):
    if renamed_code(code):
        url = reverse('district_detail', kwargs={'code': renamed_code(code)})
        return redirect(url + ('?' + request.GET.urlencode() if request.GET else ''), permanent=True)
    scope = scope_for(request)
    district = get_or_404(code, scope)
    tab = request.GET.get('tab', 'summary')
    if tab not in TABS:
        tab = 'summary'
    category = request.GET.get('category', '')[:120]
    ctx = {'d': district, 'tab': tab, 'category': category, 'ladder_rest': ladder_rest(None)}
    if tab == 'summary':
        ctx.update(formations=repo.formations(code, scope), strength=repo.strength(code, scope),
                   regions=repo.regions(code, scope))
    elif tab == 'equipment':
        q = request.GET.get('q', '')[:90]
        rows, total = repo.equipment(code, scope, category=category, term=q, page=request.GET.get('page'))
        ctx.update(rows=rows, q=q, categories=repo.equipment_categories(code, scope), pager=pager(request.GET.get('page'), total),
                   query=urlencode({'tab': tab, 'category': category, 'q': q}) + '&')
    elif tab == 'people':
        ctx.update(people_context(request, scope, district=district['district_code']))
    else:
        deficit = request.GET.get('deficit') == '1'
        rows, total = repo.supply(code, scope, category=category, only_deficit=deficit, page=request.GET.get('page'))
        ctx.update(rows=rows, deficit=deficit, categories=repo.supply_categories(code, scope), pager=pager(request.GET.get('page'), total),
                   query=urlencode({'tab': tab, 'category': category, **({'deficit': '1'} if deficit else {})}) + '&')
    return render(request, 'catalog/district.html', ctx)


@login_required
def formation_detail(request, code, fcode):
    if renamed_code(code):
        return redirect('formation_detail', code=renamed_code(code), fcode=fcode, permanent=True)
    scope = scope_for(request)
    district = get_or_404(code, scope)
    formation = repo.get_formation(fcode, scope)
    if not formation or formation['district_code'] != district['district_code']:
        raise Http404('Соединение не найдено')
    tab = unit_tab(request)
    return render(request, 'catalog/formation.html', {
        'd': district, 'f': formation, 'nav': repo.subunit_nav(repo.subunits(fcode, scope)), 'tab': tab,
        'ladder_rest': ladder_rest('бригада'),
        **unit_tab_data(tab, fcode, scope, own=False, request=request),
    })


@login_required
def subunit_detail(request, code, fcode, scode):
    if renamed_code(code):
        return redirect('subunit_detail', code=renamed_code(code), fcode=fcode, scode=scode, permanent=True)
    scope = scope_for(request)
    district = get_or_404(code, scope)
    formation = repo.get_formation(fcode, scope)
    if not formation or formation['district_code'] != district['district_code']:
        raise Http404('Соединение не найдено')
    nav = repo.subunit_nav(repo.subunits(fcode, scope), scode)
    if not nav:
        raise Http404('Подразделение не найдено')
    tab = unit_tab(request, nav['node']['level'])
    return render(request, 'catalog/subunit.html', {
        'd': district, 'f': formation, 'nav': nav, 'u': nav['node'], 'tab': tab,
        'ladder_rest': ladder_rest(nav['node']['level']),
        **unit_tab_data(tab, scode, scope, own=True, request=request),
    })


LADDER = ('бригада', 'батальон', 'рота', 'взвод', 'отделение')


def ladder_rest(level):
    """Уровни ниже текущего — пустые ступени «лестницы» на странице (округ -> бригада -> … -> отделение)."""
    return list(LADDER[LADDER.index(level) + 1:]) if level in LADDER else list(LADDER)


UNIT_TABS = ('summary', 'staff', 'people', 'equipment')


PEOPLE_FILTERS = {'cat': (('', 'Все'), ('офицеры', 'Офицеры'), ('сержанты', 'Сержанты'), ('солдаты', 'Солдаты')),
                  'srv': (('', 'Любая служба'), ('срочная воинская служба', 'Срочная'), ('по контракту', 'Контракт'))}


def people_context(request, scope, code='', district=''):
    """Вкладка «Личный состав»: поиск, фильтры по категории и виду службы, страницы."""
    get = request.GET if request else {}
    q, cat, srv = (get.get('q', '') or '')[:60], get.get('cat', ''), get.get('srv', '')
    page = get.get('page') or 1
    rows, total = repo.unit_people(code, scope, page, q, category=cat, service=srv, district=district)
    current = {'tab': 'people', 'q': q, 'cat': cat, 'srv': srv}
    filters = []
    for key, options in PEOPLE_FILTERS.items():
        filters.append([{'label': label, 'active': current[key] == value,
                         'url': '?' + urlencode({k: v for k, v in {**current, key: value}.items() if v})}
                        for value, label in options])
    return {'people': rows, 'q': q, 'cat': cat, 'srv': srv, 'people_filters': filters, 'pager': pager(page, total),
            'people_total': total, 'query': urlencode({k: v for k, v in current.items() if v}) + '&'}


def unit_tab(request, level=None):
    """Вкладка из адреса. У отделения сводки нет (это нижний уровень) — сразу «Личный состав»."""
    default = 'people' if level == 'отделение' else 'summary'
    tab = request.GET.get('tab', default)
    if tab not in UNIT_TABS or (level == 'отделение' and tab == 'summary'):
        return default
    return tab


def unit_tab_data(tab, code, scope, own, request=None):
    """Данные вкладок бригады и подразделения: должности (своё управление и все подчинённые), люди и техника."""
    if tab == 'people':
        return people_context(request, scope, code=code)
    if tab == 'staff':
        return {'own_staff': repo.unit_staff(code, scope, own_only=True) if own else [],
                'staff': repo.unit_staff(code, scope)}
    if tab == 'equipment':
        return {'equipment': repo.unit_equipment(code, scope)}
    return {'sources': repo.norm_sources()}


@login_required
def person_detail(request, number):
    """Карточка вымышленного военнослужащего. Чужой округ — 404, как будто человека нет."""
    scope = scope_for(request)
    person = repo.get_person(number, scope)
    if not person:
        raise Http404('Человек не найден')
    return render(request, 'catalog/person.html', {
        'p': person, 'd': repo.get_district(person['district_code'], scope),
        'f': repo.get_formation(person['formation_code'], scope),
    })


@login_required
def items(request):
    q = request.GET.get('q', '')[:90]
    rows, total = repo.item_catalog(q, page=request.GET.get('page'))
    return render(request, 'catalog/items.html', {'rows': rows, 'q': q, 'pager': pager(request.GET.get('page'), total),
                                                  'query': urlencode({'q': q}) + '&'})


@login_required
def item_detail(request, sname):
    item = repo.get_item(sname[:200])
    if not item:
        raise Http404('Образец не найден')
    return render(request, 'catalog/item.html', {
        'item': item, 'specs': repo.item_specs(item['item_sname']),
        'holders': repo.item_holders(item['item_sname'], scope_for(request)),
    })


TITLE_LEN = 40


def chat_title(question):
    """Временное название чата — начало первого вопроса, обрезанное по целому слову.
    Потом его заменяет короткое название от модели (assistant_title)."""
    text = ' '.join(str(question).split())
    if len(text) <= TITLE_LEN:
        return text
    cut = text[:TITLE_LEN - 1].rsplit(' ', 1)[0].rstrip(' ,.;:!?—-')
    return (cut or text[:TITLE_LEN - 1]) + '…'


def limit_json(status):
    return {'limit': status['limit'], 'used': status['used'], 'left': status['left'], 'reached': status['reached']}


def wants_json(request):
    return request.headers.get('X-Requested-With') == 'fetch'


@login_required
@require_http_methods(['GET', 'POST'])
def assistant(request, chat_id=None):
    """Чат с помощником: без chat_id — новый чат, иначе — сохранённый чат пользователя."""
    chat = get_object_or_404(AssistantChat, pk=chat_id, user=request.user) if chat_id else None
    if request.method == 'POST':
        return assistant_send(request, chat)
    return render(request, 'catalog/assistant.html', {
        'chat': chat, 'chat_messages': chat.messages.all() if chat else [],
        'chats': request.user.assistant_chats.all()[:CHAT_LIST_LEN],
        'districts': repo.list_districts(scope_for(request)), 'examples': CHAT_EXAMPLES,
        'limit': limit_status(request.user),
    })


def assistant_send(request, chat):
    question = (request.POST.get('question') or '').strip()
    if not question:
        if wants_json(request):
            return JsonResponse({'error': 'Введите вопрос.'}, status=400)
        return redirect('assistant_chat', chat.pk) if chat else redirect('assistant')
    status = limit_status(request.user)
    if status['reached']:                     # модель не вызывается, чат не создаётся
        text = LIMIT_TEXT.format(limit=status['limit'])
        if wants_json(request):
            return JsonResponse({'error': text, 'limit': limit_json(status)}, status=429)
        messages.warning(request, text)
        return redirect('assistant_chat', chat.pk) if chat else redirect('assistant')
    history = []
    if chat:
        history = [(m.question, m.text) for m in chat.messages.order_by('-created_at', '-id')[:CHAT_CONTEXT]][::-1]
    result = assistant_answer(request.user, scope_for(request), question, history=history)
    created = chat is None
    if created:
        chat = AssistantChat.objects.create(user=request.user, title=chat_title(question))
    message = chat.messages.create(question=result['question'] or question[:500], text=result['text'],
                                   tables=result['tables'], calls=result['calls'],
                                   mode=(result['mode'] or '')[:40], ok=result['ok'])
    chat.save(update_fields=['updated_at'])
    url = reverse('assistant_chat', args=[chat.pk])
    if wants_json(request):
        return JsonResponse({'chat_id': chat.pk, 'url': url, 'title': chat.title, 'created': created,
                             'send_url': url, 'title_url': reverse('assistant_title', args=[chat.pk]),
                             'limit': limit_json(limit_status(request.user)),
                             'nav_html': render_to_string('catalog/_chat_nav_item.html',
                                                          {'c': chat, 'current': chat}, request) if created else '',
                             'html': render_to_string('catalog/_chat_message.html', {'m': message}, request)})
    return redirect(url)


@login_required
@require_POST
def assistant_title(request, chat_id):
    """Короткое название от модели. Вызывается страницей после первого ответа, поэтому ответ не ждёт названия.
    Переименованный пользователем чат не трогаем."""
    chat = get_object_or_404(AssistantChat, pk=chat_id, user=request.user)
    first = chat.messages.first()
    if first and chat.title == chat_title(first.question):
        title = suggest_title(first.question, first.text)
        if title:
            chat.title = title[:120]
            chat.save(update_fields=['title'])
    return JsonResponse({'title': chat.title})


@login_required
@require_POST
def assistant_rename(request, chat_id):
    chat = get_object_or_404(AssistantChat, pk=chat_id, user=request.user)
    title = ' '.join((request.POST.get('title') or '').split())[:120]
    if title:
        chat.title = title
        chat.save(update_fields=['title', 'updated_at'])
    if wants_json(request):
        return JsonResponse({'title': chat.title})
    return redirect('assistant_chat', chat.pk)


@login_required
@require_POST
def assistant_delete(request, chat_id):
    chat = get_object_or_404(AssistantChat, pk=chat_id, user=request.user)
    chat.delete()
    current = request.POST.get('current')                 # удалили не открытый чат — остаёмся, где были
    if current and current != str(chat_id) and current.isdigit() \
            and AssistantChat.objects.filter(pk=current, user=request.user).exists():
        return redirect('assistant_chat', int(current))
    return redirect('assistant')


@login_required
@require_http_methods(['GET', 'POST'])
def manage_grants(request):
    if not UserRole.objects.filter(user=request.user, role='manager').exists() or request.user.is_superuser:
        return HttpResponseForbidden('Недостаточно прав')
    scope = scope_for(request)
    viewers = get_user_model().objects.filter(demo_role__role='viewer', is_active=True, is_superuser=False).exclude(pk=request.user.pk).order_by('username')
    if request.method == 'POST':
        try:
            target = viewers.get(pk=request.POST.get('target_id'))
            assign_grant(request.user, target, request.POST.get('root_code', '')[:128], request.POST.get('action', ''))
            messages.success(request, 'Права обновлены')
        except (ValueError, TypeError, get_user_model().DoesNotExist, GrantDenied):
            messages.error(request, 'Операция отклонена: проверь пользователя, округ и свои права')
        return redirect('manage_grants')
    visible = UnitGrant.objects.filter(user__in=viewers, root_code__in=scope, is_active=True).select_related('user').order_by('user__username', 'root_code')[:120]
    audit = GrantAudit.objects.filter(actor=request.user).select_related('target', 'target__demo_role')[:20]
    return render(request, 'catalog/grants.html', {
        'viewers': viewers, 'visible_grants': visible,
        'districts': repo.list_districts(scope), 'audit': audit, 'users': user_rows(request.user),
        'form': request.session.pop('user_form', {}), 'form_errors': request.session.pop('user_form_errors', {}),
    })


def user_rows(actor):
    """Пользователи для таблицы на странице прав: ФИО, логин, роль, округа, можно ли управлять."""
    rows = []
    users = get_user_model().objects.filter(is_superuser=False).select_related('demo_role').order_by('-is_active', 'username')
    grants = {}
    for g in UnitGrant.objects.filter(is_active=True).order_by('root_code'):
        grants.setdefault(g.user_id, []).append(g.root_code)
    for u in users:
        role = getattr(u, 'demo_role', None)
        rows.append({'user': u, 'name': role.full_name if role and role.full_name else '—',
                     'role': role.get_role_display() if role else '—', 'districts': grants.get(u.pk, []),
                     'manageable': can_manage(actor, u)})
    return rows


def is_manager(user):
    return UserRole.objects.filter(user=user, role='manager').exists() and not user.is_superuser


@login_required
@require_POST
def user_create(request):
    if not is_manager(request.user):
        return HttpResponseForbidden('Недостаточно прав')
    data = request.POST
    try:
        user = create_user(request.user, data.get('full_name', '')[:150], data.get('username', '')[:30], data.get('role', ''),
                           data.get('password', ''), data.getlist('districts'))
        messages.success(request, f'Пользователь {user.username} создан. Передайте ему логин и пароль лично.')
    except ValidationError as exc:
        request.session['user_form'] = {k: data.get(k, '') for k in ('full_name', 'username', 'role')} | {'districts': data.getlist('districts')}
        request.session['user_form_errors'] = exc.message_dict
        messages.error(request, 'Пользователь не создан: исправьте поля формы.')
    except GrantDenied:
        messages.error(request, 'Операция отклонена.')
    return redirect(reverse('manage_grants') + '#users')


@login_required
@require_POST
def user_toggle(request, pk):
    if not is_manager(request.user):
        return HttpResponseForbidden('Недостаточно прав')
    target = get_object_or_404(get_user_model(), pk=pk)
    try:
        set_user_active(request.user, target, request.POST.get('active') == '1')
        messages.success(request, f'Доступ пользователя {target.username} {"включён" if target.is_active else "отключён"}.')
    except GrantDenied:
        messages.error(request, 'Этим пользователем управлять нельзя.')
    return redirect(reverse('manage_grants') + '#users')
