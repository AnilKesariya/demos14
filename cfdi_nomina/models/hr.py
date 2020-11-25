# -*- coding: utf-8 -*-
import datetime
from datetime import timedelta
import pytz
import re
from ast import literal_eval
import logging
_logger = logging.getLogger(__name__)
from odoo import api, models, fields, _
from odoo.tools.safe_eval import safe_eval
from pytz import timezone, utc
from collections import defaultdict
from odoo.exceptions import ValidationError, UserError

GRAVADO_EXENTO_SEL = [
    ('ninguno', 'Ninguno'),
    ('gravado', 'Gravado'),
    ('exento', 'Exento'),
    ('p_gravado', 'Parcialmente Gravado'),
    ('p_exento', 'Parcialmente Exento')]


def datetime_to_string(dt):
    """ Convert the given datetime (converted in UTC) to a string value. """
    return fields.Datetime.to_string(dt.astimezone(utc))

def string_to_datetime(value):
    """ Convert the given string value to a datetime in UTC. """
    return utc.localize(fields.Datetime.from_string(value))

def _boundaries(intervals, opening, closing):
    """ Iterate on the boundaries of intervals. """
    for start, stop, recs in intervals:
        if start < stop:
            yield (start, opening, recs)
            yield (stop, closing, recs)


class Intervals(object):
    """ Collection of ordered disjoint intervals with some associated records.
        Each interval is a triple ``(start, stop, records)``, where ``records``
        is a recordset.
    """
    def __init__(self, intervals=()):
        self._items = []
        if intervals:
            # normalize the representation of intervals
            append = self._items.append
            starts = []
            recses = []
            for value, flag, recs in sorted(_boundaries(intervals, 'start', 'stop')):
                if flag == 'start':
                    starts.append(value)
                    recses.append(recs)
                else:
                    start = starts.pop()
                    if not starts:
                        append((start, value, recses[0].union(*recses)))
                        recses.clear()

    def __bool__(self):
        return bool(self._items)

    def __len__(self):
        return len(self._items)

    def __iter__(self):
        return iter(self._items)

    def __reversed__(self):
        return reversed(self._items)

    def __or__(self, other):
        """ Return the union of two sets of intervals. """
        return Intervals(chain(self._items, other._items))

    def __and__(self, other):
        """ Return the intersection of two sets of intervals. """
        return self._merge(other, False)

    def __sub__(self, other):
        """ Return the difference of two sets of intervals. """
        return self._merge(other, True)

    def _merge(self, other, difference):
        """ Return the difference or intersection of two sets of intervals. """
        result = Intervals()
        append = result._items.append

        # using 'self' and 'other' below forces normalization
        bounds1 = _boundaries(self, 'start', 'stop')
        bounds2 = _boundaries(other, 'switch', 'switch')

        start = None                    # set by start/stop
        recs1 = None                    # set by start
        enabled = difference            # changed by switch
        for value, flag, recs in sorted(chain(bounds1, bounds2)):
            if flag == 'start':
                start = value
                recs1 = recs
            elif flag == 'stop':
                if enabled and start < value:
                    append((start, value, recs1))
                start = None
            else:
                if not enabled and start is not None:
                    start = value
                if enabled and start is not None and start < value:
                    append((start, value, recs1))
                enabled = not enabled

        return result



class HrSalaryRuleGroup(models.Model):
    _name = "hr.salary.rule.group"

    name = fields.Char(required=True)


class HRSalaryRule(models.Model):
    _inherit = "hr.salary.rule"

    tipo_id = fields.Many2one("cfdi_nomina.tipo")
    tipo_de_percepcion = fields.Selection([
        ('fijo', 'Fijo'),
        ('variable', 'Variable')])

    tipo_horas = fields.Many2one(
        "cfdi_nomina.tipo_horas", string="Tipo horas extras")
    codigo_agrupador = fields.Many2one(
        "cfdi_nomina.codigo.agrupador", string=u"Código SAT")
    agrupacion = fields.Many2one("hr.salary.rule.group")
    gravado_o_exento = fields.Selection(GRAVADO_EXENTO_SEL, string="Gravado o Exento", required=True, default='gravado',
                                        help='Gravado para ISR. Genera variables  <code>_GRV_ISR y TOTAL_GRV_ISR')
    amount_python_compute2 = fields.Text(string='Python Code Parcial',
                                         help="Codigo de calculo previo, para del monto gravado o exento.")
    gravado_o_exento_imss = fields.Selection(GRAVADO_EXENTO_SEL, string="Gravado o Exento", required=True,
                                             default='ninguno',
                                             help='Gravado para IMSS Genera variables  <code>_GRV_IMSS y TOTAL_GRV_IMSS')
    amount_python_compute2_imss = fields.Text(string='Python Code Parcial',
                                              help="Codigo de calculo previo, para del monto gravado o exento.")
    gravado_o_exento_infonavit = fields.Selection(GRAVADO_EXENTO_SEL, string="Gravado o Exento", required=True,
                                                  default='ninguno',
                                                  help='Gravado para INFONAVIT. '
                                                       'Genera variables  <code>_GRV_INFONAVIT y TOTAL_GRV_INFONAVIT')
    amount_python_compute2_infonavit = fields.Text(string='Python Code Parcial',
                                                   help="Codigo de calculo previo, para del monto gravado o exento.")
    gravado_o_exento_ptu = fields.Selection(GRAVADO_EXENTO_SEL, string="Gravado o Exento", required=True,
                                            default='ninguno',
                                            help='Gravado para PTU. '
                                            'Genera variables  <code>_GRV_LOCAL y TOTAL_GRV_LOCAL')
    amount_python_compute2_ptu = fields.Text(string='Python Code Parcial',
                                             help="Codigo de calculo previo, para del monto gravado o exento.")
    gravado_o_exento_local = fields.Selection(GRAVADO_EXENTO_SEL, string="Gravado o Exento", required=True,
                                              default='ninguno',
                                              help='Gravado para Local. '
                                              'Genera variables  <code>_GRV_LOCAL y TOTAL_GRV_LOCAL')
    amount_python_compute2_local = fields.Text(string='Python Code Parcial',
                                               help="Codigo de calculo previo, para del monto gravado o exento.")

    destajo = fields.Boolean('A Destajo', default=False)
    en_especie = fields.Boolean('Pago en Especie', default=False)
    acum_calendar_id = fields.Many2one('hr.calendar.acum', string='Calendario', required=False,
                                       help='Calendario para acumulados en nomina')
    input_ids = fields.One2many(
        'hr.rule.input', 'input_id', string='Inputs', copy=True)

    @api.model
    def _set_global_values(self, localdict):

        ICPSudo = self.env['ir.config_parameter'].sudo()

        dp = 1
        fa = fi = 0
        tipo_calculo = 'mensual'
        if localdict.get('payslip'):
            slip = localdict.get('payslip')
            day1 = fields.Datetime.from_string(slip.date_from)
            day2 = fields.Datetime.from_string(slip.date_to)
            dp = abs((day2 - day1).days) + 1

            day_leave_from = slip.day_leave_from or slip.date_from
            day_leave_to = slip.day_leave_to or slip.date_to
            ausencia_ids = self.env['hr.leave'].search([
                ('employee_id', '=', slip.employee_id),
                ('holiday_type', '=', 'employee'),
                ('holiday_status_id.afecta_imss',
                 'in', ['ausentismo', 'incapacidad']),
                ('date_from', '>=', day_leave_from),
                ('date_from', '<=', day_leave_to),
            ])
            for ausencia in ausencia_ids:
                if ausencia.holiday_status_id.afecta_imss == 'ausentismo':
                    fa += 1
                elif ausencia.holiday_status_id.afecta_imss == 'incapacidad':
                    fi += 1

            tipo_calculo = slip.tipo_calculo

        # Tipo de calculo
        localdict['TIPOCALCULO'] = tipo_calculo

        # Finiquito
        localdict['FINIQUITO'] = slip.finiquito

        # Dia del mes en curso
        tz = self.env.user.tz or 'America/Mexico_City'
        ahora = fields.Datetime.context_timestamp(
            self.with_context(tz=tz), datetime.datetime.now())
        localdict['DIA_DEL_MES'] = ahora.day

        # Dias del Periodo
        localdict['DP'] = dp
        # Faltas por ausentismo
        localdict['FA'] = fa
        # Faltas por incapacidad
        localdict['FI'] = fi

        dag = dpv = sm = dv = antiguedad = 0
        if localdict.get('employee'):
            employee = localdict.get('employee')
            dag = employee.tabla_sdi_id and employee.tabla_sdi_id.get_aguinaldo_days(
                employee.anos_servicio) or 0
            dpv = employee.tabla_vacaciones_id and employee.tabla_vacaciones_id.get_prima_vacation_days(
                employee.anos_servicio) or 0
            dv = employee.tabla_vacaciones_id and employee.tabla_vacaciones_id.get_vacation_days(
                employee.anos_servicio) or 0
            sm = employee.zona_salario and employee.zona_salario.sm or 0
            antiguedad = employee.anos_servicio

        # Dias Aguinaldo
        localdict['DAG'] = dag
        # Dias Prima Vacacional
        localdict['DPV'] = dpv
        # Dias de Vacaciones
        localdict['DV'] = dv
        # Salario Minimo de Zona
        localdict['SM'] = sm
        # Antigüedad del empleado
        localdict['ANTIGUEDAD'] = antiguedad
        # Días por Año
        localdict['DA'] = literal_eval(
            ICPSudo.get_param('cfdi_nomina.DA') or '0')
        # Factor Periodo
        localdict['FPER'] = self.env['hr.payslip'].get_fper()
        # Salario mínimo DF
        localdict['SF'] = literal_eval(
            ICPSudo.get_param('cfdi_nomina.SF') or '0')
        # UMA
        localdict['UMA'] = literal_eval(
            ICPSudo.get_param('cfdi_nomina.UMA') or '0')

        # Acumulados
        dta = total_grv_isr_ac = total_grv_isr_nc = total_grv_isr_an = 0
        if localdict.get('payslip'):
            slip = localdict.get('payslip').dict
            # Base gravable ISR
            tabla_gravable_isr_id = self.env.ref(
                'cfdi_nomina.tabla_basegravable_isr').id
            anual_lines = slip.get_anual_lines()
            data_grv = slip.get_acumulado_tabla(
                anual_lines, tabla_gravable_isr_id)
            total_grv_isr_ac = data_grv.get('actual_ac', 0)
            total_grv_isr_nc = data_grv.get('actual_nc', 0)
            total_grv_isr_an = data_grv.get('anual', 0)
            # Dias trabajados del mes ( usa el calendario de la tabla ISR )
            data_dias_grv = slip.get_acumulado_dias(tabla_gravable_isr_id)
            dta = data_dias_grv.get('anual', 0)

        # Acumulado Actual, No incluye nomina actual
        localdict['TOTAL_GRV_ISR_AC'] = total_grv_isr_ac
        # Acumulado Actual, Incluye nomina actual
        localdict['TOTAL_GRV_ISR_NC'] = total_grv_isr_nc
        # Acumulado Anual, NO Incluye nomina actual ( todavía no la incluye, se
        # sumará durante el calculo )
        localdict['TOTAL_GRV_ISR_AN'] = total_grv_isr_an
        # valor inicial a 0
        localdict['TOTAL_GRV_ISR_MENSUAL'] = 0
        # SDI valor inicial a 0
        localdict['SDI'] = 0
        # DTA dias trabajados del mes
        localdict['DTA'] = dta

        # Gravado Fijo
        localdict['TOTAL_GRV_FIJO_IMSS'] = 0
        # Listar los conceptos de gravado fijo
        localdict['gravado_fijo_list'] = []
        # Listar los conceptos de gravado variable
        localdict['gravado_variable_list'] = []
        # Subsidio para el empleo
        localdict['SUBE'] = 0
        # ISPT
        localdict['ISPT'] = 0
        # ISPT_ANUAL
        localdict['ISPT_ANUAL'] = 0

    def _compute_last_income_rule(self, localdict, payslip):
        # /////////////////////////////////////////////
        # A la primera deducción se calcula el SDI, SUBE en base al total
        # gravado IMSS al momento
        if not localdict.get('SDI') and self.tipo_id.id == self.env.ref('cfdi_nomina.catalogo_tipo_deduccion').id:

            ICPSudo = self.env['ir.config_parameter'].sudo()

            localdict['SDI'] = payslip.calculate_sdi(localdict)

            # Calculo para la pestaña del bimestre actual
            payslip.calculate_sdi_last_rules(localdict)

            # se le suma el Gravado ISR de la nomina en curso
            localdict[
                'TOTAL_GRV_ISR_NC'] += localdict.get('TOTAL_GRV_ISR', 0.0)

            if payslip.tipo_calculo in ['mensual']:
                localdict['TOTAL_GRV_ISR_MENSUAL'] = localdict.get(
                    'TOTAL_GRV_ISR', 0) * localdict.get('FPER', 0)

            elif payslip.tipo_calculo in ['ajustado', 'anual']:
                localdict['TOTAL_GRV_ISR_MENSUAL'] = localdict.get(
                    'TOTAL_GRV_ISR_NC', 0)

            if payslip.tipo_calculo in ['ajustado',  'anual']:
                localdict['FPER'] = 0

            tabla_sube_id = literal_eval(ICPSudo.get_param(
                'cfdi_nomina.NominaSUBEID') or 'None')
            tabla_isr_id = literal_eval(ICPSudo.get_param(
                'cfdi_nomina.NominaIPSTMensualID') or 'None')

            if payslip.tipo_calculo == 'anual':
                localdict['ISPT'] = self.env['hr.ispt'].get_valor(localdict['TOTAL_GRV_ISR_MENSUAL'],
                                                                        tabla_isr_id)
                localdict['SUBE'] = self.env['hr.employment.sube'].get_valor(localdict['TOTAL_GRV_ISR_MENSUAL'],
                                                                        tabla_sube_id)
                # Registrar valores del Subsidio y Subsidio acumulado
                payslip.save_subsidio(localdict)
                payslip.save_ispt(localdict)

                self.calculo_anual(localdict, payslip)

            else:
                localdict['ISPT'] = self.env['hr.ispt'].get_valor(localdict['TOTAL_GRV_ISR_MENSUAL'],
                                                                        tabla_isr_id)
                localdict['SUBE'] = self.env['hr.employment.sube'].get_valor(localdict['TOTAL_GRV_ISR_MENSUAL'],
                                                                        tabla_sube_id)

                # Registrar valores del Subsidio y Subsidio acumulado
                payslip.save_subsidio(localdict)
                payslip.save_ispt(localdict)
                payslip.calculo_anual = None

    def calculo_anual(self, localdict, payslip):

        ICPSudo = self.env['ir.config_parameter'].sudo()
        tabla_isr_id = literal_eval(ICPSudo.get_param(
            'cfdi_nomina.NominaIPSTAnualID') or 'None')
        tabla_sube_id = literal_eval(ICPSudo.get_param(
            'cfdi_nomina.NominaSUBEID') or 'None')

        fecha_pago = payslip.date_to
        day2 = fields.Datetime.from_string(fecha_pago)
        day1 = datetime.datetime(year=day2.year, month=1, day=1)
        dias_transcurridos = abs((day2 - day1).days) + 1

        factor_anual = localdict.get('DA') / dias_transcurridos

        total_gravado_anual = localdict['TOTAL_GRV_ISR_AN'] + \
            localdict['TOTAL_GRV_ISR_NC'] - \
            localdict['TOTAL_GRV_ISR_AC']

        gravable_anual = factor_anual * total_gravado_anual

        ispt_tabla = self.env['hr.ispt'].get_valor(
            gravable_anual, tabla_isr_id)

        impuesto_del_gravable_acumulado = factor_anual and ispt_tabla / factor_anual or 0.0

        sube_acumulado = self.sube_acumulado_anual(payslip)

        impuesto_corresp_anual = impuesto_del_gravable_acumulado - sube_acumulado
        isr_acumulado = localdict.get('D001_AN', 0)
        ispt = impuesto_corresp_anual - isr_acumulado

        localdict['ISPT_ANUAL'] = ispt
        # localdict['SUBE'] = self.env['hr.employment.sube'].get_valor(total_gravado_anual, tabla_sube_id)

        # _logger.info("SUBE: {}, ISPT: {},  ISPT_ANUAL: {}, D100_AC: {}, FPER: {}".format(
        #     localdict['SUBE'],
        #     localdict['ISPT'],
        #     localdict['ISPT_ANUAL'],
        #     localdict['D100_AC'],
        #     localdict['FPER'],
        # ))

        calculo_anual = """
        <table>
        <tr><td style="padding: 15px;">
        
        <table>
        <tr><th colspan='2'>Factor de anualizacion</th></tr>
        <tr><td>Dias del año</td><td style="text-align: right;">&nbsp;{da:,.4f}</td></tr>
        <tr><td>/Dias transcurridos</td><td style="text-align: right;">&nbsp;{dt:,.4f}</td></tr>
        <tr><td>=Factor anual</td><td style="text-align: right;">&nbsp;{fa:,.4f}</td></tr>
        
        <tr><th colspan='2'>Base gravable anual</th></tr>
        <tr><td>Gravable acumulado</td><td style="text-align: right;">&nbsp;{gravacum:,.4f}</td></tr>
        <tr><td>*Factor anual</td><td style="text-align: right;">&nbsp;{fa:,.4f}</td></tr>
        <tr><td>=Gravable anual</td><td style="text-align: right;">&nbsp;{gravanual:,.4f}</td></tr>
        
        <tr><th colspan='2'>Impuesto determinado (art 177)</th></tr>
        <tr><td>Impuesto determinado (art 177)</td><td style="text-align: right;">&nbsp;{ispt_tabla:,.4f}</td></tr>
        <tr><td>/Factor anual</td><td style="text-align: right;">&nbsp;{fa:,.4f}</td></tr>
        <tr><td>=Imp. del Gravable acumulado</td><td style="text-align: right;">&nbsp;{impuesto_del_gravable_acumulado:,.4f}</td></tr>
        
        <tr><th colspan='2'>I.S.R. de la nomina</th></tr>
        <tr><td>Imp. del Gravable acumulado</td><td style="text-align: right;">&nbsp;{impuesto_del_gravable_acumulado:,.4f}</td></tr>
        <tr><td>-Subs. Empleo acumulado</td><td style="text-align: right;">&nbsp;{sube_acumulado:,.4f}</td></tr>
        <tr><td>=ISR correspondiente anual</td><td style="text-align: right;">&nbsp;{impuesto_corresp_anual:,.4f}</td></tr>
        <tr><td>-ISR acumualdo</td><td style="text-align: right;">&nbsp;{isr_acumulado:,.4f}</td></tr>
        <tr><td>=ISR de la nomina</td><td style="text-align: right;">&nbsp;{ispt:,.4f}</td></tr>
        </table>
        
        </td><td style="padding: 15px;">
        
        <table>
        <tr><th colspan='2'>Subsidio para el empleo acumulado</th></tr>
        <tr><td>Subsidio para el empleo acumulado</td><td style="text-align: right;">&nbsp;{sube_acumulado:,.4f}</td></tr>
        </table>
        
        </td></tr>
        </table>
        """.format(
            da=localdict.get('DA'),
            dt=dias_transcurridos,
            fa=factor_anual,
            gravacum=total_gravado_anual,
            gravanual=gravable_anual,
            ispt_tabla=ispt_tabla,
            impuesto_del_gravable_acumulado=impuesto_del_gravable_acumulado,
            sube_acumulado=sube_acumulado,
            impuesto_corresp_anual=impuesto_corresp_anual,
            isr_acumulado=isr_acumulado,
            ispt=ispt,
        )

        payslip.write({
            'calculo_anual': calculo_anual,
        })

        return calculo_anual

    def sube_acumulado_anual(self, payslip):

        day2 = fields.Datetime.from_string(payslip.date_to)
        day1 = datetime.datetime(year=day2.year, month=1, day=1)
        periodo_payslips = self.env['hr.payslip'].search([
            ('date_from', '>=', day1),
            ('date_to', '<=', day2),
            ('employee_id', '=', payslip.employee_id.id),
            ('state', '=', 'done'),
            # No incluir nomina actual si esta confirmada
            ('id', '!=', payslip.id),
            # ('tipo_calculo', 'in', ['mensual', 'ajustado']),
        ], order='date_from ASC')

        periodo_payslips += payslip   # Incluir nomina actual que aún no esta confirmada

        sube_acumulado = sum(periodo_payslips.mapped('subsidio_causado'))

        return sube_acumulado

    def _compute_rule(self, localdict):
        """
        :param localdict: dictionary containing the environement in which to compute the rule
        :return: returns a tuple build as the base/amount computed, the quantity and the rate
        :rtype: (float, float, float)
        """
        self.ensure_one()

        # Pre-calcula si hay codigo python en Otras Entradas
        self._compute_input_code(self.amount_python_compute, localdict)

        # Llama a rutina super
        # amount, qty, rate = super()._compute_rule(localdict),  # Mejor hago
        # un override...|
        if self.amount_select == 'fix':
            try:
                amount, qty, rate = self.amount_fix, float(
                    safe_eval(self.quantity, localdict)), 100.0
            except:
                raise UserError(
                    _('Wrong quantity defined for salary rule %s (%s).') % (self.name, self.code))
        elif self.amount_select == 'percentage':
            try:
                amount, qty, rate = (float(safe_eval(self.amount_percentage_base, localdict)),
                                     float(safe_eval(self.quantity, localdict)), self.amount_percentage)
            except:
                raise UserError(
                    _('Wrong percentage base or quantity defined for salary rule %s (%s).') % (self.name, self.code))
        else:
            try:
                safe_eval(self.amount_python_compute,
                          localdict, mode='exec', nocopy=True)
                amount, qty, rate = float(localdict['result']), 'result_qty' in localdict and localdict[
                    'result_qty'] or 1.0, 'result_rate' in localdict and localdict['result_rate'] or 100.0
            except Exception as e:  # JGO
                raise UserError(_('Codigo python incorrecto en Regla salarial:%s (%s).,\n%s\n%s.') % (
                    self.name, self.code, self.amount_python_compute, e))
        # --------------------------------------------

        # Gravado ISR
        exento = gravado = 0.0
        if self.gravado_o_exento in ['p_gravado', 'p_exento']:
            # compute the amount of partial the rule
            gravado_o_exento, qty, rate = self._compute_rule_partial(
                self.amount_python_compute2, localdict)
            if not amount >= gravado_o_exento:
                raise ValidationError(_(
                    'Revise las formulas gravado o exento (ISR), de la regla %s, el monto '
                    'total no puede ser menos que el monto de la '
                    'parcialidad') % self.name)
            gravado = gravado_o_exento if self.gravado_o_exento == 'p_gravado' else amount - gravado_o_exento
            exento = gravado_o_exento if self.gravado_o_exento == 'p_exento' else amount - gravado_o_exento

        elif self.gravado_o_exento in ['gravado', 'exento']:
            gravado = amount if self.gravado_o_exento == 'gravado' else 0
            exento = amount if self.gravado_o_exento == 'exento' else 0

        localdict[self.code + '_GRV_ISR'] = gravado
        localdict[self.code + '_EXT_ISR'] = exento
        localdict['TOTAL_GRV_ISR'] = localdict.get(
            'TOTAL_GRV_ISR', 0.0) + gravado
        localdict['TOTAL_EXT_ISR'] = localdict.get(
            'TOTAL_EXT_ISR', 0.0) + exento

        # Gravado IMSS
        exento = gravado = 0.0
        if self.gravado_o_exento_imss in ['p_gravado', 'p_exento']:
            # compute the amount of partial the rule
            gravado_o_exento, qty, rate = self._compute_rule_partial(
                self.amount_python_compute2_imss, localdict)
            if not amount >= gravado_o_exento:
                raise ValidationError(_(
                    'Revise las formulas gravado o exento (IMSS), de la regla %s, el monto '
                    'total no puede ser menos que el monto de la '
                    'parcialidad') % self.name)
            gravado = gravado_o_exento if self.gravado_o_exento_imss == 'p_gravado' else amount - gravado_o_exento
            exento = gravado_o_exento if self.gravado_o_exento_imss == 'p_exento' else amount - gravado_o_exento

        elif self.gravado_o_exento_imss == 'gravado':
            gravado = amount
        elif self.gravado_o_exento_imss == 'exento':
            exento = amount

        localdict[self.code + '_GRV_IMSS'] = gravado
        localdict[self.code + '_EXT_IMSS'] = exento
        localdict['TOTAL_GRV_IMSS'] = localdict.get(
            'TOTAL_GRV_IMSS', 0.0) + gravado
        localdict['TOTAL_EXT_IMSS'] = localdict.get(
            'TOTAL_EXT_IMSS', 0.0) + exento

        if self.tipo_de_percepcion == 'fijo' and gravado:
            localdict['TOTAL_GRV_FIJO_IMSS'] = localdict.get(
                'TOTAL_GRV_FIJO_IMSS', 0.0) + gravado
            localdict[
                'gravado_fijo_list'] += [{'name': self.name, 'code': self.code, 'value': gravado}]

        elif self.tipo_de_percepcion == 'variable' and gravado:
            localdict[
                'gravado_variable_list'] += [{'name': self.name, 'code': self.code, 'value': gravado}]

        # Gravado INFONAVIT
        exento = gravado = 0.0
        if self.gravado_o_exento_infonavit in ['p_gravado', 'p_exento']:
            # compute the amount of partial the rule
            gravado_o_exento, qty, rate = self._compute_rule_partial(
                self.amount_python_compute2_infonavit, localdict)
            if not amount >= gravado_o_exento:
                raise ValidationError(_(
                    'Revise las formulas gravado o exento (INFONAVIT), de la regla %s, el monto '
                    'total no puede ser menos que el monto de la '
                    'parcialidad') % self.name)
            gravado = gravado_o_exento if self.gravado_o_exento_infonavit == 'p_gravado' else amount - gravado_o_exento
            exento = gravado_o_exento if self.gravado_o_exento_infonavit == 'p_exento' else amount - gravado_o_exento

        elif self.gravado_o_exento_infonavit == 'gravado':
            gravado = amount
        elif self.gravado_o_exento_infonavit == 'exento':
            exento = amount

        localdict[self.code + '_GRV_INFONAVIT'] = gravado
        localdict[self.code + '_EXT_INFONAVIT'] = exento
        localdict['TOTAL_GRV_INFONAVIT'] = localdict.get(
            'TOTAL_GRV_INFONAVIT', 0.0) + gravado
        localdict['TOTAL_EXT_INFONAVIT'] = localdict.get(
            'TOTAL_EXT_INFONAVIT', 0.0) + exento

        # Gravado PTU
        exento = gravado = 0.0
        if self.gravado_o_exento_ptu in ['p_gravado', 'p_exento']:
            # compute the amount of partial the rule
            gravado_o_exento, qty, rate = self._compute_rule_partial(
                self.amount_python_compute2_infonavit, localdict)
            if not amount >= gravado_o_exento:
                raise ValidationError(_(
                    'Revise las formulas gravado o exento (PTU), de la regla %s, el monto '
                    'total no puede ser menos que el monto de la '
                    'parcialidad') % self.name)
            gravado = gravado_o_exento if self.gravado_o_exento_ptu == 'p_gravado' else amount - gravado_o_exento
            exento = gravado_o_exento if self.gravado_o_exento_ptu == 'p_exento' else amount - gravado_o_exento

        elif self.gravado_o_exento_ptu == 'gravado':
            gravado = amount
        elif self.gravado_o_exento_ptu == 'exento':
            exento = amount

        localdict[self.code + '_GRV_PTU'] = gravado
        localdict[self.code + '_EXT_PTU'] = exento
        localdict['TOTAL_GRV_PTU'] = localdict.get(
            'TOTAL_GRV_PTU', 0.0) + gravado
        localdict['TOTAL_EXT_PTU'] = localdict.get(
            'TOTAL_EXT_PTU', 0.0) + exento

        # Gravado LOCAL
        exento = gravado = 0.0
        if self.gravado_o_exento_ptu in ['p_gravado', 'p_exento']:
            # compute the amount of partial the rule
            gravado_o_exento, qty, rate = self._compute_rule_partial(
                self.amount_python_compute2_infonavit, localdict)
            if not amount >= gravado_o_exento:
                raise ValidationError(_(
                    'Revise las formulas gravado o exento (LOCAL), de la regla %s, el monto '
                    'total no puede ser menos que el monto de la '
                    'parcialidad') % self.name)
            gravado = gravado_o_exento if self.gravado_o_exento_local == 'p_gravado' else amount - gravado_o_exento
            exento = gravado_o_exento if self.gravado_o_exento_local == 'p_exento' else amount - gravado_o_exento

        elif self.gravado_o_exento_local == 'gravado':
            gravado = amount
        elif self.gravado_o_exento_local == 'exento':
            exento = amount

        localdict[self.code + '_GRV_LOCAL'] = gravado
        localdict[self.code + '_EXT_LOCAL'] = exento
        localdict['TOTAL_GRV_LOCAL'] = localdict.get(
            'TOTAL_GRV_LOCAL', 0.0) + gravado
        localdict['TOTAL_EXT_LOCAL'] = localdict.get(
            'TOTAL_EXT_LOCAL', 0.0) + exento

        # Totalizar total de deducciones y percepciones en TOTAL_DEDUCCIONES,
        # TOTAL_PERCEPCIONES
        deduccion = percepcion = otropago = 0.0
        if self.tipo_id and amount:
            tipo_percepcion_id = self.env.ref(
                'cfdi_nomina.catalogo_tipo_percepcion').id
            tipo_deduccion_id = self.env.ref(
                'cfdi_nomina.catalogo_tipo_deduccion').id
            tipo_otropago_id = self.env.ref(
                'cfdi_nomina.catalogo_tipo_otro_pago').id

            if self.tipo_id.id == tipo_percepcion_id:
                percepcion = amount
            elif self.tipo_id.id == tipo_deduccion_id:
                deduccion = amount
            elif self.tipo_id.id == tipo_otropago_id:
                otropago = amount

        localdict['TOTAL_DEDUCCIONES'] = localdict.get(
            'TOTAL_DEDUCCIONES', 0.0) + deduccion
        localdict['TOTAL_PERCEPCIONES'] = localdict.get(
            'TOTAL_PERCEPCIONES', 0.0) + percepcion
        localdict['TOTAL_OTROS_PAGOS'] = localdict.get(
            'TOTAL_OTROS_PAGOS', 0.0) + otropago

        # _logger.info('Nombre {}, Code {}, sequence {}, tipo {}'.format(self.name, self.code, self.sequence, self.tipo_id.name))

        return amount, qty, rate

    def _compute_rule_partial(self, amount_python_compute, localdict):
        """
        :param amount_python_compute: python code to evaluate
        :param localdict: dictionary containing the environement in which to compute the rule
        :return: returns a tuple build as the base/amount computed, the quantity and the rate
        :rtype: (float, float, float)
        """
        self.ensure_one()
        if amount_python_compute:
            # Pre-calcula si hay codigo python en Otras Entradas que se usen en
            # amount_python_code
            self._compute_input_code(amount_python_compute, localdict)

            try:
                safe_eval(amount_python_compute, localdict,
                          mode='exec', nocopy=True)
                if localdict.get('result', None) is None:  # JGO
                    raise UserError(_('No hay variable "result"'))
                return float(localdict['result']), 'result_qty' in localdict and localdict['result_qty'] \
                    or 1.0, 'result_rate' in localdict and localdict['result_rate'] or 100.0
            except Exception as e:  # JGO
                raise UserError(_('Codigo python incorrecto en Regla salarial:%s (%s)[Partial],\n%s\n%s.') % (
                    self.name, self.code, amount_python_compute, e))

    def _compute_input_code(self, amount_python_compute, localdict):
        # Pre-calcula monto de Otras Entradas si hay codigo python definido

        self.ensure_one()
        if amount_python_compute and 'inputs.' in amount_python_compute:
            inputs_used = re.findall(
                "inputs.(\w+).amount", amount_python_compute)
            inputs_dict = localdict.get('inputs', {})
            for input_code in inputs_used:
                input_line = eval('inputs_dict.{}'.format(input_code))
                if input_line and input_line.amount_python_compute:
                    try:
                        safe_eval(input_line.amount_python_compute,
                                  localdict, mode='exec', nocopy=True)
                        if localdict.get('result', None) is None:  # JGO
                            raise UserError(_('No hay variable "result"'))
                        input_amount = float(
                            localdict['result']) * input_line.quantity
                        input_line.write({'amount': input_amount})
                    except Exception as e:  # JGO
                        raise UserError(_('Codigo python incorrecto en Otras Entradas:%s, %s\n%s\n%s.') % (
                            input_line.name, input_line.code, input_line.amount_python_compute, e))

    @api.onchange('codigo_agrupador')
    def onchange_codigo_agrupador(self):
        for record in self:
            record.tipo_id = record.codigo_agrupador.tipo_id.id

    def compute_rule(self, cr, uid, rule_id, localdict, context=None):
        """
        :param rule_id: id of rule to compute
        :param localdict: dictionary containing the environement in which to compute the rule
        :return: returns a tuple build as the base/amount computed, the quantity and the rate
        :rtype: (float, float, float)
        """
        if context is None:
            context = {}
        rule = self.browse(cr, uid, rule_id, context=context)
        if rule.amount_select == 'fix':
            try:
                return rule.amount_fix, safe_eval(rule.quantity, localdict), 100.0
            except:
                raise ValidationError(_(
                    'Wrong quantity defined for salary rule %s (%s).') % (
                        rule.name, rule.code))
        elif rule.amount_select == 'percentage':
            try:
                return safe_eval(rule.amount_percentage_base, localdict), eval(rule.quantity, localdict), rule.amount_percentage
            except:
                raise ValidationError(_(
                    'Wrong percentage base or quantity defined for salary rule %s (%s).') % (
                        rule.name, rule.code))
        try:
            localdict.update({
                'gravado': 0.0,
                'exento': 0.0,
                'datetime': datetime
            })
            safe_eval(rule.amount_python_compute,
                      localdict, mode='exec', nocopy=True)
            cfdi_nomina = {
                'gravado': localdict['gravado'],
                'exento': localdict['exento'],
            }
            context.setdefault('cfdi_nomina', {})[rule_id] = cfdi_nomina
            if localdict.get('result', None) is None:  # JGO
                raise UserError(_('No hay variable "result"'))
            return localdict['result'], 'result_qty' in localdict and localdict['result_qty'] or 1.0, 'result_rate' in localdict and localdict['result_rate'] or 100.0
        except Exception as e:  # JGO
            raise UserError(_('Codigo python incorrecto en Regla salarial:%s, %s,\n%s\n%s.') % (
                rule.name, rule.code, rule.amount_python_compute, e))
        # except Exception:
        #     raise ValidationError(_('Wrong python code defined for salary rule %s (%s).') % (rule.name, rule.code))


class HrContract(models.Model):
    _inherit = "hr.contract"

    regimen_contratacion = fields.Many2one(
        "cfdi_nomina.regimen.contratacion", required=True)
    periodicidad_pago = fields.Many2one("cfdi_nomina.periodicidad_pago")
    monthly_wage = fields.Monetary(
        'Sueldo Mensual', digits=(16, 2), help='Para contrato impreso')
    planned_payment = fields.Selection([
        ('monthly','Mensual'),
        ('quarterly','Trimestral'),
        ('semiannually','Semestralmente'),
        ('annually','Anualmente'),
        ('weekly','Semanalmente'),
        ('biweekly','Bisemanal'),
        ('bimonthly','Bimensual'),
        ],default="monthly",string="Pago planificado")
    salary_journal = fields.Many2one(
        'account.journal', 'Diario de salario', required=True)


class HrJob(models.Model):
    _inherit = 'hr.job'

    template = fields.Integer(help='Total of employees authorized to this job')
    xs_tipo_grupo_poliza = fields.Selection(selection=[
            ('administracion', 'Administracion'),
            ('ventas', 'Ventas'),
        ], string='Tipo de Puesto',store=True ,default="administracion")


def to_tz(datetime, tz_name):
    tz = pytz.timezone(tz_name) if tz_name else pytz.UTC
    return pytz.UTC.localize(datetime.replace(tzinfo=None), is_dst=False).astimezone(tz).replace(tzinfo=None)


class ResourceCalendar(models.Model):
    _inherit = 'resource.calendar'

    omit_attendance = fields.Boolean(
        help='If this is True do not will be created absences to the '
        'employees with this calendar')
    tolerance = fields.Integer(
        help='Indicate the tolerance to check in the  attendance')

    
    def _leave_intervals_batch(self, start_dt, end_dt, resources=None, domain=None, tz=None):
        """ Return the leave intervals in the given datetime range.
            The returned intervals are expressed in specified tz or in the calendar's timezone.
        """
        resources = self.env['resource.resource'] if not resources else resources
        assert start_dt.tzinfo and end_dt.tzinfo
        self.ensure_one()

        # for the computation, express all datetimes in UTC
        resources_list = list(resources) + [self.env['resource.resource']]
        resource_ids = [r.id for r in resources_list]
        if domain is None:
            domain = [('time_type', '=', 'leave')]
        domain = domain + [
            ('calendar_id', '=', self.id),
            ('resource_id', 'in', resource_ids),
            ('date_from', '<=', datetime_to_string(end_dt)),
            ('date_to', '>=', datetime_to_string(start_dt)),
        ]

        # retrieve leave intervals in (start_dt, end_dt)
        result = defaultdict(lambda: [])
        tz_dates = {}
        leaves = self.env['resource.calendar.leaves']
        for leave in self.env['resource.calendar.leaves'].search(domain):
            for resource in resources_list:
                
                if leave.holiday_id and leave.holiday_id.holiday_status_id and\
                        leave.holiday_id.holiday_status_id.afecta_imss in ['ausentismo', 'incapacidad']:
                    leaves += leave

                if leave.resource_id.id not in [False, resource.id]:
                    continue
                tz = tz if tz else timezone((resource or self).tz)
                if (tz, start_dt) in tz_dates:
                    start = tz_dates[(tz, start_dt)]
                else:
                    start = start_dt.astimezone(tz)
                    tz_dates[(tz, start_dt)] = start
                if (tz, end_dt) in tz_dates:
                    end = tz_dates[(tz, end_dt)]
                else:
                    end = end_dt.astimezone(tz)
                    tz_dates[(tz, end_dt)] = end
                dt0 = string_to_datetime(leave.date_from).astimezone(tz)
                dt1 = string_to_datetime(leave.date_to).astimezone(tz)
                result[resource.id].append((max(start, dt0), min(end, dt1), leave))

        return {r.id: Intervals(result[r.id]) for r in resources_list}

    # def _get_leave_intervals(self, resource_id=None, start_datetime=None, end_datetime=None):
    #     # fully Override in order filter only IMSS official leaves  JGO
    #     """Get the leaves of the calendar. Leaves can be filtered on the resource,
    #     and on a start and end datetime.

    #     Leaves are encoded from a given timezone given by their tz field. COnverting
    #     them in naive user timezone require to use the leave timezone, not the current
    #     user timezone. For example people managing leaves could be from different
    #     timezones and the correct one is the one used when encoding them.

    #     :return list leaves: list of time intervals """
    #     self.ensure_one()
    #     if resource_id:
    #         domain = ['|', ('resource_id', '=', resource_id),
    #                   ('resource_id', '=', False)]
    #     else:
    #         domain = [('resource_id', '=', False)]
    #     if start_datetime:
    #         # domain += [('date_to', '>', fields.Datetime.to_string(to_naive_utc(start_datetime, self.env.user)))]
    #         domain += [('date_to', '>',
    #                     fields.Datetime.to_string(start_datetime + timedelta(days=-1)))]
    #     if end_datetime:
    #         # domain += [('date_from', '<', fields.Datetime.to_string(to_naive_utc(end_datetime, self.env.user)))]
    #         domain += [('date_from', '<',
    #                     fields.Datetime.to_string(end_datetime + timedelta(days=1)))]
    #     # Ignorar el horario ( calendar_id )
    #     # leaves_basic = self.env['resource.calendar.leaves'].search(domain + [('calendar_id', '=', self.id)])
    #     leaves_basic = self.env['resource.calendar.leaves'].search(domain)

    #     # Solo las ausencias oficiales IMSS
    #     leaves = self.env['resource.calendar.leaves']
    #     for leave in leaves_basic:
    #         if leave.holiday_id and leave.holiday_id.holiday_status_id and\
    #                 leave.holiday_id.holiday_status_id.afecta_imss in ['ausentismo', 'incapacidad']:
    #             leaves += leave

    #     filtered_leaves = self.env['resource.calendar.leaves']
    #     for leave in leaves:
    #         if start_datetime:
    #             leave_date_to = to_tz(
    #                 fields.Datetime.from_string(leave.date_to), leave.tz)
    #             if not leave_date_to >= start_datetime:
    #                 continue
    #         if end_datetime:
    #             leave_date_from = to_tz(
    #                 fields.Datetime.from_string(leave.date_from), leave.tz)
    #             if not leave_date_from <= end_datetime:
    #                 continue
    #         filtered_leaves += leave

    #     return [self._interval_new(
    #         to_tz(fields.Datetime.from_string(leave.date_from), leave.tz),
    #         to_tz(fields.Datetime.from_string(leave.date_to), leave.tz),
    #         {'leaves': leave}) for leave in filtered_leaves]
