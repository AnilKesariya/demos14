# -*- coding: utf-8 -*-
import base64
from itertools import groupby
import re
import logging
import tempfile
import os
from io import BytesIO
from datetime import datetime
import qrcode
import math
from lxml import objectify, etree
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
from suds.client import Client
from jinja2 import Environment, FileSystemLoader
from odoo import _, api, models, fields
from odoo.exceptions import UserError
from odoo.tools.xml_utils import _check_with_xsd

CATALOGO_TIPONOMINA = [('O', 'Ordinaria'), ('E', 'Extraordinaria')]
CHECK_CFDI_RE = re.compile(
    u'''([A-Z]|[a-z]|[0-9]| |Ñ|ñ|!|"|%|&|'|´|-|:|;|>|=|<|@|_|,|\{|\}|`|~|á|é|í|ó|ú|Á|É|Í|Ó|Ú|ü|Ü)''')  # noqa
CFDI_XSLT_CADENA = 'l10n_mx_edi/data/%s/cadenaoriginal.xslt'

_logger = logging.getLogger(__name__)


def create_list_html(array):
    """Convert an array of string to a html list.
    :param array: A list of strings
    :return: an empty string if not array, an html list otherwise.
    """
    if not array:
        return ''
    msg = ''
    for item in array:
        msg += '<li>' + item + '</li>'
    return '<ul>' + msg + '</ul>'


def get_string_cfdi(text, size=100):
    if not text:
        return ''
    for char in CHECK_CFDI_RE.sub('', text):
        text = text.replace(char, ' ')
    return text.strip()[:size]


class HrPayslip(models.Model):
    _name = "hr.payslip"
    _description = 'hr payslip'
    _inherit = ['hr.payslip', 'mail.thread']

    # CDFI
    tipo_nomina = fields.Selection(CATALOGO_TIPONOMINA, string=u"Payroll type")
    registro_patronal_codigo = fields.Char(
        string='Employer Registration',
        related='company_id.registro_patronal.name',
        store=True, readonly=True)
    timbrada = fields.Boolean("Stamped", default=False, copy=False)
    fecha_local = fields.Datetime("Date and local time")
    uuid = fields.Char("UUID", size=36, copy=False)
    qrcode = fields.Binary("QR code", copy=False)
    monto_cfdi = fields.Float("Monto CFDI", copy=False)
    fecha_sat = fields.Char("Stamping date", copy=False)
    cadena_sat = fields.Text("Original bell chain", copy=False)
    certificado_sat = fields.Char("SAT Certificate No.", copy=False)
    sello_sat = fields.Text("SAT Digital Seal", copy=False)
    certificado = fields.Char("No. certificado", copy=False)
    sello = fields.Text("Digital Seal", copy=False)
    cant_letra = fields.Char("Quantity with letter", copy=False)
    retenido = fields.Float("Retained SRI", copy=False)
    descuento = fields.Float(
        "Total deductions without ISR (discount)", copy=False)
    subtotal = fields.Float("Total perceptions (subtotal)", copy=False)
    concepto = fields.Char("Concept", copy=False)
    mandada_cancelar = fields.Boolean('Sent to cancel', copy=False)
    id_cancel_request = fields.Char(
        'Cancellation Request ID', readonly=True, copy=False)
    mensaje_pac = fields.Text('Last message from PAC', copy=False)
    test = fields.Boolean("Stamping in test mode", copy=False)
    noCertificado = fields.Char(
        relation="certificado", string="Certificate No.", copy=False)
    l10n_mx_edi_cfdi_name = fields.Char("CFDI XML Name", copy=False)
    fecha_pago = fields.Date("Payment date", copy=False)
    error_timbrado = fields.Text("Process errors", copy=False)
    estado_timbrado = fields.Selection([
        ('sin_timbrar', 'Sin timbrar'),
        ('en_proceso', 'En proceso'),
        ('a_cancelar', 'A Cancelar'),
        ('cancelada', 'Cancelado'),
        ('timbrada', 'Timbrada'),
        ('error', 'Error')], string="Stamping status",
        default='sin_timbrar', copy=False)
    fecha_ultimo_estatus = fields.Datetime(u"Date of last status", copy=False)
    finiquito = fields.Boolean("Settlement", copy=False)
    origen_recurso = fields.Selection([
        ('IP', 'Ingresos propios'),
        ('IF', 'Ingreso federales'),
        ('IM', 'Ingresos mixtos'),
    ], 'Origin of the resource')
    monto_recurso = fields.Float('Amount of Own Resource')
    total = fields.Float('Total Amount', digits='Payroll', copy=False,
                         help='Total Income + Other Payments - Deductions', default=0.00)
    l10n_mx_edi_cfdi = fields.Binary('CFDI content', copy=False, readonly=True,
                                     help='The cfdi xml content encoded in base64.')

    # Regitro Patronal Nuevo, para usarse como retroactivo en cambios de
    # sucursal de empleados
    registro_patronal_codigo_new = fields.Char(
        'New employer registration', copy=False, readonly=True)

    # compute='_compute_cfdi_values')

    # @api.onchange('company_id', 'company_id.registro_patronal.name')
    # @api.depends('company_id', 'company_id.registro_patronal.name')
    # def update_regsitro_patronal(self):
    #     for rec in self:
    #         rec.registro_patronal_codigo = rec.company_id.registro_patronal and rec.company_id.registro_patronal.name or ''

    def action_payslip_cancel(self):
        if self.filtered(lambda slip: slip.timbrada == True and slip.estado_timbrado in ['a_cancelar', 'timbrada']):
            raise UserError(
                _("No se puede cancelar una nómina timbrada y vigente."))
        self.write({'state': 'cancel'})
        return super(HrPayslip, self).action_payslip_cancel()

    def _make_qrcode(self, payslip, uuid):
        total = payslip.total
        integer, decimal = str(total).split('.')
        padded_total = integer.rjust(10, '0') + '.' + decimal.ljust(6, '0')
        data = '?re=%s&rr=%s&tt=%s&id=%s' % (
            payslip.company_id.vat, payslip.employee_id.rfc, padded_total, uuid)
        img = qrcode.make(data)
        fp, tmpfile = tempfile.mkstemp()
        img.save(tmpfile, 'PNG')
        res = base64.b64encode(open(tmpfile, 'rb').read())
        os.unlink(tmpfile)
        return res

    # Para ser usado por el modulo de contabilidad electronica
    def create_move_comprobantes(self):
        comp_obj = self.env["contabilidad_electronica.comprobante"]
        n = 1
        for rec in self.filtered(lambda r: r.move_id and r.uuid):
            n += 1
            uuid = rec.uuid
            for move_line in rec.move_id.line_id:
                res = comp_obj.search(
                    ['&', ('uuid', '=', uuid), ('move_line_id', '=', move_line.id)])
                if res:
                    continue
                comprobante = [(0, 0, {
                    'monto': rec.monto_cfdi,
                    'uuid': uuid,
                    'rfc': rec.employee_id.rfc,
                })]
                move_line.write({'comprobantes': comprobante})
        return True

    def get_payslip_lines(self, cr, uid, contract_ids, payslip_id, context):
        if context is None:
            context = {}
        res = super().get_payslip_lines(cr, uid, contract_ids, payslip_id, context=context)
        if context and 'cfdi_nomina' in context:
            for line in res:
                rule_id = line["salary_rule_id"]
                line.update(context["cfdi_nomina"][rule_id])
        return res

    def _get_days(self, code):
        dias = horas = 0
        found = False
        for line in self.worked_days_line_ids:
            if line.code == code:
                found = True
                dias += line.number_of_days
                horas += line.number_of_hours

        if not found:
            raise UserError(
                _(u"No se encontró entrada de días trabajados con código %s") % (code))

        return dias, horas

    def _get_input(self, rec, line):
        regla = line.salary_rule_id
        for input in regla.input_ids:
            codigo = input.code
            break
        cantidad = 0
        for input in rec.input_line_ids:
            if input.code == codigo:
                cantidad = input.amount
                break
        return cantidad

    def _get_code(self, line):
        if not line.salary_rule_id.codigo_agrupador:
            raise UserError(
                u"No tiene código SAT: %s" % line.salary_rule_id.name)
        codigo = line.salary_rule_id.codigo_agrupador.code
        return codigo

    def _get_folio(self):
        return str(self.id).zfill(6)

    def _get_ispt_calc(self, no_negativo=True):
        calculado = 0

        if self.tipo_calculo == 'mensual':
            fper = self.get_fper()   # DA/12/15
            calculado = self.ispt / fper
            _logger.info("Mensual: ispt_calc: {} = ispt {}/ FPER {}".format(
                calculado, self.ispt, fper))
        elif self.tipo_calculo in ['ajustado', 'anual']:
            # ISPT  en el periodo
            calculado = self.ispt
            _logger.info("Ajustado: ispt_calc: {} = ispt {}".format(
                calculado, self.ispt))

            if calculado < 0 and no_negativo:
                # No regresa negativos
                calculado = 0

        return calculado

    def _get_ispt_calc_rule(self, rule_localdict, no_negativo=True):
        causado = 0
        ispt = rule_localdict['ISPT']
        actual_ac = rule_localdict['ISPT_AC']  # DA/12/15
        fper = rule_localdict['FPER']

        if self.tipo_calculo == 'mensual':
            causado = ispt / fper
            _logger.info(
                "Mensual: ispt_calc: {} = ispt {}/ FPER {}".format(causado, ispt, fper))
        elif self.tipo_calculo in ['ajustado', 'anual']:

            # ISPT  en el periodo
            causado = ispt
            _logger.info(
                "Ajustado: ispt_calc: {} = ispt {} - actual_ac {}".format(causado, ispt, actual_ac))

        if causado < 0 and no_negativo:
            # No regresa negativos para fines de XML timbrado
            causado = 0

        return causado

    def _check_nom226(self, other_payments):
        """
            Retirar el nodo 002 que no debe existir si existe el 007 o 008, aplicando NOM226
        :param other_payments:  Lista con otros pagos
        :return:
        """
        # 29 de mayo 2020,  para evitar error NOM226:
        # NOM226 Nomina si el valor de este atributo es 02, debe existir
        # el campo TipoOtroPago con la clave 002, siempre que NO se haya registrado
        # otro elemento OtroPago con el valro 007 o 008 en el atributo
        # TipoOtroPago
        for opago in other_payments:
            if opago.get('type') == '002':
                if opago.get('subsidy') != '0.00' or opago.get('amount') != '0.00':
                    msg = _(
                        u"NOM226: Existe monto o subidio en OtroPago 002 y se registro OtroPago 007 o 008 ")
                    self.message_post(body=msg)
                    # raise UserError(msg)
                    break
                other_payments.remove(opago)
                break

        return other_payments

    def _get_sube_calc(self, no_negativo=True):
        calculado = 0

        if self.tipo_calculo == 'mensual':
            fper = self.get_fper()   # DA/12/15
            calculado = self.sube / fper
            _logger.info("Mensual: sube_calc: {} = sube {}/ FPER {}".format(
                calculado, self.ispt, fper))
        elif self.tipo_calculo in ['ajustado', 'anual']:
            # SUBE  en el periodo
            calculado = self.sube
            _logger.info("Ajustado: sube_calc: {} = sube {}".format(
                calculado, self.sube))

            if calculado < 0 and no_negativo:
                # No regresa negativos
                calculado = 0

        return calculado

    def _get_sube_calc_rule(self, rule_localdict, no_negativo=True):
        causado = 0
        sube = rule_localdict['SUBE']
        actual_ac = rule_localdict['SUBE_AC']
        fper = rule_localdict['FPER']

        if self.tipo_calculo == 'mensual':
            causado = sube / fper
            _logger.info(
                "Mensual: causado: {} = sube {}/ FPER {}".format(causado, sube, fper))
        elif self.tipo_calculo in ['ajustado', 'anual']:

            # Subsidio causado en el periodo
            causado = sube
            _logger.info(
                "Ajustado: causado: {} = sube {} - actual_ac {}".format(causado, sube, actual_ac))

        if causado < 0 and no_negativo:
            # No regresa negativos para fines de XML timbrado
            causado = 0

        return causado

    def _get_subsidio_causado(self, no_negativo=True):
        causado = 0

        if self.tipo_calculo == 'mensual':
            fper = self.get_fper()   # DA/12/15
            causado = self.sube / fper
            _logger.info(
                "Mensual: causado: {} = sube {}/ FPER {}".format(causado, self.sube, fper))
        elif self.tipo_calculo in ['ajustado', 'anual']:

            # Subsidio causado en el periodo
            data_sub_causado = self.get_acumulado_subsidio_causado_lines()
            if self.tipo_calculo == 'ajustado':
                actual_ac = data_sub_causado.get('actual_ac')
                causado = self.sube - actual_ac
                _logger.info(
                    "Ajustado: causado: {} = sube {} - actual_ac {}".format(causado, self.sube, actual_ac))
            else:  # anual
                actual_ac = data_sub_causado.get('actual_ac')
                causado = self.sube - actual_ac
                _logger.info(
                    "Anual: causado: {} = sube {} - actual_ac {}".format(causado, self.sube, actual_ac))

            if causado < 0 and no_negativo:
                # No regresa negativos para fines de XML timbrado
                causado = 0

        # elif self.tipo_calculo in ['anual']:
        #     _logger.info("Anual: causado: 0")
        #     causado = 0

        return causado

    def write(self, values):
        if 'estado_timbrado' in values:
            values['fecha_ultimo_estatus'] = datetime.now()
        return super().write(values)

    def action_create_cfdi_background(self):
        return self.action_create_cfdi()

    def es_asimimilado_salario(self):
        return self.contract_id.regimen_contratacion.code in [
            '05', '06', '07', '08', '09', '10', '11'
        ] or False

    def prepare_data_cfdi(self):
        self.ensure_one()
        empleado = self.employee_id
        company = self.company_id
        certificate = self.env['l10n_mx_edi.certificate']
        fecha_local = certificate.get_mx_current_datetime()

        if company.currency_id.name == 'MXN':
            rate = 1.0
        # Si no, obtener el tipo de cambio
        # Esto funciona aunque la moneda base no sea el peso
        else:
            mxn_rate = self.env.ref('base.MXN').rate
            rate = (1.0 / company.currency_id.rate) * mxn_rate
        # ----------------------
        # Complemento nómina
        # ----------------------
        dias_pagados = self._get_days("WORK100")[0]
        if dias_pagados == 0:
            dias_pagados = 1
        # Consideraciones cuenta de banco.
        # Si el número de cuenta es una CLABE, no se pone el dato banco
        num_cuenta = empleado.bank_account_id.acc_number or ''
        if empleado.tipo_cuenta == '40':
            banco = False
        else:
            banco = empleado.bank_account_id.bank_id.code_sat
            # Además, si no es CLABE asegurarse que tiene 10 posiciones la
            # cuenta
            num_cuenta = num_cuenta[len(num_cuenta) - 10:]
            date_to_l = str(self.date_to)
            fecha_alta_l = str(empleado.fecha_alta)
            fecha_final_pago = datetime.strptime(
                date_to_l, "%Y-%m-%d").date()
            fecha_alta = datetime.strptime(
                fecha_alta_l, "%Y-%m-%d").date()
            antiguedad = ((fecha_final_pago - fecha_alta).days + 1) / 7

        # Separar lineas por tipo
        nodos = {'p': [], 'd': [], 'h': [], 'i': [], 'o': []}
        tipos = {}
        tipos[self.env.ref("cfdi_nomina.catalogo_tipo_percepcion").id] = 'p'
        tipos[self.env.ref("cfdi_nomina.catalogo_tipo_deduccion").id] = 'd'
        # tipos[self.env.ref("cfdi_nomina.catalogo_tipo_incapacidad").id] = 'i'
        tipos[self.env.ref("cfdi_nomina.catalogo_tipo_otro_pago").id] = 'o'

        for line in self.line_ids.filtered('salary_rule_id.tipo_id'):
            tipo = tipos[line.salary_rule_id.tipo_id.id]
            goe = line.salary_rule_id.gravado_o_exento or 'gravado'
            if line.total > 0:
                line.write({goe: line.total})
            nodos[tipo].append(line)
            if tipo == 'h':
                nodos['p'].append(line)
            # elif tipo == 'i':
            #     nodos['d'].append(line)

        registro_patronal = empleado.registro_patronal.name or company.registro_patronal.name or False
        if self.contract_id.type_id.code in ['09', '10', '99']:
            registro_patronal = False

        nomina = {
            "type": self.tipo_nomina or CATALOGO_TIPONOMINA[0][0],
            "payment_date": self._context.get("fecha_pago", False) or self.fecha_pago or self.move_id.date,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "number_of_days": "%d" % dias_pagados,
            'employer_register': registro_patronal,
            'curp_emitter': company.curp or False,
            'source_sncf': self.origen_recurso or False,
            'amount_sncf': self.monto_recurso or False,
            'curp_emp': empleado.curp,
            'nss_emp': empleado.imss,
            'date_start': empleado.fecha_alta,
            'seniority_emp': "P%sW" % int(antiguedad) or 0,
            'contract_type': self.contract_id.type_id.code or False,
            'emp_syndicated': 'Si' if empleado.sindicalizado else 'No',
            'working_day': empleado.tipo_jornada.code or False,
            'emp_regimen_type': self.contract_id.regimen_contratacion.code or False,
            'asimilado_salario': self.es_asimimilado_salario(),
            'no_emp': empleado.cod_emp,
            'departament': empleado.department_id.name.replace("/", "") if empleado.department_id else False,
            'emp_job': empleado.job_id and get_string_cfdi(empleado.job_id.name) or False,
            'emp_risk': company.riesgo_puesto.code or False,
            'payment_periodicity': self.contract_id.periodicidad_pago.code or False,
            'emp_bank': banco,
            'emp_account': num_cuenta,
            'emp_base_salary': empleado.sueldo_diario,
            'emp_diary_salary': '%.2f' % empleado.sueldo_imss,
            'emp_state': empleado.address_id.state_id.code or False,
        }

        # --------------------
        # Percepciones
        # --------------------
        totalPercepciones = totalGravadoP = totalExentoP = totalSueldosP = 0.0
        totalSepIndem = totalJubilacion = 0.0
        perceptions = []
        if nodos['p']:
            for percepcion in nodos['p']:
                if not percepcion.total:
                    continue
                tipo_percepcion = self._get_code(percepcion)
                tipo = percepcion.salary_rule_id.gravado_o_exento or 'gravado'
                gravado = round(percepcion.gravado, 2)
                exento = round(percepcion.exento, 2)
                nodo_percepcion = {
                    "type": tipo_percepcion,
                    "key": percepcion.salary_rule_id.code,
                    "concept": percepcion.name.replace(".", "").replace("/", ""),
                    "amount_g": "%.2f" % gravado,
                    "amount_e": "%.2f" % exento
                }
                totalGravadoP += gravado
                totalExentoP += exento
                if tipo_percepcion not in ("022", "023", "025", "039", "044"):
                    totalSueldosP += gravado + exento
                elif tipo_percepcion in ("022", "023", "025"):
                    totalSepIndem += gravado + exento
                elif tipo_percepcion in ("039", "044"):
                    totalJubilacion += gravado + exento
                # ----------------
                # Nodo Horas extra
                # ----------------
                if tipo_percepcion == '019':
                    tipo_horas = "01"
                    # days_code = "EXTRA2" if tipo_horas == '01' else 'EXTRA3'
                    days_code = "P003" if tipo_horas == '01' else 'P015'
                    dias, horas = self._get_days(days_code)
                    with open("/tmp/debug_horas", "w") as f:
                        f.write("%s %s %s %s" %
                                (dias, tipo_horas, horas, gravado + exento))
                    if 'extra_hours' not in nodo_percepcion:
                        nodo_percepcion.update({'extra_hours': []})
                    nodo_percepcion['extra_hours'].append({
                        "days": "%d" % dias,
                        "type": "%s" % tipo_horas,
                        "hours": "%d" % horas,
                        "amount": "%.2f" % (gravado + exento),
                    })
                perceptions.append(nodo_percepcion)

            nomina.update({'perceptions': perceptions})
            totalPercepciones = round(
                totalSueldosP, 2) + round(totalSepIndem, 2) + round(totalJubilacion, 2)

            if totalSepIndem:
                # -------------------
                # Nodo indemnización
                # -------------------
                ultimo_sueldo_mensual = empleado.sueldo_imss * 30
                compensation_no_cumulative = totalSepIndem - ultimo_sueldo_mensual
                if compensation_no_cumulative < 0:
                    compensation_no_cumulative = 0

                nomina.update({
                    'compensation_paid': "%.2f" % totalSepIndem,
                    'compensation_years': "%d" % empleado.anos_servicio,
                    'compensation_last_salary': "%.2f" % ultimo_sueldo_mensual,
                    'compensation_cumulative': "%.2f" % min(totalSepIndem, ultimo_sueldo_mensual),
                    'compensation_no_cumulative': "%.2f" % compensation_no_cumulative,
                    'total_compensation': "%.2f" % totalSepIndem,
                })

            if totalJubilacion:
                ultimo_sueldo_mensual = empleado.sueldo_imss * 30
                retirement_no_cumulative = totalJubilacion - ultimo_sueldo_mensual
                if retirement_no_cumulative < 0:
                    retirement_no_cumulative = 0
                #-------------------
                # Nodo Jubilación
                #-------------------
                nomina.update({
                    'retirement_one_ex': (
                        "%.2f" % totalJubilacion) if tipo_percepcion != '044' else False,
                    'retirement_partiality': ("%.2f" % totalJubilacion) if tipo_percepcion == '044' else False,
                    'retirement_amount_diary': ("%.2f" % empleado.retiro_paricialidad) if tipo_percepcion == '044' else False,
                    'retirement_cumulative': "%.2f" % min(
                        totalJubilacion, ultimo_sueldo_mensual),
                    'retirement_no_cumulative': "%.2f" % retirement_no_cumulative,
                    'total_retirement': "%.2f" % totalJubilacion,
                })

        #--------------------
        # Deducciones
        #--------------------

        totalDeducciones = totalD = retenido = 0.0
        deductions = []
        if nodos['d']:
            for deduccion in nodos['d']:
                if deduccion.total == 0:
                    continue

                tipo_deduccion = self._get_code(deduccion)

                # ISR Negativo se va a Otros Pagos.
                if deduccion.salary_rule_id.code == 'D001' and deduccion.total < 0:
                    nodos['o'].append(deduccion)
                    continue

                if tipo_deduccion == '002':
                    retenido += deduccion.total
                else:
                    totalD += deduccion.total

                deductions.append({
                    "type": self._get_code(deduccion),
                    "key": deduccion.salary_rule_id.code,
                    "concept": deduccion.name.replace(".", "").replace("/", ""),
                    "amount": "%.2f" % abs(deduccion.total),
                })

            nomina.update({
                'deductions': deductions,
                'total_other_deductions': "%.2f" % abs(totalD),
                'total_taxes_withheld': "%.2f" % abs(retenido),
                'show_total_taxes_withheld': True if retenido else False,
            })

            totalDeducciones = abs(totalD) + abs(retenido)

        #----------------
        # Incapacidades
        #----------------
        inhabilities_list = self.worked_days_line_ids.mapped('holiday_ids').filtered(
            lambda inc: inc.afecta_imss == 'incapacidad')
        if inhabilities_list:
            inhabilities = []
            for incapacidad in inhabilities_list:
                inhabilities.append({
                    "days": "{}".format(math.ceil(abs(incapacidad.number_of_days))),
                    "type": incapacidad.tipo_incapacidad_imss,
                    # "amount": "%.2f" % 0.0,
                })
            nomina.update({'inabilities': inhabilities})

        # *****************     Otros pagos     ******************
        # subsidio_causado = self._get_subsidio_causado()

        es_nom226 = False
        subsidio_causado = self.subsidio_causado > 0 and self.subsidio_causado or 0.0
        totalOtrosPagos = 0.0

        if nodos['o']:
            other_payments = []
            for otro_pago in nodos['o']:
                tipo_otro = self._get_code(otro_pago)

                if not otro_pago.total and tipo_otro != '002':
                    continue
                # if otro_pago.total >= 0 and tipo_otro == '002' and not subsidio_causado:
                #     continue

                key = otro_pago.salary_rule_id.code

                # ISR Negativo viene de Deducciones y se cambia el codigo a D007.
                # -- 29/02/2020 - Darwin
                # if otro_pago.salary_rule_id.code == 'D001' and otro_pago.total < 0:
                #     key = "D007"
                # Se comenta el cambio anterior
                # -- 06/03/2020 - Darwin

                node_payment = {
                    "type": self._get_code(otro_pago),
                    "key": key,
                    "concept": otro_pago.name,
                    "amount": "%.2f" % abs(otro_pago.total)
                }
                totalOtrosPagos += abs(otro_pago.total)

                # --------------------
                # Subsidio al empleo
                # --------------------

                if tipo_otro in ['007', '007']:
                    # NOM226 Nomina si el valor de este atributo es 02, debe existir
                    # el campo TipoOtroPago con la clave 002, siempre que NO se haya registrado
                    # otro elemento OtroPago con el valro 007 o 008 en el
                    # atributo TipoOtroPago
                    es_nom226 = True

                if tipo_otro == '002' and otro_pago.salary_rule_id.code != 'D001':

                    # No se trata del caso ISR negativo (code D001)
                    # El nodo subsidio causado SIEMPRE va, aunque sea en 0
                    # 06/03/2020 -- Darwin
                    subsidy_text = "%.2f" % abs(subsidio_causado)
                    node_payment.update({
                        'subsidy': subsidy_text,
                    })
                    # Si subsidio causado es 0, el monto tambien debe ser 0
                    # 06/03/2020 -- Darwin
                    if subsidy_text == "0.00":
                        node_payment.update({
                            'amount': "%.2f" % 0.00,
                        })
                        totalOtrosPagos -= abs(otro_pago.total)

                # if subsidio_causado and tipo_otro == '002' and otro_pago.salary_rule_id.code != 'D001':
                #     # No se trata del caso ISR negativo (code D001)
                #
                #     if node_payment.get('amount') == "0.00":
                #         node_payment.update({
                #             'amount': "%.2f" % 0.01,
                #         })
                #         totalOtrosPagos += 0.01
                #
                #     node_payment.update({
                #         'subsidy': "%.2f" % abs(subsidio_causado),
                #         # 'subsidy': "%.2f" % abs(otro_pago.total),
                #     })

                # --------------------
                # ISR Negativo
                # --------------------
                if otro_pago.total < 0 and otro_pago.salary_rule_id.code == 'D001':
                    node_payment.update({
                        "type": "001",
                    })

                # --------------------
                # Compensación anual
                # --------------------
                elif self._get_code(otro_pago) == '004':
                    year = int(fecha_local.split("-")[0])
                    node_payment.update({
                        'compensation_amount': "%.2f" % abs(otro_pago.total),
                        'compensation_year': "%s" % (year - 1),
                        'compensation_rem': 0,
                    })
                other_payments.append(node_payment)

            # **************** Validación de NOM226 *****************
            if es_nom226:
                # retirar el nodo 002 que no debe existir si existe el 007 o
                # 008
                other_payments = self._check_nom226(other_payments)

            nomina.update({'other_payments': other_payments})

        # ***************** Conceptos y totales ******************
        importe = totalPercepciones + totalOtrosPagos

        # El PAC Advans dijo esta quincena que siempre si se suman con 0.01 31 ene 2019
        # if totalOtrosPagos == 0.01:
        #     importe = totalPercepciones

        subtotal = importe
        descuento = totalDeducciones
        total = subtotal - descuento
        # -Check certificate
        certificate_ids = company.l10n_mx_edi_certificate_ids
        if not certificate_ids:
            raise UserError(
                _(u"No se encontró ningún certificado para {}".format(company.name)))
        certificate_id = certificate_ids.sudo().get_valid_certificate()
        if not certificate_id:
            raise UserError(
                _(u"No se encontró un certificado vigente para {}".format(company.name)))

        nomina.update({
            'total_taxed': "%.2f" % totalGravadoP,
            'total_exempt': "%.2f" % totalExentoP,
            'total_salaries': "%.2f" % totalSueldosP,
            'total_perceptions': "%.2f" % totalPercepciones,
            'total_deductions': "%.2f" % totalDeducciones,
            'total_other': "%.2f" % totalOtrosPagos,
        })

        emitter_name = company.parent_id.partner_id.name if company.parent_id else company.partner_id.name

        return {
            'serie': self.journal_id.serie or '',
            'currency': company.currency_id.name,
            'rate': round(rate, 4) if rate != 1.0 else "1",
            'emitter_zip': self.journal_id.place or "",
            'date_invoice_tz': fecha_local.strftime('%Y-%m-%dT%H:%M:%S'),
            'number': self._get_folio(),
            'document_type': 'N',
            'subtotal': "%.2f" % subtotal,
            'amount_total': "%.2f" % total,
            'emitter_rfc': company.partner_id.vat or "",
            'emitter_name': emitter_name or "",
            'emitter_fiscal_position': company.partner_id.property_account_position_id.l10n_mx_edi_code,
            'receiver_rfc': empleado.rfc or "",
            'receiver_name': empleado.nombre_completo or "",
            'concept_price_unit': "%.2f" % importe,
            'concept_subtotal_wo_discount': "%.2f" % importe,
            'discount_amount': ("%.2f" % abs(descuento)) if descuento else False,
            'certificate': certificate_id.sudo().get_data()[0].decode(),
            'certificate_number': certificate_id.serial_number,
            'payroll': nomina,
            'fecha_local': fecha_local.strftime('%Y-%m-%dT%H:%M:%S'),
            'retenido': retenido,
        }

    def action_create_cfdi(self):
        for rec in self:
            company = rec.company_id
            if rec.state != 'done':
                raise UserError("La nomina no esta en estado confirmado")
            if rec.estado_timbrado == 'timbrada' or rec.uuid:
                continue
            rec.estado_timbrado = 'en_proceso'
            rec.error_timbrado = False

            cfdi_data = rec.prepare_data_cfdi()
            total = cfdi_data.get('amount_total')
            fecha_local = cfdi_data.get('fecha_local')
            subtotal = cfdi_data.get('subtotal')
            descuento = cfdi_data.get('discount_amount')
            retenido = cfdi_data.get('retenido')
            cant_letra = rec.l10n_mx_edi_amount_to_text(
                float(cfdi_data.get('amount_total')))

            # *********************** Sellado del XML ************************
            templates = os.path.join(os.path.dirname(__file__), '..', 'data')
            env = Environment(loader=FileSystemLoader(templates), extensions=[
                'jinja2.ext.autoescape'], autoescape='True')
            jinja2_xml = env.get_template('nomina12.xml').render(cfdi_data)
            xml = objectify.fromstring(jinja2_xml)
            cadena = self.env['account.invoice'].l10n_mx_edi_generate_cadena(
                CFDI_XSLT_CADENA % '3.3', xml)
            certificate_ids = rec.company_id.l10n_mx_edi_certificate_ids
            if not certificate_ids:
                raise UserError(
                    _(u"No se encontró ningún certificado para {}".format(rec.company_id.name)))
            certificate_id = certificate_ids.sudo().get_valid_certificate()
            if not certificate_id:
                raise UserError(
                    _(u"No se encontró un certificado vigente para {}".format(rec.company_id.name)))
            sello = certificate_id.sudo().get_encrypted_cadena(cadena)
            xml.attrib['Sello'] = sello

            # *************** Guardar XML y timbrarlo *******************
            cfd = etree.tostring(xml, pretty_print=True,
                                 xml_declaration=True, encoding='UTF-8')
            fd, fname_debug_xml = tempfile.mkstemp()
            rec.l10n_mx_edi_cfdi = base64.b64encode(cfd)
            with open(fname_debug_xml, "w") as f:
                f.write(cfd.decode())
            os.close(fd)
            os.unlink(fname_debug_xml)
            # Check with xsd
            attachment = self.env.ref(
                'l10n_mx_edi.xsd_cached_cfdv33_xsd', False)
            xsd_datas = base64.b64decode(
                attachment.datas) if attachment else b''
            if xsd_datas:
                try:
                    with BytesIO(xsd_datas) as xsd:
                        _check_with_xsd(cfd, xsd)
                except (IOError, ValueError):
                    _logger.info(_('The xsd file to validate the XML structure was not found'))  # noqa
                except Exception as e:
                    rec.message_post(body=_(
                        'The cfdi generated is not valid') + create_list_html(str(e).split('\\n')))

            rec._l10n_mx_edi_call_service('sign')

            tree = rec.l10n_mx_edi_get_xml_etree()
            cfdi = rec.get_tfd_etree(tree)
            uuid = cfdi.get('UUID', '')
            fecha_timbrado = cfdi.get('FechaTimbrado')
            sello_sat = cfdi.get('SelloSAT')
            certificado_sat = cfdi.get('NoCertificadoSAT')
            version_sello = cfdi.get('Version')

            # ********* Guardar campos en la base de datos ******************
            rec.monto_cfdi = total
            empleado = rec.employee_id
            rec.write({
                'sdo': empleado.sueldo_diario,
                'fecha_local': fecha_local.replace("T", " "),
                'uuid': uuid,
                'test': company.l10n_mx_edi_pac_test_env,
                'qrcode': self._make_qrcode(rec, uuid),
                'monto_cfdi': total,
                'fecha_sat': fecha_timbrado,
                'sello_sat': sello_sat,
                'certificado_sat': certificado_sat,
                'certificado': certificate_id.serial_number,
                'sello': sello,
                'cant_letra': cant_letra,
                'subtotal': subtotal,
                'descuento': descuento,
                'retenido': retenido,
                'cadena_sat': re.sub("(.{80})", "\\1\n", '||%s|%s|%s|%s|%s||' % (version_sello, uuid.lower(),
                                                                                 fecha_timbrado, sello_sat,
                                                                                 certificado_sat), 0, re.DOTALL)
            })
            self._cr.commit()

            # *************** Actualizar XML adjunto **************************
            rec.l10n_mx_edi_xml_update(rec.l10n_mx_edi_cfdi)

            if uuid:
                # self.create_move_comprobantes() Se va a necesitar TODO
                # self.send_mail()
                rec.genera_reporte_pdf()  # Genera y anexa
        return True

    def action_cancel_cfdi(self):
        for record in self:
            if not record.uuid:
                raise UserError(
                    u"No se ha generado el CFDI {} (no se encontró UUID)".format(record.name))

        self._l10n_mx_edi_cancel()
        self.mandada_cancelar = True
        return True

    def _l10n_mx_edi_cancel(self):
        '''Call the cancel service with records that can be signed.
        '''

        records = self.search([
            ('estado_timbrado', 'in', [
             'a_cancelar', 'en_proceso', 'timbrada']),
            ('id', 'in', self.ids)])
        for record in records:
            if record.estado_timbrado in ['en_proceso']:
                record.estado_timbrado = 'cancelado'
                record.message_post(body=_('The cancel service has been called with success'),
                                    subtype='account.mt_invoice_validated')
            else:
                record.estado_timbrado = 'a_cancelar'
        records = self.search([
            ('estado_timbrado', '=', 'a_cancelar'),
            ('id', 'in', self.ids)])
        records._l10n_mx_edi_call_service('cancel')

    def l10n_mx_edi_amount_to_text(self, amount):
        """Method to transform a float amount to text words
        E.g. 100 - ONE HUNDRED
        :returns: Amount transformed to words mexican format for invoices
        :rtype: str
        """
        self.ensure_one()
        currency_type = 'M.N'
        # Split integer and decimal part
        amount_i, amount_d = divmod(amount, 1)
        amount_d = round(amount_d, 2)
        amount_d = int(round(amount_d * 100, 2))
        words = self.company_id.currency_id.with_context(
            lang=self.employee_id.address_home_id.lang or 'es_MX').amount_to_text(amount_i).upper()
        invoice_words = '%(words)s %(amount_d)02d/100 %(curr_t)s' % dict(
            words=words, amount_d=amount_d, curr_t=currency_type)
        return invoice_words

    def get_tfd_etree(self, cfdi):
        """Get the TimbreFiscalDigital node from the cfdi."""
        if not hasattr(cfdi, 'Complemento'):
            return {}
        attribute = 'tfd:TimbreFiscalDigital[1]'
        namespace = {'tfd': 'http://www.sat.gob.mx/TimbreFiscalDigital'}
        node = cfdi.Complemento.xpath(attribute, namespaces=namespace)
        return node[0] if node else {}

    def genera_reporte_pdf(self):
        # ********** Crear PDF *********
        self.ensure_one()
        attach_obj = self.env['ir.attachment']
        rec = self
        fname = "CFDI_Nomina_{}.pdf".format(rec.number).replace('/', '')
        pdf = attach_obj.search([('datas_fname', '=', fname),
                                 ('res_id', '=', rec.id),
                                 ('res_model', '=', self._name)], limit=1)
        if pdf:
            return pdf

        data, otro = self.env.ref(
            'cfdi_nomina.action_report_payslip').render_qweb_pdf([rec.id])
        data = base64.b64encode(data)
        attachment_values = {
            'name': fname,
            'datas': data,
            'datas_fname': fname,
            'description': 'Comprobante Fiscal Digital (PDF) ' + rec.name,
            'res_model': self._name,
            'res_id': rec.id,
            'type': 'binary'
        }
        pdf = attach_obj.sudo().create(attachment_values)
        return pdf

    def send_mail(self):
        mail_obj = self.env["mail.mail"]
        mail_ids = []
        for rec in self:
            if rec.state != 'done':
                continue
            if rec.employee_id.address_home_id and rec.employee_id.address_home_id.email:
                email = rec.employee_id.address_home_id.email
            else:
                continue
            if not rec.uuid:
                raise UserError(u"No está timbrada %s" % rec.name)
            # ********** Recuperar XML **********
            xml = rec.l10n_mx_edi_retrieve_last_attachment()
            if not xml:
                raise UserError("No hay XML anexo en %s" % rec.name)
            # ********** Recuperar o Generar PDF *********
            pdf = rec.genera_reporte_pdf()

            # *********** Preparar para enviar por mail *************
            attachment_ids = [xml.id, pdf.id]
            company = rec.company_id.parent_id or rec.company_id
            values = self.env.ref('cfdi_nomina.email_template_payslip_cfdi').with_context(
                company=company).generate_email(rec.id)

            values.update({
                # 'email_from': self.env.user.email,
                # 'email_to': email,
                # 'subject': 'Adjunto recibo de nómina %s' % rec.number,
                # 'body_html': body_html,
                'attachment_ids': [(6, 0, attachment_ids)]
            })

            mail_ids.append(mail_obj.create(values))

        mail_obj.send(mail_ids)
        return True

    # --------------------------------------------------------------------
    # PACS
    # --------------------------------------------------------------------

    # FINKOK
    def _l10n_mx_edi_finkok_info(self, company_id, service_type):
        test = company_id.l10n_mx_edi_pac_test_env
        username = company_id.l10n_mx_edi_pac_username
        password = company_id.l10n_mx_edi_pac_password
        if service_type == 'sign':
            url = 'http://demo-facturacion.finkok.com/servicios/soap/stamp.wsdl'\
                if test else 'http://facturacion.finkok.com/servicios/soap/stamp.wsdl'
        else:
            url = 'http://demo-facturacion.finkok.com/servicios/soap/cancel.wsdl'\
                if test else 'http://facturacion.finkok.com/servicios/soap/cancel.wsdl'
        return {
            'url': url,
            'multi': False,  # TODO: implement multi
            'username': 'cfdi@vauxoo.com' if test else username,
            'password': 'vAux00__' if test else password,
        }

    def _l10n_mx_edi_finkok_sign(self, pac_info):
        '''SIGN for Finkok.
        '''
        url = pac_info['url']
        username = pac_info['username']
        password = pac_info['password']
        for inv in self:
            cfdi = [inv.l10n_mx_edi_cfdi.decode('UTF-8')]
            try:
                client = Client(url, timeout=20)
                response = client.service.stamp(cfdi, username, password)
            except Exception as e:
                inv.l10n_mx_edi_log_error(str(e))
                continue
            code = 0
            msg = None
            if response.Incidencias:
                code = getattr(response.Incidencias[0][0], 'CodigoError', None)
                msg = getattr(response.Incidencias[0][
                              0], 'MensajeIncidencia', None)
            xml_signed = getattr(response, 'xml', None)
            if xml_signed:
                xml_signed = base64.b64encode(xml_signed.encode('utf-8'))
            inv._l10n_mx_edi_post_sign_process(xml_signed, code, msg)

    def _l10n_mx_edi_finkok_cancel(self, pac_info):
        '''CANCEL for Finkok.
        '''
        url = pac_info['url']
        username = pac_info['username']
        password = pac_info['password']
        for payslip in self:
            uuid = payslip.uuid
            certificate_ids = self.company_id.l10n_mx_edi_certificate_ids
            if not certificate_ids:
                raise UserError(
                    _(u"No se encontró ningún certificado para {}".format(self.company_id.name)))
            certificate_id = certificate_ids.sudo().get_valid_certificate()
            if not certificate_id:
                raise UserError(
                    _(u"No se encontró un certificado vigente para {}".format(self.company_id.name)))

            company_id = self.company_id
            cer_pem = base64.encodestring(certificate_id.get_pem_cer(
                certificate_id.content)).decode('UTF-8')
            key_pem = base64.encodestring(certificate_id.get_pem_key(
                certificate_id.key, certificate_id.password)).decode('UTF-8')
            taxpayer_id = company_id.vat
            rtaxpayer_id = payslip.employee_id.rfc
            totalpayslip = round(payslip.total, 2)
            cancelled = False
            try:
                client = Client(url, timeout=20)
                # Solicitar Cancelacion
                invoices_list = client.factory.create("UUIDS")
                invoices_list.uuids.string = [uuid]
                response = client.service.cancel(
                    invoices_list, username, password, company_id.vat, cer_pem, key_pem)
            except Exception as e:
                payslip.l10n_mx_edi_log_error(str(e))
                continue
            if not hasattr(response, 'Folios'):
                code = getattr(response, 'CodEstatus', None)
                msg = _("Cancelling got an error") if code else _(
                    'A delay of 2 hours has to be respected before to cancel')
            else:
                if response.Folios:
                    code = getattr(response.Folios[0][0], 'EstatusUUID', None)
                else:
                    code = getattr(response, 'CodEstatus', None)
                # cancelled or previously cancelled
                cancelled = code in ('201', '202')
                # no show code and response message if cancel was success
                code = '' if cancelled else code
                msg = '' if cancelled else _("Cancelling got an error")
            payslip._l10n_mx_edi_post_cancel_process(cancelled, code, msg)

    # Soluciones Advans

    @api.model
    def _l10n_mx_edi_advans_info(self, company_id, service_type):
        return self.env['account.invoice']._l10n_mx_edi_advans_info(company_id, service_type)

    def _l10n_mx_edi_advans_sign(self, pac_info):
        '''SIGN for Advans.
        '''
        url = pac_info['url']
        password = pac_info['password']
        for payslip in self:
            cfdi = base64.decodebytes(
                payslip.l10n_mx_edi_cfdi or b'').decode('UTF-8')
            try:
                client = Client(url, timeout=20)
                response = client.service.timbrar2(password, cfdi)
            except Exception as e:
                payslip.l10n_mx_edi_log_error(str(e))
                continue
            msg = getattr(response, 'Message', None) or ''
            code = getattr(response, 'Code', None)
            xml_signed = getattr(response, 'CFDI', None) or ''
            if xml_signed:
                xml_signed = base64.b64encode(xml_signed.encode('utf-8'))

            payslip._l10n_mx_edi_post_sign_process(xml_signed, code, msg)

    def _l10n_mx_edi_advans_cancel(self, pac_info):
        '''CANCEL for Advans.
        '''
        urlcancel = pac_info['urlcancel']
        password = pac_info['password']
        for payslip in self:
            uuid = payslip.uuid
            certificate_ids = self.company_id.l10n_mx_edi_certificate_ids
            if not certificate_ids:
                raise UserError(
                    _(u"No se encontró ningún certificado para {}".format(self.company_id.name)))
            certificate_id = certificate_ids.sudo().get_valid_certificate()
            if not certificate_id:
                raise UserError(
                    _(u"No se encontró un certificado vigente para {}".format(self.company_id.name)))

            cer_pem = certificate_id.get_pem_cer(
                certificate_id.content).decode('UTF-8')
            key_pem = certificate_id.get_pem_key(
                certificate_id.key, certificate_id.password).decode('UTF-8')

            receivervat = payslip.employee_id.rfc
            totalpayslip = round(payslip.total, 2)

            try:
                client = Client(urlcancel)

                if not payslip.id_cancel_request:
                    # Solicitar Cancelacion
                    response = client.service.Cancelar(
                        ApiKey=password,
                        PrivateKeyPem=key_pem,
                        PublicKeyPem=cer_pem,
                        Uuid=uuid,
                        RfcReceptor=receivervat,
                        Total=totalpayslip,
                    )
                else:
                    # Consultar cancelacion en proceso
                    response = client.service.ConsultarEstado(
                        ApiKey=password,
                        Id=payslip.id_cancel_request
                    )
            except Exception as e:
                payslip.l10n_mx_edi_log_error(str(e))
                continue
            if not payslip.id_cancel_request:
                code = getattr(response, 'Code', None)
                detalle = getattr(response, 'Detail', None) or ''
                # Por ser nomina no necesita aceptacion
                cancelled = code in ('100', '101')
                # no show code and response message if cancel was success
                msg = '' if cancelled else getattr(
                    response, 'Message', None) + ', ' + detalle or detalle
                code = '' if cancelled else code
            else:  # Consulta de estatus
                code = getattr(response, 'Code', None)
                detalle = getattr(response, 'Detail', None) or ''
                # cancelled o cancelado sin aceptacion
                cancelled = code in ['100', '105']
                # no show code and response message if cancel was success
                msg = getattr(response, 'Message', None) + ', ' + detalle or ''
                code = '' if cancelled else code

            payslip.mensaje_pac = '{},{}'.format(code, msg)
            id_cancel_request = getattr(response, 'Id', None) or ''
            if id_cancel_request:
                payslip.id_cancel_request = id_cancel_request
                payslip.mandada_cancelar = True

            payslip._l10n_mx_edi_post_cancel_process(cancelled, code, msg)

    # -------------------------------------------------------------------------
    def l10n_mx_edi_xml_update(self, xml):
        # Update the content of the attachment

        for rec in self:
            rec.l10n_mx_edi_cfdi = xml
            fname = "CFDI_Nomina_{}.xml".format(rec.number).replace('/', '')
            rec.l10n_mx_edi_cfdi_name = fname
            # Update the content of the attachment
            attachment_id = rec.l10n_mx_edi_retrieve_last_attachment()
            if attachment_id:
                attachment_id.write({
                    'datas': xml,
                    'mimetype': 'application/xml'
                })
            else:
                self.env["ir.attachment"].create({
                    'name': fname,
                    'datas': xml,
                    'datas_fname': fname,
                    'description': 'Comprobante Fiscal Digital ' + rec.name,
                    'res_model': rec._name,
                    'res_id': rec.id,
                    'mimetype': 'application/xml'
                })

    @api.model
    def l10n_mx_edi_retrieve_attachments(self):
        '''Retrieve all the cfdi attachments generated for this invoice.

        :return: An ir.attachment recordset
        '''
        self.ensure_one()
        if not self.l10n_mx_edi_cfdi_name:
            return []
        domain = [
            ('res_id', '=', self.id),
            ('res_model', '=', self._name),
            ('name', '=', self.l10n_mx_edi_cfdi_name)]
        return self.env['ir.attachment'].search(domain)

    @api.model
    def l10n_mx_edi_retrieve_last_attachment(self):
        attachment_ids = self.l10n_mx_edi_retrieve_attachments()
        return attachment_ids and attachment_ids[0] or None

    def l10n_mx_edi_log_error(self, message):
        self.ensure_one()
        self.message_post(body=_('Error during the process: %s') % message,
                          subtype='account.mt_invoice_validated')

    def _l10n_mx_edi_call_service(self, service_type):
        '''Call the right method according to the pac_name, it's info returned by the '_l10n_mx_edi_%s_info' % pac_name'
        method and the service_type passed as parameter.
        :param service_type: sign or cancel
        '''
        # Regroup the invoices by company (= by pac)
        comp_x_records = groupby(self, lambda r: r.company_id)
        for company_id, records in comp_x_records:
            pac_name = company_id.l10n_mx_edi_pac
            if not pac_name:
                continue
            # Get the informations about the pac
            pac_info_func = '_l10n_mx_edi_%s_info' % pac_name
            service_func = '_l10n_mx_edi_%s_%s' % (pac_name, service_type)
            pac_info = getattr(self, pac_info_func)(company_id, service_type)
            # Call the service with invoices one by one or all together
            # according to the 'multi' value.
            multi = pac_info.pop('multi', False)
            if multi:
                # rebuild the recordset
                records = self.env['account.invoice'].search(
                    [('id', 'in', self.ids), ('company_id', '=', company_id.id)])
                getattr(records, service_func)(pac_info)
            else:
                for record in records:
                    getattr(record, service_func)(pac_info)

    def _l10n_mx_edi_post_sign_process(self, xml_signed, code=None, msg=None):
        """Post process the results of the sign service.
        :param xml_signed: the xml signed datas codified in base64
        :type xml_signed: base64
        :param code: an eventual error code
        :type code: string
        :param msg: an eventual error msg
        :type msg: string
        """
        self.ensure_one()
        if xml_signed:
            body_msg = _('The sign service has been called with success')
            # Update the pac status
            self.timbrada = True
            self.l10n_mx_edi_cfdi = xml_signed
            self.estado_timbrado = 'timbrada'
            self.error_timbrado = False
            self.test = self.company_id.l10n_mx_edi_pac_test_env
            # Update the content of the attachment
            self.l10n_mx_edi_xml_update(xml_signed)

            post_msg = [_('The content of the attachment has been updated')]
        else:
            body_msg = _('The sign service requested failed')
            post_msg = []
        if code:
            post_msg.extend([_('Code: ') + str(code)])
        if msg:
            post_msg.extend([_('Message: ') + msg])
        self.message_post(
            body=body_msg + create_list_html(post_msg),
            subtype='account.mt_invoice_validated')

    def _l10n_mx_edi_post_cancel_process(self, cancelled, code=None, msg=None):
        '''Post process the results of the cancel service.

        :param cancelled: is the cancel has been done with success
        :param code: an eventual error code
        :param msg: an eventual error msg
        '''

        self.ensure_one()
        if cancelled:
            body_msg = _('The cancel service has been called with success')
            self.estado_timbrado = 'cancelada'
        else:
            body_msg = _('The cancel service requested failed')
        post_msg = []
        if code:
            post_msg.extend([_('Code: ') + str(code)])
        if msg:
            post_msg.extend([_('Message: ') + msg])
        self.message_post(
            body=body_msg + create_list_html(post_msg),
            subtype='account.mt_invoice_validated')

    @api.model
    def l10n_mx_edi_get_xml_etree(self, cfdi=None):
        """Get an objectified tree representing the cfdi.
        If the cfdi is not specified, retrieve it from the attachment.
        :param str cfdi: The cfdi as string
        :type: str
        :return: An objectified tree
        :rtype: objectified"""
        # TODO helper which is not of too much help and should be removed
        self.ensure_one()
        if cfdi is None:
            cfdi = base64.decodebytes(self.l10n_mx_edi_cfdi)
        return objectify.fromstring(cfdi)
