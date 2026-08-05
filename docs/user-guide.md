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

## 3. Pantalla de Cuenta (Grupos e Instancias)

Al entrar a una cuenta ves dos secciones:

### Grupos

Si hay instancias agrupadas, aparecen como tarjetas con un color lateral.
Haz click en un grupo para:
- Ver las instancias que lo componen
- Encender o apagar todo el grupo con un solo boton

### Instancias independientes

Debajo de los grupos aparecen las instancias que no pertenecen a ningun grupo.
Haz click en una para ver su detalle y acciones.

### Boton de Configuracion (⚙️)

Si tienes permisos, veras un icono de engranaje en la esquina superior derecha.
Al hacer click se abre un panel lateral con:

- **Programacion**: Horarios automaticos de encendido/apagado (si tienes permiso)
- **Notificaciones**: Canales de alerta configurados (solo admin)
- **Costos estimados**: Gasto acumulado por instancia (solo admin)

---

## 4. Pantalla de Grupo

Al hacer click en un grupo ves:
- Botones para encender/apagar todo el grupo
- Lista de instancias del grupo con su estado actual
- Haz click en cualquier instancia para ver su detalle

---

## 5. Pantalla de Detalle

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
- Puedes refrescar manualmente con el boton de recarga

---

## 6. Programacion (Scheduler)

Si tu admin te dio permiso de ver el scheduler, desde el panel de configuracion (⚙️)
podras ver los horarios programados de encendido y apagado.

- Cada regla muestra: descripcion, hora de encendido, hora de apagado, dias activos e instancias afectadas
- Las reglas pueden estar activas o inactivas
- Si tienes permiso de edicion podras crear, modificar y eliminar reglas

---

## 7. Estados de instancias

| Indicador | Estado | Significado |
|-----------|--------|-------------|
| Verde | running | La instancia esta encendida y funcionando |
| Rojo | stopped | La instancia esta apagada |
| Amarillo | pending | La instancia se esta encendiendo |
| Amarillo | stopping | La instancia se esta apagando |

---

## 8. Preguntas Frecuentes

**P: La instancia dice "running" pero no puedo acceder al dashboard**
R: Puede tardar 1-2 minutos despues de encender para que los servicios esten listos.

**P: Encendi la instancia pero sigue en "pending"**
R: Es normal, el encendido tarda 20-60 segundos. Se actualizara automaticamente.

**P: No veo una cuenta que deberia ver**
R: Tu API Key puede no tener permisos para esa cuenta. Contacta a tu admin.

**P: No veo el boton de configuracion (⚙️)**
R: Solo aparece si tienes acceso a scheduler, notificaciones o costos.

**P: No puedo editar el scheduler**
R: Tu key puede tener permiso de solo lectura. Contacta a tu admin.

**P: El boton "Dashboard" esta deshabilitado**
R: Solo funciona cuando la instancia esta "running" y tiene dashboard configurado.

**P: Como cierro sesion?**
R: Click en el icono de salida en la esquina superior derecha.
