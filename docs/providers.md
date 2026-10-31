# Lecturas de uso

El diseño admite dos ventanas, corta y semanal. Se muestra porcentaje **utilizado**. El proveedor oficial de Codex devuelve minutos y reinicios; en esta versión su ventana corta es de 300 minutos (5 h). La etiqueta 5 h describe esa ventana, no un temporizador fijo del HUD.

## Claude: archivo local

El archivo predeterminado es `~/.config/orbita-hud/claude-usage.json`. También puede configurarse `usage.claude_file`. Formato:

```json
{
  "observed_at": 1793389320,
  "session": {"used_percent": 53, "resets_at": 1793400000},
  "weekly": {"used_percent": 26, "resets_at": 1793800000}
}
```

Estos números son **un ejemplo de formato**, no datos actuales. `observed_at` y `resets_at` usan segundos Unix. También se aceptan `five_hour`/`seven_day`, `utilization` y reinicios ISO 8601 con zona horaria.

Para importar una lectura exportada por una herramienta de confianza:

```bash
python3 ~/.conky/Orbita-HUD/runner.py import-claude /ruta/lectura.json
```

La importación conserva la fecha real de observación. No convierte una lectura antigua en una lectura vigente. La actualización llega en el siguiente ciclo (por defecto 180 s).

## Proveedor local opcional

`claude_command` es una **lista de argumentos**, ejecutada sin intérprete de shell. Debe devolver el mismo JSON por stdout en menos de 12 segundos. Configúralo únicamente con un programa de tu confianza que ya tenga acceso legítimo a tu cuenta. El HUD no necesita ni recibe tokens de ese programa.

```toml
[usage]
claude_command = ["/ruta/mi-exportador", "--json"]
```

Esta interfaz es extensible, pero no se distribuye un exportador automático de Claude. Consulta los [límites explicados por Anthropic](https://support.claude.com/en/articles/11647753-how-do-usage-and-length-limits-work) y la página de uso de tu cuenta para conocer las ventanas que realmente te aplican.

## Codex

El proceso lanza el CLI oficial en modo App Server, realiza `initialize`, notifica `initialized` y solicita `account/rateLimits/read`; termina el proceso auxiliar al recibir respuesta. No crea conversaciones. Si se configura `codex_socket`, usa el proxy oficial hacia ese socket. La salida completa del servicio se descarta: únicamente se conservan porcentajes, reinicios y fecha de lectura.

Las notificaciones y errores no se imprimen con datos de cuenta. Si falla una consulta, se mantiene la última lectura solo hasta su caducidad. Ningún fallo se presenta como cuota disponible al 100%.
