from pathlib import Path
import secrets
p=Path(__file__).resolve().parent.parent/'.env'
if p.exists():
    print('Existing .env left unchanged.')
else:
    p.write_text('POSTGRES_PASSWORD='+secrets.token_urlsafe(32)+'\nAPP_READER_PASSWORD='+secrets.token_urlsafe(32)+'\n',encoding='utf-8')
    p.chmod(0o600)
    print('.env created with random local secrets. Keep private.')
