# AberCr

Cliente Python orientado a objetos para pruebas autorizadas de las operaciones
GraphQL `LOGIN_MUTATION` y `CREATE_USER_MUTATION`.

## Identificación de investigación

Todas las solicitudes incluyen:

```http
User-Agent: Browser/immroa/0.0.1 (HackerOne User, https://hackerone.com/immroa?type=user)
X-Bug-Bounty: HackerOne
```

## Funciones

- Clase `Config` para endpoint, tienda, tiempo de espera, TLS y diagnósticos.
- Clase `AbercrombieClient` con sesión y cookies persistentes.
- Inicio de sesión y creación de una cuenta propia.
- Comando `probe` para diagnosticar únicamente el GET inicial.
- Captura de respuestas 403, HTML y JSON inválido en `diagnostics/`.
- Reference ID extraído automáticamente de respuestas del edge/WAF.
- Validación local de correo, nombres y fecha de nacimiento.
- Reintentos limitados solo para el GET inicial; los POST no se repiten.
- Pruebas unitarias sin enviar solicitudes reales.

## Instalación

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Diagnóstico inicial

```powershell
python .\base_client.py probe
```

## Inicio de sesión

La contraseña se solicita de forma oculta:

```powershell
python .\base_client.py signin --email usuario@example.com
```

También puede definirse temporalmente en una variable de entorno:

```powershell
$env:ABERCR_PASSWORD="contraseña"
python .\base_client.py signin --email usuario@example.com
Remove-Item Env:ABERCR_PASSWORD
```

## Crear usuario

```powershell
python .\base_client.py create-user `
  --email usuario@example.com `
  --first-name IM `
  --last-name MR `
  --phone "+18095551234" `
  --accept-legal
```

Las comunicaciones comerciales están desactivadas salvo que se envíe
`--marketing-opt-in` explícitamente.

## Uso como clase

```python
from base_client import AbercrombieClient, Config

with AbercrombieClient(Config()) as client:
    result = client.sign_in(
        email="usuario@example.com",
        password="CONTRASENA",
    )
    print(result)
```

## Pruebas

```powershell
python -m unittest discover -s tests -v
python -m py_compile base_client.py example.py
```

Las pruebas simulan respuestas HTTP y GraphQL; no crean cuentas ni intentan
autenticarse contra el servicio real.

## HTTP 403

Un 403 con HTML indica que la solicitud fue rechazada antes de completar
GraphQL. El cliente guarda el cuerpo recibido y el Reference ID, pero no evade
CAPTCHA, WAF, MFA ni otros controles.

Usa únicamente cuentas propias y acciones permitidas por el alcance y las
reglas vigentes del programa.
