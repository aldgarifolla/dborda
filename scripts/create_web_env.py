from pathlib import Path
import secrets

p = Path(__file__).resolve().parent.parent / '.env.web'
if p.exists():
    print('.env.web уже существует: оставлен без изменений.')
else:
    p.write_text('WEB_AUTH_PASSWORD=' + secrets.token_urlsafe(36) + '\n'
                 + 'DJANGO_SECRET_KEY=' + secrets.token_urlsafe(48) + '\n', encoding='utf-8')
    p.chmod(0o600)
    print('.env.web создан. Не публикуй файл и пароль.')
