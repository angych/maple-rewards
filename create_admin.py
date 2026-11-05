import getpass,secrets,sqlite3,sys
from server import DB,pwdhash
email=input('Correo del administrador: ').strip().lower()
name=input('Nombre: ').strip()
password=getpass.getpass('Contraseña (mínimo 10 caracteres): ')
if len(password)<10 or '@' not in email or not name:sys.exit('Datos inválidos')
salt=secrets.token_hex(16)
with sqlite3.connect(DB) as c:
 try:c.execute('INSERT INTO users(id,name,email,password_hash,salt,role,qr_token) VALUES(?,?,?,?,?,?,?)',(secrets.token_hex(12),name,email,pwdhash(password,salt),salt,'admin',secrets.token_urlsafe(24)))
 except sqlite3.IntegrityError:sys.exit('El correo ya existe')
print('Administrador creado')
