# -*- coding: utf-8 -*-
import json
import logging
import threading
from ast import literal_eval
from datetime import datetime, timedelta
from datetime import time as datetime_time
from odoo.addons.hr_payroll.models.browsable_object import BrowsableObject, InputLine, WorkedDays, Payslips
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Datetime
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT

from odoo import _, api, models, fields, registry

_logger = logging.getLogger(__name__)


class HrPayslipWorkedDays(models.Model):
    _inherit = "hr.payslip.worked_days"
    _description = 'hr payslip worked days'

    holiday_ids = fields.Many2many('hr.leave', string='Absences considered')
    dias_imss_ausencia = fields.Float()
    dias_imss_incapacidad = fields.Float()
    number_of_days = fields.Integer(string='Number of Days')

    def calc_dias_imss(self):

        for wrk in self:
            total_dias = wrk.number_of_days
            if total_dias and not self.dias_imss_ausencia and not self.dias_imss_incapacidad:
                aus = inc = 0
                for falta in wrk.holiday_ids:
                    if falta.holiday_status_id and falta.holiday_status_id.afecta_imss == 'ausentismo':
                        aus += falta.number_of_days_temp
                    elif falta.holiday_status_id.afecta_imss == 'incapacidad':
                        inc += falta.number_of_days_temp

                if aus + inc > total_dias:
                    inc = total_dias - aus
                    if inc < 0:
                        inc = 0

                wrk.dias_imss_ausencia = aus
                wrk.dias_imss_incapacidad = inc

        return


class HrPayslipInput(models.Model):
    _inherit = "hr.payslip.input"
    _description = 'hr payslip input'

    code = fields.Char("Code")
    quantity = fields.Float('Quantity', default=1.0)
    amount_python_compute = fields.Text(string='Python code',
                                        help='If there is code, it is executed and the result '
                                             'is recorded in the (amount)')


class HrPaySlipInfo(models.Model):
    _name = 'hr.payslip.info'
    _description = 'hr payslip info'

    name = fields.Char("Name")
    code = fields.Char("Key")
    value = fields.Float("Value", digits=(16, 5))


class HrPaySlipAcumulado(models.Model):
    _name = 'hr.payslip.acumulado'
    _description = 'hr payslip accumulated'

    slip_id = fields.Many2one('hr.payslip')
    name = fields.Char("Name")
    code = fields.Char("Key")
    base_grv_id = fields.Integer('Taxable Base ID')
    actual_ac = fields.Float(
        "Current AC", help="Current AC, Does not include current payroll", )
    actual_nc = fields.Float(
        "Current NC", help="Current NC, includes current payroll")
    anterior = fields.Float("Previous")
    anual = fields.Float("Annual")


class HrPayslipLine(models.Model):
    _inherit = "hr.payslip.line"
    _description = 'hr payslip line'

    date_from = fields.Date(related="slip_id.date_from", string="From")
    date_to = fields.Date(related="slip_id.date_to", string="Date To")
    codigo_agrupador = fields.Char(
        related="salary_rule_id.codigo_agrupador.name")
    tipo_de_percepcion = fields.Selection(
        [('fijo', 'Fijo'), ('variable', 'Variable')],
        related="salary_rule_id.tipo_de_percepcion")
    gravado = fields.Float("Taxed ISR")
    exento = fields.Float("Exempt ISR")
    gravado_imss = fields.Float()
    exento_imss = fields.Float()
    gravado_infonavit = fields.Float()
    exento_infonavit = fields.Float()
    gravado_ptu = fields.Float()
    exento_ptu = fields.Float()
    gravado_local = fields.Float()
    exento_local = fields.Float()
    code = fields.Char(related="salary_rule_id.code", required=True,
                       help="The code of salary rules can be used as reference in computation of other rules. "
                            "In that case, it is case sensitive.")


class HrPayslip(models.Model):
    _inherit = "hr.payslip"
    _description = 'hr payslip'

    payment_date = fields.Date(string="Payment Date")

    cod_emp = fields.Char(related="employee_id.barcode",
                          string="Code used", store=True)
    day_leave_from = fields.Date(help='Used to get the lack to the employees')
    day_leave_to = fields.Date(help='Used to get the lack to the employees')
    tipo_calculo = fields.Selection([
        ('anual', 'Anual'),
        ('ajustado', 'Ajustado'),
        ('mensual', 'Mensual'),
    ], 'Calculation type', default='mensual', readonly=True, states={'draft': [('readonly', False)]})

    sdo = fields.Float("Daily Salary", copy=False)
    sdi = fields.Float("Integrated daily wage",
                       help="Fixed SDI + variable SDI", readonly=True, copy=False)
    sdi_var = fields.Float(
        "Variable SDI", help="Variable daily wage", readonly=True, copy=False)
    sdi_fijo = fields.Float(
        "Fixed SDI", help="Fixed daily salary", readonly=True, copy=False)
    sdi_info_calc_ids = fields.Many2many('hr.payslip.info', relation="hr_payslip_hr_payslip_info_rel",
                                         string='Detail SDI Fixed', readonly=True, copy=False)
    sdip_info_calc_ids = fields.Many2many('hr.payslip.info', relation="hr_payslip_hr_payslip_infop_rel",
                                          string='Detail SDI Fixed perceptions', readonly=True, copy=False)
    sdiv_info_calc_ids = fields.Many2many('hr.payslip.info', relation="hr_payslip_hr_payslip_infov_rel",
                                          string='Detail SDI Variable', readonly=True, copy=False)

    acumulado_ids = fields.One2many(
        'hr.payslip.acumulado', 'slip_id', string='Accumulated', readonly=True, copy=False)

    # variables de subsidio para calculos prosteriores
    subsidio_causado = fields.Float("Subsidy Due", copy=False)
    sube = fields.Float("GO UP", copy=False)
    sube_calc = fields.Float("RISE calc", copy=False)
    ispt = fields.Float("ISPT", copy=False)
    ispt_calc = fields.Float("ISPT calc", copy=False)

    # Registro de historicos Obrero-Patronal IMSS por nomina
    # No. dias trabajados JRV 20190514
    dtnom = fields.Integer("Days worked", readonly=True)
    # No. dias del periodo nomina JRV 20190514
    dpnom = fields.Integer("Payroll period days", readonly=True)
    pe_patron = fields.Float("Fixed Quota Species",
                             digits=(8, 4), readonly=True)
    ae3_patron = fields.Float("Major species 3 UMA",
                              digits=(8, 4), readonly=True)
    ae3_trab = fields.Float("Major species 3 UMA",
                            digits=(8, 4), readonly=True)
    ed_patron = fields.Float("Cash Benefits",
                             digits=(8, 4), readonly=True)
    ed_trab = fields.Float("Cash Benefits",
                           digits=(8, 4), readonly=True)
    gmp_patron = fields.Float(
        "Pensioners and beneficiaries", digits=(8, 4), readonly=True)
    gmp_trab = fields.Float("Pensioners and beneficiaries",
                            digits=(8, 4), readonly=True)
    iv_patron = fields.Float("Disability and life", digits=(8, 4), readonly=True)
    iv_trab = fields.Float("Disability and life", digits=(8, 4), readonly=True)
    rt_patron = fields.Float("Occupational Risk", digits=(8, 4), readonly=True)
    gua_patron = fields.Float(
        "Nursery Schools and Social Services", digits=(8, 4), readonly=True)
    ret_patron = fields.Float("Retirement Insurance", digits=(8, 4), readonly=True)
    ceav_patron = fields.Float(
        "Cesantia and old age", digits=(8, 4), readonly=True)
    ceav_trab = fields.Float("Cesantia and old age", digits=(8, 4), readonly=True)
    infonavit_patron = fields.Float("Infonavit", digits=(8, 4), readonly=True)

    # Segunda pestaña de datos SDI
    sdi_last = fields.Float("Integrated daily wage",
                            help="Fixed SDI + variable SDI", readonly=True, copy=False)
    sdi_var_last = fields.Float(
        "Variable SDI", help="Variable daily wage", readonly=True, copy=False)
    sdi_fijo_last = fields.Float(
        "Fixed SDI", help="Fixed daily salary", readonly=True, copy=False)
    sdi_info_calc_last_ids = fields.Many2many('hr.payslip.info', relation="hr_payslip_hr_payslip_info_last_rel",
                                              string='Detail SDI Fixed', readonly=True, copy=False)
    sdip_info_calc_last_ids = fields.Many2many('hr.payslip.info', relation="hr_payslip_hr_payslip_infop_last_rel",
                                               string='Detail SDI Fixed Perceptions', readonly=True, copy=False)
    sdiv_info_calc_last_ids = fields.Many2many('hr.payslip.info', relation="hr_payslip_hr_payslip_infov_last_rel",
                                               string='Detail SDI Variable', readonly=True, copy=False)

    calculo_anual = fields.Html(
        "Annual Calculation", readonly=True, help="Annual data")
    # localdict = fields.Text("Variables durante el calculo", readonly=True)
    worked_days_line_ids = fields.One2many('hr.payslip.worked_days', 'payslip_id',
                                           string='Payslip Worked Days', copy=True, readonly=False,
                                           states={'verify': [('readonly', True)]})
    rule_line_ids = fields.One2many('hr.payslip.line',
                                    compute='_compute_details_by_salary_rule_category',
                                    string='Details by Salary Rule Category')

    def _compute_details_by_salary_rule_category(self):
        for payslip in self:
            payslip.rule_line_ids = payslip.mapped('line_ids').filtered(lambda line: line.category_id)

    @api.constrains('date_from', 'date_to', 'state', 'employee_id', 'tipo_nomina')
    def _check_date(self):
        for payslip in self.filtered(lambda p: p.state == 'done' and 'tipo_nomina' == 'O'):
            domain = [
                ('date_from', '<=', payslip.date_to),
                ('date_to', '>=', payslip.date_from),
                ('employee_id', '=', payslip.employee_id.id),
                ('id', '!=', payslip.id),
                ('tipo_nomina', '=', 'O'),  # Solo nominas ordinarias
                ('state', 'in', ['done']),
            ]
            payslips = self.search_count(domain)
            if payslips:
                raise ValidationError(
                    _('No puede haber 2 nominas Ordinarias solapadas en el mismo periodo!'))

    @api.model
    def default_get(self, fields):
        res = super(HrPayslip, self).default_get(fields)

        if 'employee_id' in res:
            employee = self.env['hr.employee'].browse(res.get('employee_id'))
            if 'day_leave_from' in res:
                res['day_leave_from'] = self.check_start_date(
                    employee, res.get('day_leave_from'))
            if 'date_from' in res:
                res['date_from'] = self.check_start_date(
                    employee, res.get('date_from'))

        return res

    @api.model
    def check_start_date(self, employee, start_date):
        if employee and employee.fecha_alta and start_date and employee.fecha_alta > start_date:
            return employee.fecha_alta
        return start_date

    @api.onchange('employee_id', 'struct_id', 'contract_id', 'date_from', 'date_to', 'day_leave_from', 'day_leave_to')
    def _onchange_employee(self):
        self.day_leave_from = self.check_start_date(
            self.employee_id, self.day_leave_from)
        self.date_from = self.check_start_date(
            self.employee_id, self.date_from)
        if self.contract_id:
            self.journal_id = self.contract_id.salary_journal if self.contract_id.salary_journal else False
        if self.struct_id and self.struct_id.rule_ids and self.struct_id.rule_ids.input_ids:
            self.input_line_ids = [(5, 0)]
            payslip_input_type_obj = self.env['hr.payslip.input.type']
            for line in self.struct_id.rule_ids.input_ids:
                type = payslip_input_type_obj.search([('name', '=', line.name), ('code', '=', line.code),
                                                      ('struct_ids', 'in', self.struct_id.id)], limit=1)
                if not type:
                    type = payslip_input_type_obj.create({
                        'name': line.name,
                        'code': line.code,
                        'struct_ids': [(4, self.struct_id.id)]
                    })
                self.input_line_ids = [(0, 0, {
                    'input_type_id': type.id,
                    'code': line.code
                })]
        return super(HrPayslip, self)._onchange_employee()

    def _calculation_confirm_sheet(self, use_new_cursor=False):
        with api.Environment.manage():
            with registry(use_new_cursor or self.env.cr.dbname).cursor() as new_cr:  # noqa
                new_env = api.Environment(
                    new_cr, self.env.uid, self.env.context)
                try:
                    for payslip in self.with_env(new_env):
                        payslip.action_payslip_done()
                        new_cr.commit()
                except Exception as e:
                    _logger.error(
                        'Confirmacion masiva de nomina {}'.format(str(e)))
                    payslip_run = self.env.context.get('payslip_run')
                    if payslip_run:
                        payslip_run.with_env(new_env).message_post(
                            body=_('Confirmacion masiva de nomina {}'.format(str(e))))
                    pass
                finally:
                    pass
        return {}

    def action_payslip_done(self):
        # Marcar las faltas para no repetir en otro calculo de quincenca
        res = super().action_payslip_done()
        for payslip in self:
            total = 0
            for line in payslip.worked_days_line_ids:
                total += line.number_of_days * payslip.contract_id.wage
                for falta in line.holiday_ids:
                    falta.payslip_status = True
            payslip.total = total
        return res

    def compute_sheet(self):
        res = super().compute_sheet()
        self.compute_sheet_total()
        for line in self.line_ids:
            if line.code =='S_TOTAL' and line.category_id.code == 'NET':
                self.total = line.total
        return res

    def compute_sheet_total(self):
        tipo_percepcion_id = self.env.ref(
            'cfdi_nomina.catalogo_tipo_percepcion').id
        tipo_deduccion_id = self.env.ref(
            'cfdi_nomina.catalogo_tipo_deduccion').id
        tipo_otropago_id = self.env.ref(
            'cfdi_nomina.catalogo_tipo_otro_pago').id

        amount_total = 0
        for payslip in self:
            if payslip.state == 'draft':
                line_total = 0.0
                for line in payslip.line_ids.filtered(
                        lambda l: bool(l.total) and l.salary_rule_id.tipo_id and not l.salary_rule_id.en_especie):

                    if line.salary_rule_id.tipo_id.id == tipo_percepcion_id:
                        line_total += line.total
                    elif line.salary_rule_id.tipo_id.id == tipo_otropago_id:
                        line_total += line.total
                    elif line.salary_rule_id.tipo_id.id == tipo_deduccion_id:
                        line_total -= line.total

                _logger.info("Recalculando acumulados")
                payslip.recalc_acumulados()
                payslip.calc_cuotas_obrero_patronal()
                payslip.total = line_total
            else:
                line_total = payslip.total

            amount_total += line_total

        return amount_total

    def calc_cuotas_obrero_patronal(self, uma=False):
        for payslip in self:
            if not payslip.employee_id.company_id.registro_patronal:
                raise UserError('No hay Registro patron en la compañía %s del empleado %s' % (
                    payslip.employee_id.company_id.name, payslip.employee_id.nombre_compelto))

            rp = payslip.employee_id.company_id.registro_patronal
            if not uma:
                uma = rp.UMA
            sbc = payslip.sdi

            # dias del periodo de la nomina 15 o 16 JRV 20190514
            date_from = fields.Date.from_string(payslip.date_from)
            date_to = fields.Date.from_string(payslip.date_to)
            day_from = datetime.combine(date_from, datetime_time.min)
            day_to = datetime.combine(
                date_to, datetime_time.min) + timedelta(days=1)
            dpnom = (day_to - day_from).days
            payslip.dpnom = dpnom

            # suma de faltas en el periodo  JRV 21112019
            data_faltas = payslip.worked_days_line_ids.filtered(
                lambda l: l.code == 'No pagado' or l.code == 'PS' or l.code ==
                          'Incapacidad General' or l.code == 'Incapacidad Permanente Parcial' or l.code == 'Incapacidad Permanente Toatl')
            dias_faltas = sum(data_faltas.mapped('number_of_days'))

            ################
            data_trabajados = payslip.worked_days_line_ids.filtered(
                lambda l: l.code == 'WORK100')
            dias_periodo = sum(data_trabajados.mapped('number_of_days'))
            payslip.ae3_trab = 0
            payslip.ae3_patron = 0
            # Tope 25 uma's JRV 170619
            if sbc > (uma * 25):
                sbc = uma * 25
            # fin JRV
            if sbc > (uma * 3):
                payslip.ae3_trab = (
                                           ((sbc - (uma * 3)) * payslip.dpnom) * rp.AE3_TRAB) / 100
                payslip.ae3_patron = (
                                             ((sbc - (uma * 3)) * payslip.dpnom) * rp.AE3_PATRON) / 100

            payslip.pe_patron = ((uma * dpnom) * rp.PE_PATRON) / 100
            payslip.ed_trab = ((sbc * dpnom) * rp.ED_TRAB) / 100
            payslip.ed_patron = ((sbc * dpnom) * rp.ED_PATRON) / 100
            payslip.gmp_trab = ((sbc * dpnom) * rp.GMP_TRAB) / 100
            payslip.gmp_patron = ((sbc * dpnom) * rp.GMP_PATRON) / 100
            payslip.iv_trab = ((sbc * rp.IV_TRAB) *
                               (dpnom - dias_faltas)) / 100
            payslip.iv_patron = ((sbc * rp.IV_PATRON) *
                                 (dpnom - dias_faltas)) / 100
            payslip.gua_patron = ((sbc * rp.GUA_PATRON)
                                  * (dpnom - dias_faltas)) / 100
            payslip.ret_patron = ((sbc * dpnom) * rp.RET_PATRON) / 100
            payslip.ceav_trab = ((dpnom * sbc) * rp.CEAV_TRAB) / 100
            payslip.ceav_patron = ((dpnom * sbc) * rp.CEAV_PATRON) / 100
            payslip.infonavit_patron = (
                                               (dpnom * sbc) * rp.INFONAVIT_PATRON) / 100
            payslip.rt_patron = ((sbc * rp.PRT) * (dpnom - dias_faltas)) / 100
            # imss = ae3_trab + ed_trab + gmp_trab + iv_patron + ceav_patron
            payslip.dtnom = dias_periodo  # Dias trabajado en el periodo JRV 20190514

    @api.model
    def get_worked_day_lines(self, contracts, date_from, date_to):
        # Override a la rutina original de hr_payroll,   JGO
        #  * tomar periodo de faltas de context
        #  * registrar id de la falta (hr.leave)
        #  * extender date_to a las 0 hrs del dia siguiente
        """
        @param contract: Browse record of contracts
        @return: returns a list of dict containing the input that should be applied for the given contract between date_from and date_to
        """
        res = []
        tz_horas_diff = self.env['hr.attendance.gen.wiz'].get_timedelta_tz()
        date_leave_from = self._context.get('default_day_leave_from', self.day_leave_from) or date_from
        date_leave_to = self._context.get('default_day_leave_to', self.day_leave_to) or date_to

        # fill only if the contract as a working schedule linked
        for contract in contracts.filtered(lambda contract: contract.resource_calendar_id):

            e_date_leave_from = fields.Date.from_string(self.check_start_date(contract.employee_id, date_leave_from))
            e_date_from = fields.Date.from_string(self.check_start_date(contract.employee_id, date_from))
            date_leave_to = fields.Date.from_string(date_leave_to)
            date_to = fields.Date.from_string(date_to)

            day_from = datetime.combine(e_date_from, datetime_time.min)
            day_to = datetime.combine(date_to, datetime_time.min) + timedelta(days=1)

            # Usar periodo para faltas.
            day_leave_from = datetime.combine(e_date_leave_from, datetime_time.min) - tz_horas_diff
            day_leave_to = datetime.combine(date_leave_to, datetime_time.max) - tz_horas_diff

            # compute leave days on day_leave_from and day_leave_to
            leaves = {}
            day_leave_intervals = contract.employee_id.iter_leaves(day_leave_from, day_leave_to,
                                                                   calendar=contract.resource_calendar_id)

            # Ajuste para Ofix.  Solo considerar fechas
            dias_falta = 0
            dias_trabajados = (day_to - day_from).days

            for day_intervals in day_leave_intervals:
                for interval in day_intervals:
                    holiday = interval[2]['leaves'].holiday_id
                    # Falta ya procesada en la generacion de nominas anteriores
                    if not holiday or holiday.payslip_status:
                        continue

                    # Solo faltas oficiales IMSS
                    if not holiday.holiday_status_id or holiday.holiday_status_id and \
                            holiday.holiday_status_id.afecta_imss not in ['ausentismo', 'incapacidad']:
                        continue

                    current_leave_struct = leaves.setdefault(holiday.holiday_status_id, {
                        'name': holiday.holiday_status_id.name,
                        'sequence': 5,
                        'code': holiday.holiday_status_id and holiday.holiday_status_id.name.replace(" ", "_") or "",
                        'number_of_days': 0.0,
                        'number_of_hours': 0.0,
                        'contract_id': contract.id,
                        'dias_imss_ausencia': 0.0,  # JGO
                        'dias_imss_incapacidad': 0.0,  # JGO
                        'holiday_ids': [],  # Tomar nota de las faltas consideradas en el calculo JGO
                    })
                    leave_time = (interval[1] - interval[0]).seconds / 3600
                    current_leave_struct['number_of_hours'] += leave_time

                    work_hours = contract.employee_id.get_day_work_hours_count(interval[0].date(),
                                                                               calendar=contract.resource_calendar_id)

                    # _logger.info("ausencia: {}, {}-{} = leave_time: {}".format(holiday.name, interval[0], interval[1], leave_time))
                    # _logger.info("horas_trabajo: {} dias_falta: {}".format(work_hours, leave_time / work_hours if work_hours else 0))

                    if work_hours:
                        current_leave_struct['number_of_days'] += leave_time / work_hours
                        dias_falta += leave_time / work_hours

                        # _logger.info("dias_falta_acuml : {}".format(dias_falta))

                        if leave_time:
                            if holiday.holiday_status_id.afecta_imss == 'ausentismo':
                                current_leave_struct['dias_imss_ausencia'] += leave_time / work_hours
                            elif holiday.holiday_status_id.afecta_imss == 'incapacidad':
                                current_leave_struct['dias_imss_incapacidad'] += leave_time / work_hours

                    current_leave_struct['holiday_ids'] += [(4, holiday.id, None)]  # Agrega la falta considerada

            # compute worked days
            work_data = contract.employee_id.get_work_days_data(day_from, day_to,
                                                                calendar=contract.resource_calendar_id)

            # Sobreescribir dias trabajados
            work_data['days'] = dias_trabajados - dias_falta

            attendances = {
                'name': _("Normal Working Days paid at 100%"),
                'sequence': 1,
                'code': 'WORK100',
                'number_of_days': work_data['days'],
                'number_of_hours': work_data['hours'],
                'contract_id': contract.id,
            }

            res.append(attendances)
            res.extend(leaves.values())
        return res

    @api.model
    def get_inputs(self, contracts, date_from, date_to):
        if self._context.get('struct_run_id'):
            # Si en el context viene la estructura a usar desde el
            # Procesamiento de Nominas

            res = []
            structure_ids = [self._context.get('struct_run_id')]
            rule_ids = self.env['hr.payroll.structure'].browse(
                structure_ids).get_all_rules()
            sorted_rule_ids = [id for id, sequence in sorted(
                rule_ids, key=lambda x: x[1])]
            inputs = self.env['hr.salary.rule'].browse(
                sorted_rule_ids).mapped('input_ids')

            for contract in contracts:
                for input in inputs:
                    input_data = {
                        'name': input.name,
                        'code': input.code,
                        'contract_id': contract.id,
                    }
                    res += [input_data]
        else:
            res = super().get_inputs(contracts, date_from, date_to)

        employee = self.employee_id or contracts.employee_id

        for i, line in enumerate(res):
            code = line.get('code')
            #  Movimientos de nomina adicionales
            movnom_line = self.env['hr.mov.nomina.line'].search([('mov_nomina_id.rule_code', '=', code),
                                                                 ('mov_nomina_id.state',
                                                                  '=', 'alta'),
                                                                 ('employee_id',
                                                                  '=', employee.id),
                                                                 '|',
                                                                 ('date_deadline',
                                                                  '>=', date_to),
                                                                 ('date_deadline',
                                                                  '=', None),
                                                                 ], limit=1)
            amount_python_compute = ''
            # Si la linea del mov tiene formula, se le da preferencia ante la
            # formula del movimiento de nomina
            if movnom_line:
                if movnom_line.amount_python_compute and movnom_line.amount_python_compute.strip():
                    amount_python_compute = movnom_line.amount_python_compute
                elif movnom_line.mov_nomina_id.amount_python_compute:
                    amount_python_compute = movnom_line.mov_nomina_id.amount_python_compute.strip() or ''

            #  Si la regla salarial tiene destajo
            destajo = self.env['hr.salary.rule'].search(
                [('code', '=', code)]).destajo

            # Si hay entrada y si tiene codigo python
            rule_input = self.env['hr.rule.input'].search(
                [('code', '=', code)])
            if rule_input and rule_input.amount_python_compute:
                amount_python_compute = rule_input.amount_python_compute

            res[i].update({
                'amount_python_compute': amount_python_compute,
                'quantity': 0 if destajo else 1,
            })

        return res

    # def _get_payslip_lines(self):
    #     print ("inside method =-=-=-")
    #     def _sum_salary_rule_category(localdict, category, amount):
    #         if category.parent_id:
    #             localdict = _sum_salary_rule_category(localdict, category.parent_id, amount)
    #         localdict['categories'].dict[category.code] = localdict['categories'].dict.get(category.code, 0) + amount
    #
    #         print ("local dict =-=", localdict)
    #         return localdict
    #
    #     self.ensure_one()
    #     result = {}
    #     rules_dict = {}
    #     worked_days_dict = {line.code: line for line in self.worked_days_line_ids if line.code}
    #     inputs_dict = {line.code: line for line in self.input_line_ids if line.code}
    #
    #     employee = self.employee_id
    #     contract = self.contract_id
    #
    #     localdict = {
    #         **self._get_base_local_dict(),
    #         **{
    #             'categories': BrowsableObject(employee.id, {}, self.env),
    #             'rules': BrowsableObject(employee.id, rules_dict, self.env),
    #             'payslip': Payslips(employee.id, self, self.env),
    #             'worked_days': WorkedDays(employee.id, worked_days_dict, self.env),
    #             'inputs': InputLine(employee.id, inputs_dict, self.env),
    #             'employee': employee,
    #             'contract': contract
    #         }
    #     }
    #
    #     localdict = dict(localdict, employee=employee, contract=contract)
    #     # set global initial variables and values
    #     self.env['hr.salary.rule']._set_global_values(localdict)
    #
    #     # disponibles variables acumuladas  NC (aún no contiene la nomina actual),
    #     # AC (periodo actual sin la nomina actual), ANT (anterior), AN (anual)
    #     sorted_rule_ids = [id for id, sequence in sorted(self.struct_id.rule_ids, key=lambda x: x[1])]
    #     sorted_rules = self.env['hr.salary.rule'].browse(sorted_rule_ids)
    #     self.set_acumulado_variables(localdict, sorted_rules)
    #
    #     for rule in sorted(self.struct_id.rule_ids, key=lambda x: x.sequence):
    #         localdict.update({
    #             'result': None,
    #             'result_qty': 1.0,
    #             'result_rate': 100})
    #         if rule._satisfy_condition(localdict):
    #             rule._compute_last_income_rule(localdict, payslip)
    #             amount, qty, rate = rule._compute_rule(localdict)
    #             # check if there is already a rule computed with that code
    #             previous_amount = rule.code in localdict and localdict[rule.code] or 0.0
    #             # set/overwrite the amount computed for this rule in the localdict
    #             tot_rule = amount * qty * rate / 100.0
    #             localdict[rule.code] = tot_rule
    #             rules_dict[rule.code] = rule
    #             # sum the amount for its salary category
    #             localdict = _sum_salary_rule_category(localdict, rule.category_id, tot_rule - previous_amount)
    #
    #             codigo_nc = "{}_NC".format(rule.code)
    #             localdict[codigo_nc] = localdict.get(codigo_nc, 0) + tot_rule
    #             # create/overwrite the rule in the temporary results
    #             result[rule.code] = {
    #                 'sequence': rule.sequence,
    #                 'code': rule.code,
    #                 'name': rule.name,
    #                 'note': rule.note,
    #                 'salary_rule_id': rule.id,
    #                 'contract_id': contract.id,
    #                 'employee_id': employee.id,
    #                 'amount': amount,
    #                 'quantity': qty,
    #                 'rate': rate,
    #                 'slip_id': self.id,
    #                 'gravado': localdict[rule.code + '_GRV_ISR'],
    #                 'exento': localdict[rule.code + '_EXT_ISR'],
    #                 'gravado_imss': localdict[rule.code + '_GRV_IMSS'],
    #                 'exento_imss': localdict[rule.code + '_EXT_IMSS'],
    #                 'gravado_infonavit': localdict[rule.code + '_GRV_INFONAVIT'],
    #                 'exento_infonavit': localdict[rule.code + '_EXT_INFONAVIT'],
    #                 'gravado_ptu': localdict[rule.code + '_GRV_PTU'],
    #                 'exento_ptu': localdict[rule.code + '_EXT_PTU'],
    #                 'gravado_local': localdict[rule.code + '_GRV_LOCAL'],
    #                 'exento_local': localdict[rule.code + '_EXT_LOCAL']
    #             }
    #     print ("Result =-=-=", result.values())
    #     return result.values()

    @api.model
    def get_fper(self):
        da = literal_eval(self.env['ir.config_parameter'].sudo(
        ).get_param('cfdi_nomina.DA') or '0')
        return da / 12 / 15

    def save_subsidio(self, rule_localdict):
        self.sube = rule_localdict.get('SUBE', 0)
        _logger.info("sube: {}".format(self.sube))
        # Permite regresar subsidio negativo para fines de registro en tablas
        subsidio_causado = self._get_subsidio_causado(no_negativo=False)
        # subsidio_causado = self._get_subsidio_causado_rule(rule_localdict, no_negativo=False)
        subsidio_causado = round(subsidio_causado, 2)

        self.subsidio_causado = subsidio_causado
        # _logger.info("subsidio_causado_rule: {}".format(subsidio_causado_rule))
        _logger.info("subsidio_causado: {}".format(subsidio_causado))

        # sube_calc = self._get_sube_calc(no_negativo=False)
        sube_calc = self._get_sube_calc_rule(rule_localdict, no_negativo=False)
        sube_calc = round(sube_calc, 2)

        rule_localdict['SUBE_NC'] += sube_calc
        self.sube_calc = sube_calc
        _logger.info("sube_calc: {}".format(sube_calc))

    def save_ispt(self, rule_localdict):
        self.ispt = rule_localdict.get('ISPT', 0)
        _logger.info("ispt: {}".format(self.ispt))
        # Permite regresar subsidio negativo para fines de registro en tablas
        # ispt_calc = self._get_ispt_calc(no_negativo=False)
        ispt_calc = self._get_ispt_calc_rule(rule_localdict, no_negativo=False)
        ispt_calc = round(ispt_calc, 2)

        rule_localdict['ISPT_NC'] += ispt_calc
        self.ispt_calc = ispt_calc
        _logger.info("ispt_calc: {}".format(ispt_calc))

    def calculate_sdi(self, rule_localdict):

        def last_day_of_month(date):
            if date.month == 12:
                return date.replace(day=31)
            return date.replace(month=date.month + 1, day=1) - timedelta(days=1)

        self.ensure_one()

        sdi_fijo = sdi_var = 0.0
        employee = self.employee_id
        self.sdi_info_calc_ids.unlink()
        self.sdip_info_calc_ids.unlink()
        self.sdiv_info_calc_ids.unlink()
        sdi_info_calc_ids = []
        sdip_info_calc_ids = []
        sdiv_info_calc_ids = []

        tipo_sueldo = (employee.tipo_sueldo or '').upper()
        if tipo_sueldo in ['FIJO', 'MIXTO', '']:
            # Sumar todos los ingresos fijos gravable imss de reglas salariales fijas en la nomina actual,
            # se divide entre dias TRABAJADOS del periodo
            dias_trabajados = self._get_days("WORK100")[0]
            sdi_info_calc_ids.append(
                (0, 0, {'name': 'Dias trabajados', 'value': dias_trabajados}))
            # Días por Año / DA
            # da = literal_eval(self.env['ir.config_parameter'].sudo().get_param('cfdi_nomina.DA') or '0')
            da = rule_localdict.get('DA')
            # Dias Prima Vacacional
            # dpv = employee.tabla_vacaciones_id and employee.tabla_vacaciones_id.get_prima_vacation_days(employee.anos_servicio) or 0
            dpv = rule_localdict.get('DPV')
            sdi_info_calc_ids.append(
                (0, 0, {'name': 'Dias prima vacacional', 'code': 'DPV', 'value': dpv}))
            # Dias Aguinaldo
            # dag = employee.tabla_sdi_id and employee.tabla_sdi_id.get_aguinaldo_days(employee.anos_servicio) or 0
            dag = rule_localdict.get('DAG')
            sdi_info_calc_ids.append(
                (0, 0, {'name': 'Dias aguinaldo', 'code': 'DAG', 'value': dag}))
            sdi_info_calc_ids.append(
                (0, 0, {'name': 'Años servicio', 'value': employee.anos_servicio}))

            # Usar percepciones gravadas fijas imss
            if rule_localdict.get('TOTAL_GRV_FIJO_IMSS'):
                sueldo = rule_localdict.get('TOTAL_GRV_FIJO_IMSS')
                for fijo in rule_localdict.get('gravado_fijo_list'):
                    sdip_info_calc_ids.append((0, 0, fijo))
            else:
                lines_nomina_fija = self.line_ids.filtered(lambda l: bool(
                    l.gravado_imss) and l.tipo_de_percepcion == 'fijo')
                # sueldo = sum(lines_nomina_fija.mapped('gravado_imss'))
                # sueldo = sdo * dias_trabajados
                sueldo = 0.0
                for line in lines_nomina_fija:
                    sueldo += line.gravado_imss
                    sdip_info_calc_ids.append(
                        (0, 0, {'name': line.name, 'code': line.code, 'value': line.gravado_imss}))

            # Salario diario ordinario
            sdo = employee.sueldo_diario
            # sdo = sueldo / dias_trabajados
            sdi_info_calc_ids.insert(
                0, (0, 0, {'name': 'Salario diario ordinario', 'code': 'SDO', 'value': sdo}))

            parte_prop_prima_vacacional = sdo * dpv / da * dias_trabajados
            sdip_info_calc_ids.append(
                (0, 0, {'name': 'Parte prop. prima vacacional', 'value': parte_prop_prima_vacacional}))

            parte_prop_aguinaldo = dag * sdo / da * dias_trabajados
            sdip_info_calc_ids.append(
                (0, 0, {'name': 'Parte prop. aguinaldo', 'value': parte_prop_aguinaldo}))

            total_percepciones = sueldo + parte_prop_prima_vacacional + parte_prop_aguinaldo
            sdip_info_calc_ids.append(
                (0, 0, {'name': 'Total percepciones', 'value': total_percepciones}))

            sdi_fijo = total_percepciones / dias_trabajados if dias_trabajados else 0

            # Factor de Integracion
            # fi = employee.tabla_sdi_id.get_fi(employee.anos_servicio)
            fi = sdi_fijo / sdo if sdo else 1
            sdi_info_calc_ids.insert(
                0, (0, 0, {'name': 'Factor Integracion', 'value': fi}))

        if tipo_sueldo in ['VARIABLE', 'MIXTO', '']:
            # Buscar los ultimos 2 meses completos de nomina confirmadas.
            # de acuerdo al calendario de la tabla IMSS
            tabla_id = self.env.ref('cfdi_nomina.hr_taxable_base_id2').id,
            tbgrv = self.env['hr.basegravable.acum'].browse(tabla_id)
            if not tbgrv:
                raise UserError(
                    'No hay tabla Base Gravable con id %s' % tabla_id)
            if not tbgrv.acum_calendar_id:
                raise UserError(
                    'No hay calendario definido para la tabla Base Gravable %s' % tbgrv.name)

            str_start_date, str_end_date = tbgrv.acum_calendar_id.get_periodo_anterior(
                self.date_from)

            nomina_bimestral = self.env['hr.payslip'].search([
                ('employee_id', '=', employee.id),
                ('state', '=', 'done'),
                ('date_from', '>=', str_start_date),
                ('date_to', '<=', str_end_date),
                ('tipo_nomina', 'in', ['O', False]),  # Solo nominas ordinarias
                '|',
                ('registro_patronal_codigo', '=',
                 self.company_id.registro_patronal.name),
                ('registro_patronal_codigo_new', '=',
                 self.company_id.registro_patronal.name),
            ])

            if nomina_bimestral:

                bimestre_worked_days = 0
                nomina_bimestral_ids = []
                for nominab in nomina_bimestral:
                    bimestre_worked_days += nominab._get_days("WORK100")[0]
                    nomina_bimestral_ids.append(nominab.id)

                sdiv_info_calc_ids.append(
                    (0, 0, {'name': 'Dias trabajados Bimestre', 'value': bimestre_worked_days}))

                lines_nomina_bimestral_ids = self.env['hr.payslip.line'].search([
                    ('slip_id', 'in', nomina_bimestral_ids),
                    ('gravado_imss', '>', 0),  # Usar total_gravado imss
                    ('tipo_de_percepcion', '=', 'variable'),
                ])
                # total_percepciones = sum(lines_nomina_bimestral_ids.mapped('gravado_imss'))
                total_percepciones = 0.0
                pvar_dict = {}
                for line in lines_nomina_bimestral_ids:
                    total_percepciones += line.gravado_imss
                    current_pvar_struct = pvar_dict.setdefault(line.code, {
                        'name': line.name,
                        'code': line.code,
                        'value': 0,
                    })
                    current_pvar_struct['value'] += line.gravado_imss

                for pvar, v in pvar_dict.items():
                    sdiv_info_calc_ids.append((0, 0, v))

                sdiv_info_calc_ids.append(
                    (0, 0, {'name': 'Percepciones bimestre', 'value': total_percepciones}))

                sdi_var = bimestre_worked_days and total_percepciones / bimestre_worked_days or 0

            else:
                # Si no hay nominas anteriores se toma el SALARIO BASE DE
                # COTIZACION del empelado para SDI_FIJO
                sdi_fijo = employee.sueldo_imss

        self.write({
            'sdi_info_calc_ids': sdi_info_calc_ids,
            'sdip_info_calc_ids': sdip_info_calc_ids,
            'sdiv_info_calc_ids': sdiv_info_calc_ids,
            'sdi_fijo': sdi_fijo,
            'sdi_var': sdi_var,
            'sdi': sdi_fijo + sdi_var,
        })

        employee.sueldo_imss = sdi_fijo + sdi_var

        return sdi_fijo + sdi_var

    def calculate_sdi_last_rules(self, rule_localdict):
        # Mismos calculos, pero para el bimestre actual,
        # el diccionario de reglas en tiempo de calculo de nomina actual

        self.ensure_one()

        sdi_fijo = sdi_var = 0.0
        employee = self.employee_id
        # Se eliminan los datos anteriores
        self.sdi_info_calc_last_ids.unlink()
        self.sdip_info_calc_last_ids.unlink()
        self.sdiv_info_calc_last_ids.unlink()
        sdi_info_calc_ids = []
        sdip_info_calc_ids = []
        sdiv_info_calc_ids = []

        # Solo si la nomina tiene calculo ajustado o anual
        if self.tipo_calculo not in ['ajustado', 'anual']:
            return 0

        tipo_sueldo = (employee.tipo_sueldo or '').upper()
        if tipo_sueldo in ['FIJO', 'MIXTO', '']:
            # Sumar todos los ingresos fijos gravable imss de reglas salariales fijas en la nomina actual,
            # se divide entre dias TRABAJADOS del periodo
            dias_trabajados = self._get_days("WORK100")[0]
            sdi_info_calc_ids.append(
                (0, 0, {'name': 'Dias trabajados', 'value': dias_trabajados}))
            # Días por Año / DA
            # da = literal_eval(self.env['ir.config_parameter'].sudo().get_param('cfdi_nomina.DA') or '0')
            da = rule_localdict.get('DA')

            # Se obtienen fecha de la siguiente quincena
            next_quincena = datetime.strptime(
                self.date_to, DEFAULT_SERVER_DATE_FORMAT) + timedelta(days=15)
            next_quincena = next_quincena.strftime(DEFAULT_SERVER_DATE_FORMAT)

            # Dias Prima Vacacional
            # Calcular años servicio para el bimestre siguiente
            anos_servicio = employee.get_anos_servicio(next_quincena)

            dpv = employee.tabla_vacaciones_id and employee.tabla_vacaciones_id.get_prima_vacation_days(
                anos_servicio) or 0
            # dpv = rule_localdict.get('DPV')
            sdi_info_calc_ids.append(
                (0, 0, {'name': 'Dias prima vacacional', 'code': 'DPV', 'value': dpv}))
            # Dias Aguinaldo
            dag = employee.tabla_sdi_id and employee.tabla_sdi_id.get_aguinaldo_days(
                anos_servicio) or 0
            # dag = rule_localdict.get('DAG')
            sdi_info_calc_ids.append(
                (0, 0, {'name': 'Dias aguinaldo', 'code': 'DAG', 'value': dag}))
            sdi_info_calc_ids.append(
                (0, 0, {'name': 'Años servicio', 'value': anos_servicio}))

            # Usar percepciones gravadas fijas imss
            if rule_localdict.get('TOTAL_GRV_FIJO_IMSS'):
                sueldo = rule_localdict.get('TOTAL_GRV_FIJO_IMSS')
                for fijo in rule_localdict.get('gravado_fijo_list'):
                    sdip_info_calc_ids.append((0, 0, fijo))
            else:
                lines_nomina_fija = self.line_ids.filtered(
                    lambda l: bool(l.gravado_imss) and l.tipo_de_percepcion == 'fijo')
                # sueldo = sum(lines_nomina_fija.mapped('gravado_imss'))
                # sueldo = sdo * dias_trabajados
                sueldo = 0.0
                for line in lines_nomina_fija:
                    sueldo += line.gravado_imss
                    sdip_info_calc_ids.append(
                        (0, 0, {'name': line.name, 'code': line.code, 'value': line.gravado_imss}))

            # Salario diario ordinario
            # sdo = employee.sueldo_diario
            sdo = sueldo / dias_trabajados if dias_trabajados else 0
            sdi_info_calc_ids.insert(0, (0, 0, {
                'name': 'Salario diario ordinario',
                'code': 'SDO',
                'value': sdo
            }))

            parte_prop_prima_vacacional = sdo * dpv / da * dias_trabajados
            sdip_info_calc_ids.append(
                (0, 0, {'name': 'Parte prop. prima vacacional', 'value': parte_prop_prima_vacacional}))

            parte_prop_aguinaldo = dag * sdo / da * dias_trabajados
            sdip_info_calc_ids.append(
                (0, 0, {'name': 'Parte prop. aguinaldo', 'value': parte_prop_aguinaldo}))

            total_percepciones = sueldo + parte_prop_prima_vacacional + parte_prop_aguinaldo
            sdip_info_calc_ids.append(
                (0, 0, {'name': 'Total percepciones', 'value': total_percepciones}))

            sdi_fijo = total_percepciones / dias_trabajados if dias_trabajados else 0

            # Factor de Integracion
            # fi = employee.tabla_sdi_id.get_fi(employee.anos_servicio)
            fi = sdi_fijo / sdo if sdo else 1
            sdi_info_calc_ids.insert(
                0, (0, 0, {'name': 'Factor Integracion', 'value': fi}))

        if tipo_sueldo in ['VARIABLE', 'MIXTO', '']:
            # Buscar los ultimos 2 meses completos de nomina confirmadas.
            # de acuerdo al calendario de la tabla IMSS
            tabla_id = self.env.ref('cfdi_nomina.hr_taxable_base_id2').id,
            tbgrv = self.env['hr.basegravable.acum'].browse(tabla_id)
            if not tbgrv:
                raise UserError(
                    'No hay tabla Base Gravable con id %s' % tabla_id)
            if not tbgrv.acum_calendar_id:
                raise UserError(
                    'No hay calendario definido para la tabla Base Gravable %s' % tbgrv.name)

            # Datos del periodo actual
            str_start_date, str_end_date = tbgrv.acum_calendar_id.get_periodo_actual(
                self.date_from)

            nomina_bimestral = self.env['hr.payslip'].search([
                ('employee_id', '=', employee.id),
                ('state', '=', 'done'),
                ('date_from', '>=', str_start_date),
                ('date_to', '<=', str_end_date),
                ('tipo_nomina', 'in', ['O', False]),  # Solo nominas ordinarias
                '|',
                ('registro_patronal_codigo', '=',
                 self.company_id.registro_patronal.name),
                ('registro_patronal_codigo_new', '=',
                 self.company_id.registro_patronal.name),
            ])

            if nomina_bimestral:

                bimestre_worked_days = 0
                nomina_bimestral_ids = []
                for nominab in nomina_bimestral:
                    bimestre_worked_days += nominab._get_days("WORK100")[0]
                    nomina_bimestral_ids.append(nominab.id)

                # Mas dias nomina actual
                bimestre_worked_days += rule_localdict.get(
                    'worked_days').WORK100.number_of_days

                sdiv_info_calc_ids.append((0, 0, {
                    'name': 'Dias trabajados Bimestre',
                    'value': bimestre_worked_days,
                }))

                lines_nomina_bimestral_ids = self.env['hr.payslip.line'].search([
                    ('slip_id', 'in', nomina_bimestral_ids),
                    ('gravado_imss', '>', 0),  # Usar total_gravado imss
                    ('tipo_de_percepcion', '=', 'variable'),
                ])
                # total_percepciones = sum(lines_nomina_bimestral_ids.mapped('gravado_imss'))
                total_percepciones = 0.0
                pvar_dict = {}

                for line in lines_nomina_bimestral_ids:
                    total_percepciones += line.gravado_imss
                    current_pvar_struct = pvar_dict.setdefault(line.code, {
                        'name': line.name,
                        'code': line.code,
                        'value': 0,
                    })
                    current_pvar_struct['value'] += line.gravado_imss

                # Mas lineas de la nomina actual
                # Usar percepciones gravadas variables imss
                gravado_variable_list = rule_localdict.get(
                    'gravado_variable_list')
                if not gravado_variable_list:
                    lines_nomina_variable = self.line_ids.filtered(
                        lambda l: bool(l.gravado_imss) and l.tipo_de_percepcion == 'variable')
                    for line in lines_nomina_variable:
                        gravado_variable_list.append({
                            'name': line.name,
                            'code': line.code,
                            'value': line.gravado_imss,
                        })
                # Agrupa la nomina actual en el diccionario.
                for v in gravado_variable_list:
                    total_percepciones += v.get('value', 0)
                    code = v.get('code')
                    if code not in pvar_dict:
                        pvar_dict[code] = v
                    else:
                        pvar_dict[code]['value'] += v.get('value')

                for pvar, v in pvar_dict.items():
                    sdiv_info_calc_ids.append((0, 0, v))

                sdiv_info_calc_ids.append((0, 0, {
                    'name': 'Percepciones bimestre',
                    'value': total_percepciones,
                }))

                sdi_var = bimestre_worked_days and total_percepciones / bimestre_worked_days or 0

            else:
                # Si no hay nominas anteriores se toma el SALARIO BASE DE
                # COTIZACION del empelado para SDI_FIJO
                sdi_fijo = employee.sueldo_imss

        self.write({
            'sdi_info_calc_last_ids': sdi_info_calc_ids,
            'sdip_info_calc_last_ids': sdip_info_calc_ids,
            'sdiv_info_calc_last_ids': sdiv_info_calc_ids,
            'sdi_fijo_last': sdi_fijo,
            'sdi_var_last': sdi_var,
            'sdi_last': sdi_fijo + sdi_var,
        })

        employee.sueldo_imss_bimestre_actual = sdi_fijo + sdi_var

        return sdi_fijo + sdi_var

    def calculate_sdi_last(self):
        # Mismos calculos, pero para el bimestre actual, usando datos ya
        # calculados

        self.ensure_one()

        sdi_fijo = sdi_var = 0.0
        employee = self.employee_id
        # Se eliminan los datos anteriores
        self.sdi_info_calc_last_ids.unlink()
        self.sdip_info_calc_last_ids.unlink()
        self.sdiv_info_calc_last_ids.unlink()
        sdi_info_calc_ids = []
        sdip_info_calc_ids = []
        sdiv_info_calc_ids = []

        # Solo si la nomina tiene calculo ajustado o anual
        if self.tipo_calculo not in ['ajustado', 'anual']:
            return 0

        tipo_sueldo = (employee.tipo_sueldo or '').upper()
        if tipo_sueldo in ['FIJO', 'MIXTO', '']:
            # Sumar todos los ingresos fijos gravable imss de reglas salariales fijas en la nomina actual,
            # se divide entre dias TRABAJADOS del periodo
            dias_trabajados = self._get_days("WORK100")[0]
            sdi_info_calc_ids.append(
                (0, 0, {'name': 'Dias trabajados', 'value': dias_trabajados}))
            # Días por Año / DA
            da = literal_eval(self.env['ir.config_parameter'].sudo(
            ).get_param('cfdi_nomina.DA') or '0')

            # Se obtienen fecha de la siguiente quincena
            next_quincena = datetime.strptime(
                self.date_to, DEFAULT_SERVER_DATE_FORMAT) + timedelta(days=15)
            next_quincena = next_quincena.strftime(DEFAULT_SERVER_DATE_FORMAT)

            # Dias Prima Vacacional
            # Calcular años servicio para el bimestre siguiente
            anos_servicio = employee.get_anos_servicio(next_quincena)

            dpv = employee.tabla_vacaciones_id and employee.tabla_vacaciones_id.get_prima_vacation_days(
                anos_servicio) or 0
            # dpv = rule_localdict.get('DPV')
            sdi_info_calc_ids.append(
                (0, 0, {'name': 'Dias prima vacacional', 'code': 'DPV', 'value': dpv}))
            # Dias Aguinaldo
            dag = employee.tabla_sdi_id and employee.tabla_sdi_id.get_aguinaldo_days(
                anos_servicio) or 0
            # dag = rule_localdict.get('DAG')
            sdi_info_calc_ids.append(
                (0, 0, {'name': 'Dias aguinaldo', 'code': 'DAG', 'value': dag}))
            sdi_info_calc_ids.append(
                (0, 0, {'name': 'Años servicio', 'value': anos_servicio}))

            # Usar percepciones gravadas fijas imss
            lines_nomina_fija = self.line_ids.filtered(lambda l: bool(
                l.gravado_imss) and l.tipo_de_percepcion == 'fijo')
            # sueldo = sum(lines_nomina_fija.mapped('gravado_imss'))
            # sueldo = sdo * dias_trabajados
            sueldo = 0.0
            for line in lines_nomina_fija:
                sueldo += line.gravado_imss
                sdip_info_calc_ids.append(
                    (0, 0, {'name': line.name, 'code': line.code,
                            'value': line.gravado_imss})
                )

            # Salario diario ordinario
            # sdo = employee.sueldo_diario
            sdo = sueldo / dias_trabajados if dias_trabajados else 0
            sdi_info_calc_ids.insert(
                0, (0, 0, {'name': 'Salario diario ordinario', 'code': 'SDO', 'value': sdo}))

            parte_prop_prima_vacacional = sdo * dpv / da * dias_trabajados
            sdip_info_calc_ids.append(
                (0, 0, {'name': 'Parte prop. prima vacacional', 'value': parte_prop_prima_vacacional}))

            parte_prop_aguinaldo = dag * sdo / da * dias_trabajados
            sdip_info_calc_ids.append(
                (0, 0, {'name': 'Parte prop. aguinaldo', 'value': parte_prop_aguinaldo}))

            total_percepciones = sueldo + parte_prop_prima_vacacional + parte_prop_aguinaldo
            sdip_info_calc_ids.append(
                (0, 0, {'name': 'Total percepciones', 'value': total_percepciones}))

            sdi_fijo = total_percepciones / dias_trabajados if dias_trabajados else 0

            # Factor de Integracion
            # fi = employee.tabla_sdi_id.get_fi(employee.anos_servicio)
            fi = sdi_fijo / sdo if sdo else 1
            sdi_info_calc_ids.insert(
                0, (0, 0, {'name': 'Factor Integracion', 'value': fi}))

        if tipo_sueldo in ['VARIABLE', 'MIXTO', '']:
            # Buscar los ultimos 2 meses completos de nomina confirmadas.
            # de acuerdo al calendario de la tabla IMSS
            tabla_id = self.env.ref('cfdi_nomina.hr_taxable_base_id2').id,
            tbgrv = self.env['hr.basegravable.acum'].browse(tabla_id)
            if not tbgrv:
                raise UserError(
                    'No hay tabla Base Gravable con id %s' % tabla_id)
            if not tbgrv.acum_calendar_id:
                raise UserError(
                    'No hay calendario definido para la tabla Base Gravable %s' % tbgrv.name)

            # Datos del periodo actual
            str_start_date, str_end_date = tbgrv.acum_calendar_id.get_periodo_actual(
                self.date_from)

            nomina_bimestral = self.env['hr.payslip'].search([
                ('employee_id', '=', employee.id),
                ('state', '=', 'done'),
                ('date_from', '>=', str_start_date),
                ('date_to', '<=', str_end_date),
                ('tipo_nomina', 'in', ['O', False]),  # Solo nominas ordinarias
                '|',
                ('registro_patronal_codigo', '=',
                 self.company_id.registro_patronal.name),
                ('registro_patronal_codigo_new', '=',
                 self.company_id.registro_patronal.name),
            ])

            if nomina_bimestral:

                bimestre_worked_days = 0
                nomina_bimestral_ids = []
                for nominab in nomina_bimestral:
                    bimestre_worked_days += nominab._get_days("WORK100")[0]
                    nomina_bimestral_ids.append(nominab.id)

                # Si la nomina actual aun no esta en estado terminado,
                # se agregan dias nomina actual, porque no fue incluido en el
                # search anterior
                if self.state != 'done':
                    # bimestre_worked_days += rule_localdict.get('worked_days').WORK100.number_of_days
                    bimestre_worked_days += self._get_days("WORK100")[0]

                sdiv_info_calc_ids.append((0, 0, {
                    'name': 'Dias trabajados Bimestre',
                    'value': bimestre_worked_days
                }))

                lines_nomina_bimestral_ids = self.env['hr.payslip.line'].search([
                    ('slip_id', 'in', nomina_bimestral_ids),
                    ('gravado_imss', '>', 0),  # Usar total_gravado imss
                    ('tipo_de_percepcion', '=', 'variable'),
                ])
                # total_percepciones = sum(lines_nomina_bimestral_ids.mapped('gravado_imss'))
                total_percepciones = 0.0
                pvar_dict = {}

                for line in lines_nomina_bimestral_ids:
                    total_percepciones += line.gravado_imss
                    current_pvar_struct = pvar_dict.setdefault(line.code, {
                        'name': line.name,
                        'code': line.code,
                        'value': 0,
                    })
                    current_pvar_struct['value'] += line.gravado_imss

                # Si la nomina actual aun no esta en estado terminado, se agregan
                # lineas nomina actual, porque no fue incluido en el search
                # anterior
                if self.state != 'done':
                    gravado_variable_list = []
                    lines_nomina_variable = self.line_ids.filtered(
                        lambda l: bool(l.gravado_imss) and l.tipo_de_percepcion == 'variable')
                    for line in lines_nomina_variable:
                        gravado_variable_list.append({
                            'name': line.name,
                            'code': line.code,
                            'value': line.gravado_imss,
                        })
                    # Agrupa la nomina actual en el diccionario.
                    for v in gravado_variable_list:
                        total_percepciones += v.get('value', 0)
                        code = v.get('code')
                        if code not in pvar_dict:
                            pvar_dict[code] = v
                        else:
                            pvar_dict[code]['value'] += v.get('value')

                for pvar, v in pvar_dict.items():
                    sdiv_info_calc_ids.append((0, 0, v))

                sdiv_info_calc_ids.append((0, 0, {
                    'name': 'Percepciones bimestre',
                    'value': total_percepciones
                }))

                sdi_var = bimestre_worked_days and total_percepciones / bimestre_worked_days or 0

            else:
                # Si no hay nominas anteriores se toma el SALARIO BASE DE
                # COTIZACION del empelado para SDI_FIJO
                sdi_fijo = employee.sueldo_imss

        self.write({
            'sdi_info_calc_last_ids': sdi_info_calc_ids,
            'sdip_info_calc_last_ids': sdip_info_calc_ids,
            'sdiv_info_calc_last_ids': sdiv_info_calc_ids,
            'sdi_fijo_last': sdi_fijo,
            'sdi_var_last': sdi_var,
            'sdi_last': sdi_fijo + sdi_var,
        })

        employee.sueldo_imss_bimestre_actual = sdi_fijo + sdi_var

        return sdi_fijo + sdi_var

    def get_acumulado_tabla(self, anual_lines, tabla_id, name=None, field_name=None):
        self.ensure_one()
        payslip = self
        tbgrv = self.env['hr.basegravable.acum'].browse(tabla_id)
        if not tbgrv:
            raise UserError('No hay tabla Base Gravable con id %s' % tabla_id)

        if not tbgrv.acum_calendar_id:
            raise UserError(
                'No hay calendario definido para la tabla Base Gravable %s' % tbgrv.name)

        field_name = field_name or tbgrv.data_field
        # No incluye nomina actual
        anual_ac_lines = anual_lines.filtered(
            lambda l: l.slip_id.id != payslip.id)
        anual = sum(anual_ac_lines.mapped(field_name))

        anterior = 0
        fecha1, fecha2 = tbgrv.acum_calendar_id.get_periodo_anterior(
            payslip.date_from)
        if fecha1:
            lines_anterior = anual_ac_lines.filtered(
                lambda l: l.slip_id.date_from >= fecha1 and l.slip_id.date_to <= fecha2
            )
            anterior = sum(lines_anterior.mapped(field_name))

        fecha1, fecha2 = tbgrv.acum_calendar_id.get_periodo_actual(
            payslip.date_to)
        # No incluye nomina actual
        lines_actual = anual_ac_lines.filtered(
            lambda l: l.slip_id.date_from >= fecha1 and l.slip_id.date_to <= fecha2
        )
        actual_ac = sum(lines_actual.mapped(field_name))
        # payslip_lines = self.env['hr.payslip.line'].search([
        #     ('slip_id.date_from', '>=', fecha1),
        #     ('slip_id.date_to', '<=', fecha2),
        #     ('slip_id.employee_id', '=', payslip.employee_id.id),
        #     ('slip_id.state', '=', 'done'),
        #     ('slip_id.id', '!=', payslip.id),
        # ])
        # actual_ac = sum(payslip_lines.mapped(field_name))

        # Solo nomina actual
        actual_nomina = sum(payslip.line_ids.mapped(field_name))

        return {
            'name': name or tbgrv.name,
            'code': None,
            'actual_nc': actual_ac + actual_nomina,
            'actual_ac': actual_ac,
            'anterior': anterior,
            'anual': anual,
        }

    def get_acumulado_dias(self, tabla_id, name=None):
        self.ensure_one()
        payslip = self
        field_name = 'number_of_days'
        tbgrv = self.env['hr.basegravable.acum'].browse(tabla_id)
        if not tbgrv:
            raise UserError('No hay tabla Base Gravable con id %s' % tabla_id)

        if not tbgrv.acum_calendar_id:
            raise UserError(
                'No hay calendario definido para la tabla Base Gravable %s' % tbgrv.name)

        fecha_fin = Datetime.from_string(payslip.date_to)
        # No incluir nomina actual
        anual_worked_days = self.env['hr.payslip.worked_days'].search([
            ('payslip_id.date_from', '>=', datetime(
                year=fecha_fin.year, month=1, day=1)),
            ('payslip_id.date_to', '<=', fecha_fin),
            ('payslip_id.employee_id', '=', payslip.employee_id.id),
            ('payslip_id.state', '=', 'done'),
            ('code', '=', 'WORK100'),
            ('payslip_id', '!=', payslip.id)
        ])

        anual = sum(anual_worked_days.mapped(field_name))

        anterior = 0
        fecha1, fecha2 = tbgrv.acum_calendar_id.get_periodo_anterior(
            payslip.date_from)
        if fecha1:
            lines_anterior = anual_worked_days.filtered(
                lambda l: l.payslip_id.date_from >= fecha1 and l.payslip_id.date_to <= fecha2
            )
            anterior = sum(lines_anterior.mapped(field_name))

        fecha1, fecha2 = tbgrv.acum_calendar_id.get_periodo_actual(
            payslip.date_to)
        # No incluye nomina actual
        lines_actual = anual_worked_days.filtered(
            lambda l: l.payslip_id.date_from >= fecha1 and l.payslip_id.date_to <= fecha2
        )
        actual_ac = sum(lines_actual.mapped(field_name))

        # Solo nomina actual
        payslip_worked_line = payslip.worked_days_line_ids.filtered(
            lambda l: l.code == "WORK100")
        actual_nomina = sum(payslip_worked_line.mapped(field_name))

        return {
            'name': name or tbgrv.name,
            'actual_nc': actual_ac + actual_nomina,
            'actual_ac': actual_ac,
            'anterior': anterior,
            'anual': anual,
        }

    def get_acumulado_imss_dias(self):
        self.ensure_one()
        payslip = self
        tabla_basegrv_imss_id = self.env.ref(
            'cfdi_nomina.hr_taxable_base_id2').id
        tbgrv = self.env['hr.basegravable.acum'].browse(
            tabla_basegrv_imss_id)
        if not tbgrv:
            raise UserError('No hay tabla Base Gravable con id %s' %
                            tabla_basegrv_imss_id)

        if not tbgrv.acum_calendar_id:
            raise UserError(
                'No hay calendario definido para la tabla Base Gravable %s' % tbgrv.name)

        fecha_fin = Datetime.from_string(payslip.date_to)
        anual_days = self.env['hr.payslip.worked_days'].search([
            ('payslip_id.date_from', '>=', datetime(
                year=fecha_fin.year, month=1, day=1)),
            ('payslip_id.date_to', '<=', fecha_fin),
            ('payslip_id.employee_id', '=', payslip.employee_id.id),
            ('payslip_id.state', '=', 'done'),
            ('code', '!=', 'WORK100'),
        ])

        anual_payslips = self.env['hr.payslip'].search([
            # ('company_id', '=', payslip.company_id.id),
            ('date_from', '>=', datetime(year=fecha_fin.year, month=1, day=1)),
            ('date_to', '<=', fecha_fin),
            ('employee_id', '=', payslip.employee_id.id),
            ('state', '=', 'done'),
        ])
        anual = 0
        for p in anual_payslips:
            date_from = fields.Date.from_string(p.date_from)
            date_to = fields.Date.from_string(p.date_to)
            anual += (date_to - date_from).days + 1

        anual_aus = anual_inc = 0
        for line in anual_days:
            line.calc_dias_imss()  # JGO  un rato
            anual_aus += line.dias_imss_ausencia
            anual_inc += line.dias_imss_incapacidad

        anterior = ant_aus = ant_inc = 0
        fecha1, fecha2 = tbgrv.acum_calendar_id.get_periodo_anterior(
            payslip.date_from)
        if fecha1:
            ant_payslips = anual_payslips.filtered(
                lambda l: l.date_from >= fecha1 and l.date_to <= fecha2)
            anterior = 0
            for p in ant_payslips:
                date_from = fields.Date.from_string(p.date_from)
                date_to = fields.Date.from_string(p.date_to)
                anterior += (date_to - date_from).days + 1

            ant_days = anual_days.filtered(
                lambda l: l.payslip_id.date_from >= fecha1 and l.payslip_id.date_to <= fecha2
            )
            ant_aus = ant_inc = 0
            for line in ant_days:
                line.calc_dias_imss()  # JGO  un rato
                ant_aus += line.dias_imss_ausencia
                ant_inc += line.dias_imss_incapacidad

        fecha1, fecha2 = tbgrv.acum_calendar_id.get_periodo_actual(
            payslip.date_to)
        actual_payslips = anual_payslips.filtered(
            lambda l: l.date_from >= fecha1 and l.date_to <= fecha2)
        actual_ac = 0
        for p in actual_payslips:
            date_from = fields.Date.from_string(p.date_from)
            date_to = fields.Date.from_string(p.date_to)
            actual_ac += (date_to - date_from).days + 1

        actual_days = anual_days.filtered(
            lambda l: l.payslip_id.date_from >= fecha1 and l.payslip_id.date_to <= fecha2
        )
        act_ac_aus = act_ac_inc = 0
        for line in actual_days:
            line.calc_dias_imss()  # JGO  un rato
            act_ac_aus += line.dias_imss_ausencia
            act_ac_inc += line.dias_imss_incapacidad

        date_from = fields.Date.from_string(payslip.date_from)
        date_to = fields.Date.from_string(payslip.date_to)
        actual_nomina = (date_to - date_from).days + 1
        act_nom_aus = act_nom_inc = 0
        for line in payslip.worked_days_line_ids.filtered(lambda l: l.code != "WORK100"):
            line.calc_dias_imss()  # JGO  un rato
            act_nom_aus += line.dias_imss_ausencia
            act_nom_inc += line.dias_imss_incapacidad

        return {
            'actual_imss_nc': (actual_ac - act_ac_aus) + (actual_nomina - act_nom_aus),
            'actual_imss2_nc': (actual_ac - act_ac_inc) + (actual_nomina - act_nom_inc),
            'actual_imss_ac': actual_ac - act_ac_aus,
            'actual_imss2_ac': actual_ac - act_ac_inc,
            'anterior_imss': anterior - ant_aus,
            'anterior_imss2': anterior - ant_inc,
            'anual_imss': anual - anual_aus,
            'anual_imss2': anual - anual_inc,
        }

    def get_acumulado_rule(self, lines, rules, prefijo=''):
        self.ensure_one()
        payslip = self
        field_name = 'total'

        result = []
        for rule in rules:
            # No incluye nomina actual
            lines_anual = lines.filtered(
                lambda l: l.salary_rule_id.id == rule.id and l.slip_id.id != payslip.id)
            anual = sum(lines_anual.mapped(field_name))

            if not rule.acum_calendar_id:
                raise UserError('No hay calendario definido para la regla %s '
                                'y se necesita para calculo de montos acumulados' % rule.name)

            anterior = 0
            fecha1, fecha2 = rule.acum_calendar_id.get_periodo_anterior(
                payslip.date_from)
            if fecha1:
                lines_anterior = lines_anual.filtered(
                    lambda l: l.slip_id.date_from >= fecha1 and l.slip_id.date_to <= fecha2
                )
                anterior = sum(lines_anterior.mapped(field_name))

            fecha1, fecha2 = rule.acum_calendar_id.get_periodo_actual(
                payslip.date_from)
            # No incluye nomina actual
            lines_actual = lines_anual.filtered(
                lambda l: l.slip_id.date_from >= fecha1 and l.slip_id.date_to <= fecha2
            )
            actual_ac = sum(lines_actual.mapped(field_name))

            payslip_rules = payslip.line_ids.filtered(
                lambda l: l.salary_rule_id and l.salary_rule_id.id == rule.id)
            # Solo nomina actual
            actual_nomina = sum(payslip_rules.mapped(field_name))

            data_line = {
                # 'name': prefijo + rule.name,
                'name': "[{}] {}".format(rule.code, rule.name),
                'code': rule.code,
                'actual_nc': actual_ac + actual_nomina,
                'actual_ac': actual_ac,
                'anterior': anterior,
                'anual': anual,
            }

            result.append(data_line)

        return result

    def get_anual_lines(self):
        # Regresa todas la Lineas Calculo de as nominas confirmadas del
        # empleado,
        self.ensure_one()
        payslip = self

        fecha_fin = Datetime.from_string(payslip.date_to)
        anual_lines = self.env['hr.payslip.line'].search([
            ('slip_id.date_from', '>=', datetime(
                year=fecha_fin.year, month=1, day=1)),
            ('slip_id.date_to', '<=', fecha_fin),
            ('slip_id.employee_id', '=', payslip.employee_id.id),
            ('slip_id.state', '=', 'done'),
            ('slip_id.id', '!=', payslip.id),  # No incluye nomina actual
        ])
        return anual_lines

    def get_anual_slip(self):
        # Regresa todas ls nominas del año del empleado
        self.ensure_one()
        payslip = self

        fecha_ini = Datetime.from_string(payslip.date_to)
        nominas_anuales = self.search([
            ('date_from', '>=', datetime(year=fecha_ini.year, month=1, day=1)),
            ('date_to', '<=', payslip.date_to),
            ('employee_id', '=', payslip.employee_id.id),
            ('state', '=', 'done'),
            ('id', '!=', payslip.id),
        ])

        return nominas_anuales

    def get_acumulado_lines(self):
        self.ensure_one()
        payslip = self
        lines = []

        # Lineas Calculo Anual
        anual_lines = self.get_anual_lines()

        # Ingresos Exentos ISR
        tabla_basegravable_id = self.env.ref(
            'cfdi_nomina.hr_taxable_base_id1').id
        data_grv = payslip.get_acumulado_tabla(anual_lines, tabla_basegravable_id,
                                               name='Ingresos Exentos', field_name='exento')
        lines.append((0, 0, data_grv))
        # Datos de la tabla de base gravable
        base_gravable_ids = [
            self.env.ref('cfdi_nomina.hr_taxable_base_id1').id,
            self.env.ref('cfdi_nomina.hr_taxable_base_id2').id,
            self.env.ref('cfdi_nomina.hr_taxable_base_id3').id,
            self.env.ref('cfdi_nomina.hr_taxable_base_id4').id,
            self.env.ref('cfdi_nomina.hr_taxable_base_id5').id,
        ]
        for base_gravable_id in base_gravable_ids:
            data_grv = payslip.get_acumulado_tabla(
                anual_lines, base_gravable_id)
            data_grv.update(base_grv_id=base_gravable_id)
            lines.append((0, 0, data_grv))

        # Sueldo fijo IMSS
        lines_nomina_fija = anual_lines.filtered(lambda l: bool(
            l.gravado_imss) > 0 and l.tipo_de_percepcion == 'fijo')
        tabla_basegrv_imss_id = self.env.ref(
            'cfdi_nomina.hr_taxable_base_id2').id
        data_grv = payslip.get_acumulado_tabla(lines_nomina_fija, tabla_basegrv_imss_id,
                                               name='Sueldo fijo IMSS', field_name='gravado_imss')
        lines.append((0, 0, data_grv))

        # Dias trabajados IMSS
        data_imss = payslip.get_acumulado_imss_dias()
        lines.append((0, 0, {
            'name': 'Dias trabajados IMSS',
            'actual_nc': data_imss.get('actual_imss_nc'),
            'actual_ac': data_imss.get('actual_imss_ac'),
            'anterior': data_imss.get('anterior_imss'),
            'anual': data_imss.get('anual_imss'),
        }))
        lines.append((0, 0, {
            'name': 'Dias trabajados INFONAVIT',
            'actual_nc': data_imss.get('actual_imss2_nc'),
            'actual_ac': data_imss.get('actual_imss2_ac'),
            'anterior': data_imss.get('anterior_imss2'),
            'anual': data_imss.get('anual_imss2'),
        }))

        # Dias trabajados del mes ( usa el calendario de la tabla ISR )
        data_grv = payslip.get_acumulado_dias(self.env.ref('cfdi_nomina.hr_taxable_base_id1').id,
                                              name="Dias trabajados del mes")
        lines.append((0, 0, data_grv))

        # Percepciones
        percepcion_id = self.env.ref('cfdi_nomina.catalogo_tipo_percepcion').id
        tipo_otropago_id = self.env.ref(
            'cfdi_nomina.catalogo_tipo_otro_pago').id
        per_lines = anual_lines.filtered(
            lambda l: l.salary_rule_id and l.salary_rule_id.tipo_id.id in [percepcion_id, tipo_otropago_id])
        rules = list(set([line.salary_rule_id for line in per_lines]))
        per_data = payslip.get_acumulado_rule(
            per_lines, rules, prefijo='PER: ')
        for data_grv in per_data:
            lines.append((0, 0, data_grv))

        # Deducciones
        deduccion_id = self.env.ref('cfdi_nomina.catalogo_tipo_deduccion').id
        ded_lines = anual_lines.filtered(
            lambda l: l.salary_rule_id and l.salary_rule_id.tipo_id.id == deduccion_id)
        rules = list(set([line.salary_rule_id for line in ded_lines]))
        ded_data = payslip.get_acumulado_rule(
            ded_lines, rules, prefijo='DED: ')
        for data_grv in ded_data:
            lines.append((0, 0, data_grv))

        nominas_anuales = self.get_anual_slip()

        # Subsidio causado
        data_sub_causado = payslip.get_acumulado_subsidio_causado_lines(
            nominas_anuales)
        lines.append((0, 0, data_sub_causado))

        # SUB acum
        data_ispt = payslip.get_acumulado_sube_lines(nominas_anuales)
        lines.append((0, 0, data_ispt))

        # ISPT acum
        data_ispt = payslip.get_acumulado_ispt_lines(nominas_anuales)
        lines.append((0, 0, data_ispt))

        return lines

    def get_acumulado_ispt_lines(self, nominas_anuales=None):
        # Obtiene valores de ISPT calc acumulado y calcula el ipst nc
        # Lo salva en la nomina
        self.ensure_one()
        payslip = self

        tabla_id = self.env.ref('cfdi_nomina.hr_taxable_base_id1').id
        tbgrv = self.env['hr.basegravable.acum'].browse(tabla_id)
        if not tbgrv:
            raise UserError('No hay tabla Base Gravable con id %s' % tabla_id)

        if not tbgrv.acum_calendar_id:
            raise UserError(
                'No hay calendario definido para la tabla Base Gravable %s' % tbgrv.name)

        if not nominas_anuales:
            nominas_anuales = payslip.get_anual_slip()

        anual = sum(nominas_anuales.mapped('ispt_calc'))

        anterior = 0
        fecha1, fecha2 = tbgrv.acum_calendar_id.get_periodo_anterior(
            payslip.date_from)
        if fecha1:
            nom_anterior = nominas_anuales.filtered(
                lambda l: l.date_from >= fecha1 and l.date_to <= fecha2
            )
            anterior = sum(nom_anterior.mapped('ispt_calc'))

        fecha1, fecha2 = tbgrv.acum_calendar_id.get_periodo_actual(
            payslip.date_to)
        # No incluye nomina actual
        nom_actual = nominas_anuales.filtered(
            lambda l: l.date_from >= fecha1 and l.date_to <= fecha2
        )
        actual_ac = sum(nom_actual.mapped('ispt_calc'))

        # ISPT solo nomina actual
        actual_nomina = payslip.ispt_calc

        return {
            'name': 'ISPT',
            'code': None,
            'actual_nc': actual_ac + actual_nomina,
            'actual_ac': actual_ac,
            'anterior': anterior,
            'anual': anual,
        }

    def get_acumulado_sube_lines(self, nominas_anuales=None):
        # Obtiene valores de subsidio causado acumulado y calcula el subsidio causado de la nomina actual
        # Lo salva en la nomina
        self.ensure_one()
        payslip = self

        tabla_id = self.env.ref('cfdi_nomina.hr_taxable_base_id1').id
        tbgrv = self.env['hr.basegravable.acum'].browse(tabla_id)
        if not tbgrv:
            raise UserError('No hay tabla Base Gravable con id %s' % tabla_id)

        if not tbgrv.acum_calendar_id:
            raise UserError(
                'No hay calendario definido para la tabla Base Gravable %s' % tbgrv.name)

        if not nominas_anuales:
            nominas_anuales = payslip.get_anual_slip()

        anual = sum(nominas_anuales.mapped('sube_calc'))

        anterior = 0
        fecha1, fecha2 = tbgrv.acum_calendar_id.get_periodo_anterior(
            payslip.date_from)
        if fecha1:
            nom_anterior = nominas_anuales.filtered(
                lambda l: l.date_from >= fecha1 and l.date_to <= fecha2
            )
            anterior = sum(nom_anterior.mapped('sube_calc'))

        fecha1, fecha2 = tbgrv.acum_calendar_id.get_periodo_actual(
            payslip.date_to)
        # No incluye nomina actual
        nom_actual = nominas_anuales.filtered(
            lambda l: l.date_from >= fecha1 and l.date_to <= fecha2
        )
        actual_ac = sum(nom_actual.mapped('sube_calc'))

        # Subsidio calc solo nomina actual
        actual_nomina = payslip.sube_calc

        return {
            'name': 'SUBE',
            'code': None,
            'actual_nc': actual_ac + actual_nomina,
            'actual_ac': actual_ac,
            'anterior': anterior,
            'anual': anual,
        }

    def get_acumulado_subsidio_causado_lines(self, nominas_anuales=None):
        # Obtiene valores de subsidio causado acumulado y calcula el subsidio causado de la nomina actual
        # Lo salva en la nomina
        self.ensure_one()
        payslip = self

        tabla_id = self.env.ref('cfdi_nomina.hr_taxable_base_id1').id
        tbgrv = self.env['hr.basegravable.acum'].browse(tabla_id)
        if not tbgrv:
            raise UserError('No hay tabla Base Gravable con id %s' % tabla_id)

        if not tbgrv.acum_calendar_id:
            raise UserError(
                'No hay calendario definido para la tabla Base Gravable %s' % tbgrv.name)

        if not nominas_anuales:
            nominas_anuales = payslip.get_anual_slip()

        anual = sum(nominas_anuales.mapped('subsidio_causado'))

        anterior = 0
        fecha1, fecha2 = tbgrv.acum_calendar_id.get_periodo_anterior(
            payslip.date_from)
        if fecha1:
            nom_anterior = nominas_anuales.filtered(
                lambda l: l.date_from >= fecha1 and l.date_to <= fecha2
            )
            anterior = sum(nom_anterior.mapped('subsidio_causado'))

        fecha1, fecha2 = tbgrv.acum_calendar_id.get_periodo_actual(
            payslip.date_to)
        # No incluye nomina actual
        nom_actual = nominas_anuales.filtered(
            lambda l: l.date_from >= fecha1 and l.date_to <= fecha2
        )
        actual_ac = sum(nom_actual.mapped('subsidio_causado'))

        # Subsidio Causado solo nomina actual
        actual_nomina = payslip.subsidio_causado

        return {
            'name': 'Subsidio causado',
            'code': None,
            'actual_nc': actual_ac + actual_nomina,
            'actual_ac': actual_ac,
            'anterior': anterior,
            'anual': anual,
        }

    def set_acumulado_variables(self, localdict, sorted_rules):
        self.ensure_one()
        payslip = self

        # se toman todas las reglas para crear variables en 0
        for rule in self.env["hr.salary.rule"].search([]):
            localdict['{}_NC'.format(rule.code)] = 0
            localdict['{}_AC'.format(rule.code)] = 0
            localdict['{}_ANT'.format(rule.code)] = 0
            localdict['{}_AN'.format(rule.code)] = 0

        nominas_anuales = self.get_anual_slip()

        # Subsidio causado
        data_sube = payslip.get_acumulado_sube_lines(nominas_anuales)
        code = "SUBE"
        localdict['{}_NC'.format(code)] = data_sube.get('actual_ac', 0)
        localdict['{}_AC'.format(code)] = data_sube.get('actual_ac', 0)
        localdict['{}_ANT'.format(code)] = data_sube.get('anterior', 0)
        localdict['{}_AN'.format(code)] = data_sube.get('anual', 0)

        # ISPT calc
        data_ispt = payslip.get_acumulado_ispt_lines(nominas_anuales)
        code = "ISPT"
        localdict['{}_NC'.format(code)] = data_ispt.get('actual_ac', 0)
        localdict['{}_AC'.format(code)] = data_ispt.get('actual_ac', 0)
        localdict['{}_ANT'.format(code)] = data_ispt.get('anterior', 0)
        localdict['{}_AN'.format(code)] = data_ispt.get('anual', 0)

        # Lineas Calculo Anual
        anual_lines = self.get_anual_lines()
        if not anual_lines:
            # No hay datos anuales,
            return

        # Percepciones
        percepcion_id = self.env.ref('cfdi_nomina.catalogo_tipo_percepcion').id
        tipo_otropago_id = self.env.ref(
            "cfdi_nomina.catalogo_tipo_otro_pago").id
        per_lines = anual_lines.filtered(
            lambda l: l.salary_rule_id and l.salary_rule_id.tipo_id.id in [percepcion_id, tipo_otropago_id])
        rules = list(set([line.salary_rule_id for line in per_lines]))
        per_data = payslip.get_acumulado_rule(
            per_lines, rules, prefijo='PER: ')
        for data_grv in per_data:
            code = data_grv.get('code')
            localdict['{}_NC'.format(code)] = data_grv.get('actual_ac', 0)
            localdict['{}_AC'.format(code)] = data_grv.get('actual_ac', 0)
            localdict['{}_ANT'.format(code)] = data_grv.get('anterior', 0)
            localdict['{}_AN'.format(code)] = data_grv.get('anual', 0)

        # Deducciones
        deduccion_id = self.env.ref('cfdi_nomina.catalogo_tipo_deduccion').id
        ded_lines = anual_lines.filtered(
            lambda l: l.salary_rule_id and l.salary_rule_id.tipo_id.id == deduccion_id)
        rules = list(set([line.salary_rule_id for line in ded_lines]))
        ded_data = payslip.get_acumulado_rule(
            ded_lines, rules, prefijo='DED: ')
        for data_grv in ded_data:
            code = data_grv.get('code')
            localdict['{}_NC'.format(code)] = data_grv.get('actual_ac', 0)
            localdict['{}_AC'.format(code)] = data_grv.get('actual_ac', 0)
            localdict['{}_ANT'.format(code)] = data_grv.get('anterior', 0)
            localdict['{}_AN'.format(code)] = data_grv.get('anual', 0)

        return

    def recalc_acumulados(self):
        # recalcula acumulados
        for payslip in self:
            payslip.acumulado_ids.unlink()
            payslip.acumulado_ids = payslip.get_acumulado_lines()

    def migra_sube_causado_run(self):
        logging.info("Main    : before creating thread")
        threaded_calculation = threading.Thread(
            target=self.migra_test_thread, name=self.id)
        threaded_calculation.start()
        logging.info("Main    : wait for the thread to finish")
        return {}

    def migra_test_thread(self):
        cntx = dict(self.env.context)
        with api.Environment.manage():
            with registry(self.env.cr.dbname).cursor() as new_cr:
                new_env = api.Environment(new_cr, self.env.uid, cntx)
                for payslip in self.with_env(new_env):
                    payslip.with_env(new_env).migra_test()
        return {}

    def migra_test(self):
        from dateutil import relativedelta
        # from datetime import datetime
        # from ast import literal_eval

        acumulado_obj = self.env['hr.payslip.acumulado']
        payslip_obj = self.env['hr.payslip']
        ICPSudo = self.env['ir.config_parameter'].sudo()
        # empleados = self.env['hr.employee'].search([])
        # empleados = self.env['hr.employee'].search([('id', 'in', [4278, 4300, 5280])])
        empleados = self.env['hr.employee'].search(
            [('id', 'in', [4300, 4152])])  # Yancarlo
        total = len(empleados)
        i = 0
        fper = payslip_obj.get_fper()
        tabla_gravable_isr_id = self.env.ref(
            'cfdi_nomina.hr_taxable_base_id1').id
        tabla_isr_id = literal_eval(ICPSudo.get_param(
            'cfdi_nomina.NominaIPSTMensualID') or 'None')
        tabla_sube_id = literal_eval(ICPSudo.get_param(
            'cfdi_nomina.NominaSUBEID') or 'None')

        for emp in empleados:
            i += 1
            _logger.info("({}/{}) {}".format(i, total, emp.nombre_completo))
            # Periodos mensuales, solo diciembre
            for mes in range(1, 2):
                ini_mes = datetime(year=2020, month=mes, day=1)
                fin_mes = ini_mes + \
                          relativedelta.relativedelta(months=+1, days=-1)
                nominas_mes = payslip_obj.search([
                    ('employee_id', '=', emp.id),
                    ('state', '=', 'done'),
                    ('date_from', '>=', ini_mes),
                    ('date_to', '<=', fin_mes),
                ], order='date_from ASC')

                for slip in nominas_mes:
                    _logger.info("{}  {}--{}".format(slip.name,
                                                     slip.date_from, slip.date_to))

                    anual_lines = slip.get_anual_lines()
                    data_grv = slip.get_acumulado_tabla(
                        anual_lines, tabla_gravable_isr_id)
                    total_grv_isr_nc = data_grv.get('actual_nc', 0)

                    nominas_anuales = slip.get_anual_slip()

                    total_grv_isr_mensuaL = 0
                    if slip.tipo_calculo in ['mensual']:
                        total_grv_isr_mensuaL = total_grv_isr_nc * fper
                        _logger.info(
                            "total_grv_isr_nc: {} * {}".format(total_grv_isr_nc, fper))
                    elif slip.tipo_calculo in ['ajustado', 'anual']:
                        total_grv_isr_mensuaL = total_grv_isr_nc
                        _logger.info(
                            "total_grv_isr_nc: {} ".format(total_grv_isr_nc))

                    _logger.info("total_grv_isr_mensuaL calc: {}".format(
                        total_grv_isr_mensuaL))

                    # subex = self.env['hr.tabla.employment'].get_valor(total_grv_isr_mensuaL, tabla_sube_id)
                    # _logger.info("subex {}, sube {}".format(subex, slip.sube))
                    ispt = self.env['hr.ispt'].get_valor(
                        total_grv_isr_mensuaL, tabla_isr_id)

                    slip.ispt = round(ispt, 2)
                    ispt_calc = slip._get_ispt_calc()
                    slip.ispt_calc = round(ispt_calc, 2)
                    ispt_data = slip.get_acumulado_ispt_lines(nominas_anuales)
                    _logger.info("ispt calc: {}, ispt_data: {}".format(
                        ispt_calc, ispt_data))

                    sube_calc = slip._get_sube_calc()
                    slip.sube_calc = round(sube_calc, 2)
                    sube_data = slip.get_acumulado_sube_lines(nominas_anuales)
                    _logger.info("sube calc: {}, sube_data: {}".format(
                        sube_calc, sube_data))

                    acum_line = acumulado_obj.search([
                        ('slip_id', '=', slip.id),
                        ('name', 'in', ['ISPT', 'ISPT ', 'SUBE'])])
                    acum_line.unlink()

                    slip.write({
                        'acumulado_ids': [(0, 0, sube_data), (0, 0, ispt_data)],
                    })

        return True
