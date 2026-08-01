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
- Métodos `build_navigation_headers()` y `build_graphql_headers()`.
- Fetch Metadata coherente con navegación y `fetch` same-origin.
- Importación opcional de headers propios capturados en DevTools.
- Comando `headers` para revisar los headers sin enviar solicitudes.
- Inicio de sesión y creación de una cuenta propia.
- Comando `probe` para diagnosticar únicamente el GET inicial.
- Detección informativa de posibles Fastly Client Challenges.
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

## Revisar los headers generados

```powershell
python .\base_client.py headers
```

El POST GraphQL genera, entre otros:

```http
Accept: application/json, text/plain, */*
Content-Type: application/json
Origin: https://www.abercrombie.com
Referer: https://www.abercrombie.com/shop/wd-es
Sec-Fetch-Site: same-origin
Sec-Fetch-Mode: cors
Sec-Fetch-Dest: empty
Priority: u=1, i
```

`requests` administra automáticamente `Host`, `Content-Length`, `Cookie`,
`Connection` y `Accept-Encoding`; no deben copiarse manualmente.

## Importar headers propios desde DevTools

AberCr acepta JSON, una lista de headers exportada desde HAR o texto con una
línea `Nombre: valor` por header:

```text
Sec-CH-UA: "Chromium";v="138", "Not=A?Brand";v="24"
Sec-CH-UA-Mobile: ?0
Sec-CH-UA-Platform: "Windows"
DNT: 1
Sec-GPC: 1
```

Revisa primero cuáles se aplicarán:

```powershell
python .\base_client.py headers --browser-headers .\browser_headers.txt
```

Luego úsalos en el flujo:

```powershell
python .\base_client.py signin `
  --email usuario@example.com `
  --browser-headers .\browser_headers.txt
```

El importador ignora `Cookie`, `Host`, `Content-Length`, `Connection`,
`Accept-Encoding`, `Authorization`, `User-Agent`, `Origin`, `Referer`,
`Content-Type` y `X-Bug-Bounty`. Esos valores los administra el cliente o la
sesión.

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
    print(client.build_navigation_headers())
    print(client.build_graphql_headers())

    # Opcional: headers propios copiados desde DevTools.
    client.load_browser_headers("browser_headers.txt")

    result = client.sign_in(
        email="usuario@example.com",
        password="CONTRASENA",
    )
    print(result)
```

## Por qué puede continuar el HTTP 403

El HTML de la tienda expone `/anf/auth` como `Fastly Challenge`. Los Client
Challenges pueden ejecutar JavaScript y emitir cookies de desafío. Una sesión
de `requests` conserva cookies recibidas, pero no ejecuta JavaScript; por eso
agregar headers mejora la fidelidad de la petición, pero no garantiza eliminar
el 403.

AberCr no genera, falsifica ni evade tokens de CAPTCHA, WAF, MFA o Client
Challenge. Cuando detecta indicios del desafío, lo informa en `probe` y añade
contexto al error 403.

## Pruebas

```powershell
python -m unittest discover -s tests -v
python -m py_compile base_client.py example.py abercr/*.py
```

Las pruebas simulan respuestas HTTP y GraphQL; no crean cuentas ni intentan
autenticarse contra el servicio real.

Usa únicamente cuentas propias y acciones permitidas por el alcance y las
reglas vigentes del programa.
