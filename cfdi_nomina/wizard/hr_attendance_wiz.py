import datetime
import math
import time
import logging
from dateutil import relativedelta
from ast import literal_eval
from odoo import api, models, fields

_logger = logging.getLogger(__name__)


def float_to_time(float_hour):
    return datetime.time(int(math.modf(float_hour)[1]), int(60 * math.modf(float_hour)[0]), 0)


class HrMovNomina(models.TransientModel):
    _name = 'hr.attendance.gen.wiz'
    _description = 'Wizard para Buscar Inasistencias'

    date_from = fields.Date('Fecha Inicial', required=True,
                            default=(datetime.datetime.now() + relativedelta.relativedelta(days=-15)))
    date_to = fields.Date('Fecha Final', required=True,
                          default=datetime.datetime.now())
    resultado_txt = fields.Text('Resultado', readonly=True)
   

    def get_timedelta_tz(self, day=None, user=None):
        if not user:
            user = self.env.user
        if not day:
            day = datetime.datetime.now()
        tz = self._context.get(
            'tz', user.partner_id.tz) or 'America/Mexico_City'
        ahora_tz = fields.Datetime.context_timestamp(
            self.with_context(tz=tz), day)
        tz_horas_diff = ahora_tz.tzinfo._utcoffset  # timedelta
        return tz_horas_diff

    @api.model
    def buscar_faltas_cron(self):
        # Usado por el cron, busca la faltas del día en curso, necesario usar
        # la zona horaria

        tz = self._context.get('tz', 'America/Mexico_City')
        ahora_tz = fields.Datetime.context_timestamp(
            self.with_context(tz=tz), datetime.datetime.now())
        wizard = self.create({'date_from': ahora_tz, 'date_to': ahora_tz})
        wizard.with_context(tz=tz).buscar_faltas()

    @api.model
    def es_descanso(self, employee, weekday):
        return weekday in [emp.weekday for emp in employee.dias_descanso_ids]

    def buscar_faltas(self):

        inicio_time = datetime.datetime.now()
        _logger.info(
            '*********** INICIO Selecc horarios {}'.format(inicio_time))

        self.resultado_txt = 'Resultado:\n'

        # Empleados activos
        contratos_vigentes = self.env['hr.contract'].search(
            [('state', '=', 'open'), ('employee_id', '!=', None)])
        # contratos_vigentes = self.env['hr.contract'].search([('state', '=', 'open'), ('employee_id', '!=', None)], limit=200)
        # contratos_vigentes = self.env['hr.contract'].search([('state', '=', 'open'), ('employee_id', '=', 4828)])

        empleados_dict = {}
        for contrato in contratos_vigentes:
            if not contrato.employee_id.resource_calendar_id or contrato.employee_id.resource_calendar_id.omit_attendance:
                continue
            if contrato.employee_id.id not in empleados_dict:
                empleados_dict[contrato.employee_id.id] = {
                    'employee': contrato.employee_id,
                    'contract': contrato,
                }

        empleados_ids = [i for i, data in empleados_dict.items()]

        start_date = fields.Datetime.from_string(self.date_from)
        tz_horas_diff_start = self.get_timedelta_tz(day=start_date)
        end_date = fields.Datetime.from_string(self.date_to)
        tz_horas_diff_end = self.get_timedelta_tz(day=end_date)

        date_from = start_date - tz_horas_diff_start
        date_to = datetime.datetime.combine(
            end_date, datetime.time.max) - tz_horas_diff_end

        asistencia_ids = self.env['hr.attendance'].search([
            ('check_in', '>=', str(date_from)),
            ('check_in', '<=', str(date_to)),
            ('employee_id', 'in', empleados_ids),
        ], order='check_in ASC')

        asisdic = {}
        for check in asistencia_ids:

            check_datetime = fields.Datetime.context_timestamp(
                check, fields.Datetime.from_string(check.check_in))
            weekday = check_datetime.weekday()
            day = check_datetime.date()

            key = (day, check.employee_id.id)
            if key not in asisdic:
                # valor inicial del diccionario
                contrato = empleados_dict[check.employee_id.id].get('contract')
                asisdic[key] = {
                    'day': day,
                    'employee': check.employee_id,
                    'nombre': check.employee_id.nombre_completo,
                    'check_list': [check_datetime],
                    'horario_rst': self.env['resource.calendar.attendance'].search([
                        ('dayofweek', '=', weekday),
                        ('calendar_id', '=', contrato.resource_calendar_id.id)],
                        order='hour_from ASC'
                    ),
                    'weekday': weekday,
                    'falta': False,
                }
            else:
                # agrega hora de checada
                asisdic[key]['check_list'] += [check_datetime]

        #  Busca dias dentro del rango que no tengan registrada alguna asistencia.
        #  faltas dias completos si no son de descanso
        day_count = (end_date - start_date).days + 1

        for single_date in (start_date + datetime.timedelta(n) for n in range(day_count)):
            weekday = single_date.weekday()
            day = single_date.date()  # "%Y-%m-%d"
            for emp_id, empdata in empleados_dict.items():
                contrato = empdata.get('contract')
                emp = empdata.get('employee')
                key = (day, emp_id)
                if key not in asisdic:
                    horario_ids = self.env['resource.calendar.attendance'].search([
                        ('dayofweek', '=', weekday),
                        ('calendar_id', '=', contrato.resource_calendar_id.id)
                    ], order='hour_from ASC'
                    )
                    if horario_ids:
                        # Tiene horario ese dia, de no ser dia de descanso,
                        # sera falta
                        asisdic[key] = {
                            'day': day,
                            'employee': emp,
                            'nombre': emp.nombre_completo,
                            'check_list': [],
                            'horario_rst': horario_ids,
                            'weekday': weekday,
                            'falta': True,
                        }

        d = datetime.datetime.now() - inicio_time
        _logger.info(
            '******** Buscando faltas Tiempo {}'.format(d.seconds + d.microseconds / 1000000.0))

        # Busca faltas del dia en base a horario y asistencias
        for k, v in asisdic.items():
            horario_rst = v.get('horario_rst')

            if len(horario_rst) and not self.es_descanso(v.get('employee'), v.get('weekday')):
                ausencias = []
                if v.get('falta'):
                    # faltó el día completo
                    ausencias.append({
                        'tipo': 'falta',
                        'motivo': 'No se presentó',
                    })

                elif len(v.get('check_list')) < len(horario_rst) * 2:
                    # menos de las checadas del horario = falta
                    ausencias.append({
                        'tipo': 'falta',
                        'motivo': 'Checar en {} ocasion(es), debe checar {} veces ese día'.format(
                            len(v.get('check_list')), len(horario_rst) * 2),
                    })

                else:
                    attendances_list, ausencias = self.get_checadas_validas_dia(
                        v.get('check_list'), v.get('day'), v.get('employee'), horario_rst)

                for aus in ausencias:
                    self.crear_ausencia_retardo(v.get('employee'), v.get('nombre'), v.get('day'),
                                                aus.get('motivo'), aus.get('tipo'))

        if self.resultado_txt == 'Resultado:\n':
            self.resultado_txt += 'No se encontraron motivos para faltas con los datos dados.'

        fin = datetime.datetime.now()
        _logger.info('********************* FIN {}'.format(fin))
        _logger.info(
            '********************* Tiempo {}'.format((fin - inicio_time).seconds))
        # raise UserError('Fin Tiempo {}'.format((fin - inicio).seconds))
        self.resultado_txt += 'Tiempo invertido {}'.format(
            (fin - inicio_time).seconds)
        return self._return_action

    def get_checadas_validas_dia(self, attendances_list, day, employee, horario_rst):
        # Version Ofix

        # Para filtrar rango de minutos despues de la entrada
        rango = literal_eval(self.env['ir.config_parameter'].sudo(
        ).get_param('cfdi_nomina.AttendanceRange') or '30')
        falta = retardo1 = retardo2 = False
        motivo = motivoretardo1 = motivoretardo2 = None
        entrada_ok = False
        checadas_validas = []

        if not len(horario_rst):
            return attendances_list, []
        if not len(attendances_list):
            return attendances_list, [{'tipo': 'falta', 'motivo': 'No presenta asistencia'}]

        # convierte todas las entradas a hora
        checadas_list = [chk.time() for chk in attendances_list]

        # Toma entrada del horario (con tolerancia)
        hora_in = float_to_time(horario_rst[0].hour_from)
        hora_from = (datetime.datetime.combine(datetime.datetime.today(), hora_in) +
                     datetime.timedelta(minutes=horario_rst[0].calendar_id.tolerance)).time()
        hora_after = (datetime.datetime.combine(datetime.datetime.today(), hora_in) +
                      datetime.timedelta(minutes=rango)).time()

        # Checadas antes de la hora de entrada con tolerancia, se toma la
        # primera
        entradas_list = list(filter(lambda x: x <= hora_from, checadas_list))
        if not entradas_list:
            entrada_mal_list = list(
                filter(lambda x: hora_from < x <= hora_after, checadas_list))
            hora_entrada_registrada = entrada_mal_list[
                0] if entrada_mal_list else False
            if entrada_mal_list:
                retardo1 = True
                motivoretardo1 = 'Entró a las {} después de {}'.format(
                    entrada_mal_list[0], hora_from)
            else:
                falta = True
                motivo = motivo or 'No entró antes de {}'.format(hora_from)
        else:
            entrada_ok = True
            hora_entrada_registrada = entradas_list[0]

        # Hora de entrada
        checadas_validas.append(hora_entrada_registrada)

        # Toma salida horario
        hora_out = float_to_time(horario_rst[0].hour_to)
        hora_before = (datetime.datetime.combine(datetime.datetime.today(), hora_out) -
                       datetime.timedelta(minutes=rango)).time()
        hora_after = datetime.time.max
        if len(horario_rst) > 1:
            # si hay hora a comer, toma la salida a comer con rango
            hora_after = (datetime.datetime.combine(datetime.datetime.today(), hora_out) +
                          datetime.timedelta(minutes=rango)).time()

        # Checadas desde rango a la hora de salida, se toma la ultima
        salidas_mal_list = list(
            filter(lambda x: hora_before < x < hora_out, checadas_list))
        if salidas_mal_list:
            falta = True
            motivo = motivo or 'Salió a las {} antes de {}'.format(
                salidas_mal_list[-1], hora_out)
            hora_salida_comer_registrada = salidas_mal_list[-1]
        else:
            salidas_list = list(
                filter(lambda x: hora_out <= x < hora_after, checadas_list))
            hora_salida_comer_registrada = salidas_list[
                -1] if salidas_list else False
            if not hora_salida_comer_registrada and len(horario_rst) == 1:
                falta = True
                motivo = motivo or 'No checó salida'

        # Hora de salida a comer
        checadas_validas.append(hora_salida_comer_registrada)

        if len(horario_rst) > 1:

            # Toma entrada de comer del horario (con tolerancia)
            hora_in = float_to_time(horario_rst[1].hour_from)
            hora_from = (datetime.datetime.combine(datetime.datetime.today(), hora_in) +
                         datetime.timedelta(minutes=horario_rst[1].calendar_id.tolerance)).time()

            hora_before = (datetime.datetime.combine(datetime.datetime.today(), hora_in) -
                           datetime.timedelta(minutes=rango)).time()
            hora_after = (datetime.datetime.combine(datetime.datetime.today(), hora_in) +
                          datetime.timedelta(minutes=rango)).time()

            # Checadas desde el rango hasta entrar a comer con tolerancia, se
            # toma la primera
            entradas_list = list(
                filter(lambda x: hora_before < x <= hora_from, checadas_list))
            if not entradas_list:
                entrada_mal_list = list(
                    filter(lambda x: hora_from <= x <= hora_after, checadas_list))
                hora_entrada_comer_registrada = entrada_mal_list[
                    0] if entrada_mal_list else False
                if entrada_mal_list:
                    retardo2 = True
                    motivoretardo2 = 'Regresó a las {} después de {}'.format(
                        entrada_mal_list[0], hora_from)
                else:
                    falta = True
                    motivo = motivo or 'No regresó antes de {}'.format(
                        hora_from)

                if entrada_ok and not hora_salida_comer_registrada and not hora_entrada_comer_registrada:
                    # esta persona entró bien, pero no salió a comer. No es
                    # falta
                    falta = False
                    motivo = None

            else:
                hora_entrada_comer_registrada = entradas_list[0]

            # Hora de entrada a comer
            checadas_validas.append(hora_entrada_comer_registrada)

            # Toma salida del horario
            hora_out = float_to_time(horario_rst[1].hour_to)
            hora_before = (datetime.datetime.combine(datetime.datetime.today(), hora_out) -
                           datetime.timedelta(minutes=rango)).time()
            hora_after = datetime.time.max

            # Checadas de salida del día, se toma la ultima
            salidas_mal_list = list(
                filter(lambda x: hora_before < x < hora_out, checadas_list))
            if salidas_mal_list:
                falta = True
                motivo = motivo or 'Salió a las {} antes de {}'.format(
                    salidas_mal_list[-1], hora_out)
                hora_salida_registrada = salidas_mal_list[-1]
            else:
                salidas_list = list(
                    filter(lambda x: hora_out <= x <= hora_after, checadas_list))
                hora_salida_registrada = salidas_list[
                    -1] if salidas_list else False
                if not hora_salida_registrada:
                    falta = True
                    motivo = motivo or 'No checó salida'

            # Hora de salida
            checadas_validas.append(hora_salida_registrada)

        # Invierte horas de comida si hubo traslape por rango,  Ofix usa un
        # rango muy amplio y se traslapan
        if len(checadas_validas) >= 3:
            if checadas_validas[1] and checadas_validas[2]:
                if checadas_validas[1] > checadas_validas[2]:
                    # swap
                    tmp = checadas_validas[2]
                    checadas_validas[2] = checadas_validas[1]
                    checadas_validas[1] = tmp

        # regresa las checadas a fecha datetime
        checadas_validas = [datetime.datetime.combine(
            day, check) if check else check for check in checadas_validas]

        ausencias = []
        if falta:
            ausencias.append({
                'tipo': 'falta',
                'motivo': motivo,
            })
            return checadas_validas, ausencias

        if retardo1:
            ausencias.append({
                'tipo': 'retardo1',
                'motivo': motivoretardo1,
            })
        if retardo2:
            ausencias.append({
                'tipo': 'retardo2',
                'motivo': motivoretardo2,
            })

        return checadas_validas, ausencias

    def crear_ausencia_retardo(self, employee, nombre_empleado, fecha, motivo, tipo_ausencia):
        if not tipo_ausencia:
            return False

        holiday_obj = self.env['hr.leaves']
        # Falta desde los primeros 3 segundos del dia
        date_from = datetime.datetime(
            year=fecha.year, month=fecha.month, day=fecha.day) + datetime.timedelta(seconds=3)
        tz_horas_diff = self.get_timedelta_tz(day=date_from)
        date_to = datetime.datetime.combine(fecha, datetime.time.max)
        if tipo_ausencia == 'retardo1':
            # Retardo 1 desde los 0 segundos del dia
            date_to = date_from = datetime.datetime(
                year=fecha.year, month=fecha.month, day=fecha.day)
        elif tipo_ausencia == 'retardo2':  # Solo un minuto
            # Retardo 2 desde segundo 1 del dia
            date_to = date_from = datetime.datetime(year=fecha.year, month=fecha.month, day=fecha.day) + \
                datetime.timedelta(seconds=1)
        date_from -= tz_horas_diff
        date_to -= tz_horas_diff

        # Verifica que no exista una ausencia previa
        ausencia_ids = self.env['hr.leaves'].search([('employee_id', '=', employee.id),
                                                     ('date_from', '<=',
                                                      str(date_to)),
                                                     ('date_to', '>=',
                                                      str(date_from)),
                                                     ('state', 'not in', [
                                                      'cancel', 'refuse']),
                                                     ])
        if ausencia_ids:
            mensaje = '** No creada, Ya existe una ausencia de {} para el dia {}'.format(
                nombre_empleado, fecha)
            self.resultado_txt += mensaje + '\n'
            _logger.info(mensaje)
            return False

        if tipo_ausencia == 'falta':
            holiday_status_id = self.env.ref(
                'hr_holidays.holiday_status_unpaid').id
            asuencia = 'Falta'
        else:
            holiday_status_id = self.env.ref(
                'cfdi_nomina.holiday_status_retardo').id
            asuencia = 'Retardo'
        mensaje = '{} por checador, Motivo: {}, {}'.format(
            asuencia, motivo, nombre_empleado)

        data_ausencia = {
            'name': mensaje,
            'employee_id': employee.id,
            'holiday_type': 'employee',
            'date_from': date_from,
            'date_to': date_to,
            'number_of_days_temp': 1 if tipo_ausencia == 'falta' else 0,
            'holiday_status_id': holiday_status_id,
        }

        try:
            uno = datetime.datetime.now()
            res = holiday_obj.create(data_ausencia)
            dos = datetime.datetime.now()
            d = dos - uno
            # _logger.info('******** Tiempo creando {}'.format(d.seconds + d.microseconds / 1000000.0))
            res.with_context().action_approve()
            d = datetime.datetime.now() - dos
            # _logger.info('******** Tiempo aprobando {}'.format(d.seconds + d.microseconds / 1000000.0))
            self.resultado_txt += mensaje + '\n'
            _logger.info(mensaje)
        except Exception as e:
            self.resultado_txt += mensaje + ' ** NO creada' + '\n'
            _logger.info('{} ** NO creada, {}'.format(mensaje, str(e)))
            res = False

        if tipo_ausencia != 'falta':
            # Considerar retardos acumuladas en el mes del retardo recien
            # registrado
            date_dia_1_mes = datetime.datetime(
                year=fecha.year, month=fecha.month, day=1)
            date_dia_ultimo_mes = datetime.datetime(year=fecha.year, month=fecha.month, day=1) + \
                relativedelta.relativedelta(months=+1, day=1, seconds=-1)
            tz_horas_diff1 = self.get_timedelta_tz(day=date_dia_1_mes)
            tz_horas_diffultimo = self.get_timedelta_tz(
                day=date_dia_ultimo_mes)
            date_dia_1_mes -= tz_horas_diff
            date_dia_ultimo_mes -= tz_horas_diffultimo

            nretardos = literal_eval(self.env['ir.config_parameter'].sudo(
            ).get_param('cfdi_nomina.AttendanceNDelay') or '3')

            retardos_acum = holiday_obj.search([
                ('date_from', '>=', str(date_dia_1_mes)),
                ('date_to', '<=', str(date_dia_ultimo_mes)),
                ('holiday_status_id', '=', self.env.ref(
                    'cfdi_nomina.holiday_status_retardo').id),
                ('employee_id', '=', employee.id),
                ('holiday_type', '=', 'employee'),
                # Si no ha sido marcado el retardo
                ('payslip_status', '!=', True)
            ], limit=nretardos)
            if len(retardos_acum) >= nretardos:
                # Crea una falta por acumulacion de retardos
                falta_acum = self.crear_ausencia_retardo(employee, nombre_empleado, fecha,
                                                         'Falta por acumulacion de {} retardos'.format(
                                                             len(retardos_acum)), 'falta')
                if falta_acum:
                    retardos_acum_list = [(4, retardo.id, 0)
                                          for retardo in retardos_acum]
                    falta_acum.write(
                        {'retardos_acum_list': retardos_acum_list})
                    retardos_acum.write({'payslip_status': True})

        return res

    @property
    def _return_action(self):

        view_rec = self.env['ir.model.data'].get_object_reference(
            'cfdi_nomina', 'view_hr_attendance_wiz_form')
        view_id = view_rec and view_rec[1] or False
        return {
            'name': 'Resultado Faltas Checador',
            'res_id': self.id,
            'view_type': 'form',
            'view_id': [view_id],
            'view_mode': 'form',
            'res_model': 'hr.attendance.gen.wiz',
            'type': 'ir.actions.act_window',
            'target': 'new',
            'context': self._context
        }


class HRAttendanceByEmployee(models.TransientModel):

    _name = 'hr.attendance.employee'

    date_from = fields.Date(
        'From', required=True, default=lambda *a: time.strftime('%Y-%m-01'))
    date_to = fields.Date(
        'To', required=True, default=lambda *a: time.strftime('%Y-%m-01'))
    emp = fields.Many2many(
        'hr.employee', 'attendance_emp_rel', 'att_id', 'emp_id',
        string='Employee(s)')

    def print_report(self):
        self.ensure_one()
        [data] = self.read()
        data['emp'] = self.env.context.get('active_ids', [])
        employees = self.env['hr.employee'].browse(data['emp'])
        datas = {
            'ids': [],
            'model': 'hr.employee',
            'form': data
        }
        return self.env.ref('cfdi_nomina.print_contract_time_pdf').report_action(employees, data=datas)
