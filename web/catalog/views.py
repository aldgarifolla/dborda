from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from . import repository as repo
from .models import UnitGrant, UserRole, GrantAudit
from .services import assign_grant, GrantDenied


def scope_for(request):
    return repo.allowed_codes(request.user)


def get_or_404(code, scope):
    unit = repo.get_unit(code, scope)
    if not unit:
        raise Http404('Подразделение не найдено')
    return unit


@login_required
def dashboard(request):
    scope = scope_for(request)
    return render(request, 'catalog/dashboard.html', {
        'counts': repo.totals(scope), 'units': repo.list_units(scope, limit=18),
        'role': getattr(getattr(request.user, 'demo_role', None), 'role', 'viewer'),
        'accessible': len(scope),
    })


@login_required
def unit_list(request):
    scope = scope_for(request)
    q = request.GET.get('q', '')[:90]
    return render(request, 'catalog/units.html', {
        'units': repo.list_units(scope, q), 'q': q, 'total_access': len(scope),
    })


@login_required
def unit_detail(request, code):
    scope = scope_for(request)
    unit = get_or_404(code, scope)
    subtree = repo.subtree(scope, code)
    include = request.GET.get('desc') == '1'
    selected = subtree if include else [code]
    return render(request, 'catalog/detail.html', {
        'unit': unit, 'children': repo.unit_children(scope, code),
        'position_rows': repo.positions(selected, limit=65), 'holding_rows': repo.holdings(selected, limit=65),
        'totals': repo.totals(selected), 'desc': include, 'total_children': max(len(subtree)-1, 0),
    })


@login_required
def items(request):
    q = request.GET.get('q', '')[:90]
    return render(request, 'catalog/items.html', {'rows': repo.item_catalog(q), 'q': q})


@login_required
def workbook(request):
    scope = scope_for(request)
    kind = request.GET.get('kind', 'positions')
    if kind not in repo.WORKBOOK_VIEWS:
        kind = 'positions'
    q = request.GET.get('q', '')[:90]
    return render(request, 'catalog/workbook.html', {
        'rows': repo.workbook_rows(scope, kind, q), 'kind': kind, 'q': q,
    })


@login_required
@require_http_methods(['GET', 'POST'])
def assistant(request):
    scope = scope_for(request)
    available = repo.list_units(scope, limit=100)
    response = None
    chosen = ''
    message = ''
    if request.method == 'POST':
        chosen = request.POST.get('unit_code', '')[:128]
        message = request.POST.get('question', '')[:500].strip()
        unit = get_or_404(chosen, scope)
        if not message:
            response = {'title': 'Введите вопрос', 'text': 'Например: сколько штатных позиций?'}
        else:
            q = message.casefold()
            descendants = any(w in q for w in ('подчин', 'включая', 'вместе', 'всех', 'потомк', 'барлық', 'қоса'))
            codes = repo.subtree(scope, chosen) if descendants else [chosen]
            info = repo.totals(codes)
            coverage = 'с разрешёнными дочерними подразделениями' if descendants else 'только в выбранном подразделении'
            if any(w in q for w in ('имущ', 'техник', 'материал', 'жабдық')):
                records = repo.holdings(codes, limit=10)
                response = {
                    'title': f'Имущество — {unit["short_name"]}',
                    'text': f'Учебных записей имущества: {info["holdings_rows"]} ({coverage}).',
                    'rows': [f'{x["item_sname"]}: {x["model_qty"]} {x["unit_measure"] or ""}' for x in records],
                    'source': 'registry_api.holdings',
                }
            elif any(w in q for w in ('должност', 'позици', 'штат', 'лауазым')):
                response = {
                    'title': f'Штатные позиции — {unit["short_name"]}',
                    'text': f'В учебной модели найдено {info["positions"]} штатных позиций ({coverage}).',
                    'source': 'registry_api.staff_positions',
                }
            elif any(w in q for w in ('человек', 'численн', 'людей', 'сколько', 'адам', 'қанша')):
                response = {
                    'title': 'Уточнение показателя',
                    'text': f'Модельных штатных позиций: {info["positions"]} ({coverage}); '
                            f'связанных модельных карточек: {info["linked_model_persons"]}. '
                            'Это учебные показатели, не оперативная численность.',
                    'source': 'registry_api.staff_positions',
                }
            else:
                response = {
                    'title': 'Поддерживаемые вопросы',
                    'text': 'Спроси «Сколько штатных позиций?» или «Какое имущество?» '
                            'Добавь «с подчинёнными» для включения доступных дочерних подразделений. '
                            'Настоящая LLM пока не подключена.',
                }
    return render(request, 'catalog/assistant.html', {
        'available': available, 'response': response, 'chosen': chosen, 'message': message,
    })


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
            messages.error(request, 'Операция отклонена: проверь пользователя, подразделение и свои права')
        return redirect('manage_grants')
    visible = UnitGrant.objects.filter(user__in=viewers, root_code__in=scope, is_active=True).select_related('user').order_by('user__username', 'root_code')[:120]
    audit = GrantAudit.objects.filter(actor=request.user).select_related('target')[:20]
    return render(request, 'catalog/grants.html', {
        'viewers': viewers, 'visible_grants': visible,
        'units': repo.list_units(scope, limit=200), 'audit': audit,
    })
