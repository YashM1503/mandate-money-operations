"""Create local credentials once; writes secrets to restricted files, never source control."""
import hashlib,json,os,secrets,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from mandate.env import load_runtime_env
load_runtime_env()
data=Path(os.getenv('MANDATE_DATA_DIR',str(root/'data')));data.mkdir(parents=True,exist_ok=True)
config=data/'config.json'
if config.exists(): raise SystemExit('Existing configuration retained. See data/demo-credentials.txt or your secret manager.')
users={};passwords=[]
for role in ('analyst','controller','auditor'):
    password=secrets.token_urlsafe(18);salt=secrets.token_hex(16)
    users[role]=dict(role=role,salt=salt,hash=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),600000).hex())
    passwords.append(f'{role}: {password}')
for path,text in [(config,json.dumps(dict(signing_key=secrets.token_hex(32),users=users),indent=2)),(data/'demo-credentials.txt','\n'.join(passwords)+'\n')]:
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:f.write(text)
print('Created protected local configuration. Read data/demo-credentials.txt privately to sign in. Never commit or share it.')
