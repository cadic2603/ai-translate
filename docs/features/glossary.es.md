---
description: Gestiona conjuntos de glosarios personalizados para aplicar terminología consistente en las traducciones — importar/exportar CSV, alcance por par de idiomas, priorizar por proyecto.
---

# Glosario

Bloquea términos específicos a traducciones específicas en cada
trabajo de traducción. Útil para nombres de marca, terminología de
producto, jerga técnica o nombres de personajes que quieres mantener
consistentes.

## Cómo funciona

Un glosario es una lista de pares (término origen, término destino)
agrupados en un **conjunto**. Cuando activas un conjunto, cada llamada
LLM en la app recibe las entradas relevantes inyectadas en el prompt —
así que el LLM ve "usa 'OpenAI' para 'OpenAI', no '开放AI'" antes de traducir.

Múltiples conjuntos pueden estar activos a la vez. Sólo las entradas
cuyo origen o destino aparece en el texto del batch se añaden al
prompt (compresión por llamada), así que un glosario de 5.000
entradas se mantiene barato en tokens.

## Paso a paso

1. Haz clic en **Glosario** en la barra lateral.
2. Haz clic en **Nuevo conjunto** (`Ctrl+N`) y dale un nombre (p. ej. "Proyecto Acme").
3. Con el conjunto seleccionado a la izquierda, el panel derecho muestra sus entradas.
4. Haz clic en **Añadir** para crear una nueva entrada. Rellena:
    - **Origen** — el término original
    - **Destino** — la traducción a imponer
    - Opcionalmente un comentario / nota
5. Repite para cada término.
6. Marca la casilla **Activo** en el nombre del conjunto para activarlo.

## Activar / desactivar conjuntos

La casilla **Activo** junto al nombre de cada conjunto controla si
sus entradas se inyectan en los prompts LLM. Puedes dejar 50 conjuntos
inactivos en almacenamiento y sólo activar los 2 que necesitas para
el proyecto actual.

## Importar / Exportar (CSV)

- **Exportar** — selecciona un conjunto, haz clic en **Exportar** →
  guarda como `.csv`. Dos columnas: `source`, `target` (UTF-8,
  separado por comas, escape RFC 4180).
- **Importar** — haz clic en **Importar** → elige un `.csv` → elige
  un conjunto destino (existente o nuevo). En origen duplicado
  obtendrás un prompt reemplazar-o-omitir.

El formato CSV hace round-trip, así que un Exportar → editar en
Excel → Importar es seguro.

## Búsqueda y filtrado

`Ctrl+F` enfoca la barra de búsqueda. Escribe cualquier subcadena
y las entradas (y la lista de conjuntos) se filtran a coincidencias;
la subcadena coincidente se resalta. Limpiar la búsqueda restaura la
lista completa.

La búsqueda es **insensible a acentos e insensible a mayúsculas** —
`cafe` encuentra `café` y viceversa.

## Edición en sitio

Haz clic en cualquier celda para editar. Pulsa `Tab` para moverte a
la siguiente celda. Pulsa `Esc` para revertir. Auto-guardado se
dispara cuando haces clic fuera de la fila. Origen o destino vacíos
revierten la fila en lugar de guardar una entrada inválida.

## Eliminar

- **Eliminar una entrada** — selecciónala, pulsa `Supr`. Verás un
  diálogo de confirmación.
- **Eliminar todo un conjunto** — selecciona el conjunto, pulsa
  `Supr`. El diálogo muestra el conteo de entradas en cascada para
  que sepas qué estás eliminando.

## Atajos

| Atajo | Acción |
|---|---|
| `Ctrl+N` | Nuevo conjunto |
| `Ctrl+F` | Foco en búsqueda |
| `Supr` | Eliminar entrada / conjunto seleccionado |

## Trucos

!!! tip "Alcance por conjunto"
    Un conjunto es un agrupamiento *lógico*. Agrupa por proyecto, por
    cliente, por dominio (médico / legal / gaming) — lo que tenga
    sentido. Activa sólo los conjuntos relevantes al trabajo actual.

!!! tip "El glosario no anula la traducción"
    Al LLM se le instruye usar las entradas del glosario, pero sigue
    siendo una pista — traducciones extremadamente forzadas y
    incómodas todavía pueden surgir. Usa pares simples
    `término → traducción` en lugar de oraciones completas.
