# Guia del Usuario - Cloud Control Panel

## Que es Cloud Control Panel?

Es un panel web que te permite controlar tus servidores (instancias EC2) desde
el navegador sin necesidad de entrar a la consola de AWS.

---

## 1. Ingresar al Panel

1. Abre la URL del panel que te dio tu administrador
2. Ingresa tu API Key (te la da el admin)
3. Marca "Recordar en este dispositivo" si es tu equipo personal
4. Click en Ingresar

Si la key es invalida veras un mensaje de error y deberas pedirle
una nueva a tu administrador.

---

## 2. Pantalla de Cuentas

Si tu organizacion tiene multiples cuentas AWS, veras una lista de las
cuentas a las que tienes acceso.

- Haz click en una cuenta para ver sus instancias
- Si solo tienes acceso a 1 cuenta, entraras directamente

---

## 3. Pantalla de Instancias

Aqui ves todas las instancias de la cuenta seleccionada.

### Estados posibles

| Indicador | Estado | Significado |
|-----------|--------|-------------|
| Verde | running | La instancia esta encendida y funcionando |
| Rojo | stopped | La instancia esta apagada |
| Amarillo | pending | La instancia se esta encendiendo |
| Amarillo | stopping | La instancia se esta apagando |

### Grupos

Si hay instancias agrupadas, veras una seccion "Grupos" arriba con botones:
- Encender: Enciende TODAS las instancias del grupo en orden
- Apagar: Apaga TODAS las instancias del grupo en orden

### Instancias individuales

Haz click en una instancia para ver su detalle y acciones.

---

## 4. Pantalla de Detalle

Aqui ves el estado completo de una instancia y puedes realizar acciones.

### Informacion visible

- IP Publica: Direccion IP actual (cambia cada vez que se enciende)
- Uptime: Tiempo que lleva encendida
- Instance ID: Identificador unico de la instancia
- Descripcion: Texto informativo sobre la instancia

### Acciones

| Boton | Accion |
|-------|--------|
| Encender | Inicia la instancia (tarda ~30s en estar disponible) |
| Apagar | Detiene la instancia (pide confirmacion) |
| Actualizar | Ejecuta actualizacion del software en la instancia |
| Dashboard | Abre el dashboard de la instancia en nueva pestana |

### Notas

- Los botones se habilitan/deshabilitan segun el estado actual
- El estado se refresca automaticamente cada 30 segundos
- Puedes refrescar manualmente con el boton de recarga en la esquina superior

---

## 5. Actividad

En la parte inferior de la pantalla de detalle hay un log de actividad
que muestra las acciones que realizaste durante la sesion actual.

---

## 6. Preguntas Frecuentes

P: La instancia dice "running" pero no puedo acceder al dashboard
R: Puede tardar 1-2 minutos despues de encender para que los servicios esten listos.

P: Encendi la instancia pero sigue en "pending"
R: Es normal, el encendido tarda 20-60 segundos. Se actualizara automaticamente.

P: No veo una cuenta que deberia ver
R: Tu API Key puede no tener permisos para esa cuenta. Contacta a tu admin.

P: El boton "Dashboard" esta deshabilitado
R: Solo funciona cuando la instancia esta en estado "running" y tiene dashboard configurado.

P: Como cierro sesion?
R: Click en el icono de salida en la esquina superior derecha.

P: Olvide mi API Key
R: Contacta a tu administrador para que te la proporcione nuevamente.
